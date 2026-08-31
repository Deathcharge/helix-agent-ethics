"""Real TLS and SDK OAuth client-credentials contracts; NOT a hosted auth service."""

from __future__ import annotations

import base64
import hmac
import ipaddress
import json
import secrets
import ssl
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote

import anyio
import httpx2
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from mcp import Client
from mcp.client.auth import OAuthClientProvider, OAuthFlowError
from mcp.client.auth.extensions.client_credentials import ClientCredentialsOAuthProvider
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from mcp.shared.exceptions import MCPError
from test_mcp_client_http import HTTPHarness, _leaves, _serve
from test_mcp_client_sdk import _bindings

from samsarix_ethics import (
    MCPHTTPResponseError,
    ToolCallDeniedError,
    create_mcp_client_tool_policy,
    create_mcp_http_transport,
)


@dataclass
class TLSMaterial:
    certfile: str
    keyfile: str
    ca_pem: str

    def client_context(self) -> ssl.SSLContext:
        context = ssl.create_default_context(cadata=self.ca_pem)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        return context


def _tls(directory: Path, *, hostname: bool = True, expired: bool = False) -> TLSMaterial:
    """Generate test-only material; trust is confined to one client SSLContext."""
    directory.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Ephemeral MCP test CA")])
    ca = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=3))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False
        )
        .add_extension(
            x509.KeyUsage(False, False, False, False, False, True, True, None, None), critical=True
        )
        .sign(ca_key, hashes.SHA256())
    )
    key = ec.generate_private_key(ec.SECP256R1())
    certificate = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "MCP test server")]))
        .issuer_name(ca_name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=2))
        .not_valid_after(now - timedelta(days=1) if expired else now + timedelta(hours=1))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False
        )
        .add_extension(
            x509.KeyUsage(True, False, False, False, False, False, False, None, None), critical=True
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
                if hostname
                else [x509.DNSName("wrong-host.invalid")]
            ),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    certfile, keyfile = directory / "server.pem", directory / "server-key.pem"
    certfile.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    keyfile.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return TLSMaterial(
        str(certfile), str(keyfile), ca.public_bytes(serialization.Encoding.PEM).decode()
    )


class MemoryTokens:
    """Per-client volatile test store, never a recommended production credential store."""

    def __init__(self) -> None:
        self.tokens: OAuthToken | None = None
        self.client_info: OAuthClientInformationFull | None = None
        self.writes = 0
        self.fail_writes = False

    async def get_tokens(self) -> OAuthToken | None:
        return self.tokens

    async def set_tokens(self, tokens: OAuthToken) -> None:
        if self.fail_writes:
            raise OSError("Injected credential-store outage")
        self.tokens = tokens
        self.writes += 1

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        return self.client_info

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self.client_info = client_info


async def _json(send: Any, status: int, value: Any, headers: list[Any] | None = None) -> None:
    body = json.dumps(value).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                *(headers or []),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class ProtectedServer(HTTPHarness):
    def __init__(self, *, json_response: bool = True) -> None:
        super().__init__(json_response=json_response)
        self.tokens.clear()
        self.url = ""
        self.issuer = ""
        self.metadata_requests = 0
        self.unauthorized = 0
        self.basic_seen = False
        self.request_bodies: list[bytes] = []
        self.metadata_resource: str | None = None
        self.metadata_padding = 0
        self.challenge_scope = "support:tools"
        self.forbidden = False
        self.forbidden_count = 0

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] == "http":
            # Observe actual receipt, including requests rejected before MCP reads their body.
            # Keep this bounded and replay the original ASGI messages to the existing harness.
            original_receive = receive
            messages: list[Any] = []
            body = bytearray()
            with anyio.fail_after(5):
                while True:
                    message = await original_receive()
                    if message["type"] == "http.disconnect":
                        return
                    assert message["type"] == "http.request"
                    messages.append(message)
                    body.extend(message.get("body", b""))
                    assert len(body) <= 32768
                    if not message.get("more_body", False):
                        break
            self.request_bodies.append(bytes(body))
            pending_messages = iter(messages)

            async def replay_receive() -> Any:
                message = next(pending_messages, None)
                return message if message is not None else await original_receive()

            receive = replay_receive
            header = dict(scope["headers"]).get(b"authorization", b"").decode("ascii")
            self.basic_seen |= header.startswith("Basic ")
            if scope["path"] == "/.well-known/oauth-protected-resource/mcp":
                self.metadata_requests += 1
                await _json(
                    send,
                    200,
                    {
                        "resource": self.metadata_resource or self.url,
                        "authorization_servers": [self.issuer],
                        "scopes_supported": ["support:tools"],
                        "test_padding": "x" * self.metadata_padding,
                    },
                )
                return
            if header.removeprefix("Bearer ") not in self.tokens or not header.startswith(
                "Bearer "
            ):
                self.unauthorized += 1
                metadata = (
                    self.url.removesuffix("/mcp") + "/.well-known/oauth-protected-resource/mcp"
                )
                await _json(
                    send,
                    401,
                    {"error": "invalid_token"},
                    [
                        (
                            b"www-authenticate",
                            (
                                f'Bearer resource_metadata="{metadata}", '
                                f'scope="{self.challenge_scope}"'
                            ).encode(),
                        ),
                    ],
                )
                return
            if self.forbidden:
                self.forbidden_count += 1
                await _json(send, 403, {"error": "forbidden"})
                return
        await super().__call__(scope, receive, send)


class AuthorizationServer:
    """Client-credentials fixture only; no browser, registration or public listener."""

    def __init__(self, resource: ProtectedServer) -> None:
        self.resource = resource
        self.url = ""
        self.clients = {
            f"support-{tenant}": (secrets.token_urlsafe(32), tenant) for tenant in ("one", "two")
        }
        self.events: list[tuple[str, str]] = []
        self.grants: list[tuple[str, str, str]] = []
        self.metadata_issuer: str | None = None
        self.metadata_padding = 0
        self.token_status = 200
        self.token_padding = 0
        self.token_entered = anyio.Event()
        self.delay_token = False
        self.token_disconnected = anyio.Event()
        self.scope_requests: list[str] = []
        self.grant_types = ["client_credentials"]

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                else:
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        headers = dict(scope["headers"])
        auth = headers.get(b"authorization", b"").decode("ascii")
        self.events.append((scope["path"], auth.split(" ", 1)[0] if auth else "none"))
        if scope["path"] == "/.well-known/oauth-authorization-server":
            await _json(
                send,
                200,
                {
                    "issuer": self.metadata_issuer or self.url,
                    "authorization_endpoint": self.url + "/authorize",
                    "token_endpoint": self.url + "/token",
                    "grant_types_supported": self.grant_types,
                    "token_endpoint_auth_methods_supported": [
                        "client_secret_basic",
                        "client_secret_post",
                    ],
                    "scopes_supported": ["support:tools"],
                    "test_padding": "x" * self.metadata_padding,
                },
            )
            return
        if scope["path"] != "/token" or scope["method"] != "POST":
            await _json(send, 404, {"error": "not_found"})
            return
        self.token_entered.set()
        if self.delay_token:
            while (await receive())["type"] != "http.disconnect":
                pass
            self.token_disconnected.set()
            return
        body = bytearray()
        with anyio.fail_after(5):
            while True:
                message = await receive()
                assert message["type"] == "http.request"
                body.extend(message.get("body", b""))
                assert len(body) <= 32768
                if not message.get("more_body", False):
                    break
        fields = parse_qs(body.decode("ascii"), strict_parsing=True)
        if auth.startswith("Basic "):
            identity, secret = (
                base64.b64decode(auth.removeprefix("Basic "), validate=True).decode().split(":", 1)
            )
            identity, secret = unquote(identity), unquote(secret)
            assert "client_secret" not in fields
        else:
            identity, secret = (
                fields.get("client_id", [""])[0],
                fields.get("client_secret", [""])[0],
            )
        expected, tenant = self.clients.get(identity, ("", ""))
        if not expected or not hmac.compare_digest(expected, secret):
            await _json(send, 401, {"error": "invalid_client"})
            return
        assert fields["resource"] == [self.resource.url]
        await self.issue_token(fields, tenant, send)

    async def issue_token(self, fields: dict[str, list[str]], tenant: str, send: Any) -> None:
        assert fields["grant_type"] == ["client_credentials"]
        self.scope_requests.append(fields["scope"][0])
        if fields["scope"] != ["support:tools"]:
            await _json(send, 400, {"error": "invalid_scope"})
            return
        self.grants.append((tenant, fields["resource"][0], fields["scope"][0]))
        if self.token_status != 200:
            await _json(send, self.token_status, {"error": "temporarily_unavailable"})
            return
        token = secrets.token_urlsafe(32)
        self.resource.tokens[token] = tenant
        await _json(
            send,
            200,
            {
                "access_token": token,
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": "support:tools",
                "test_padding": "x" * self.token_padding,
            },
        )


@asynccontextmanager
async def _deployment(
    tls: TLSMaterial,
    *,
    json_response: bool = True,
    issuer_tls: TLSMaterial | None = None,
    authority_type: type[AuthorizationServer] = AuthorizationServer,
) -> Any:
    resource = ProtectedServer(json_response=json_response)
    authority = authority_type(resource)
    issuer_tls = issuer_tls or tls
    async with (
        _serve(resource, certfile=tls.certfile, keyfile=tls.keyfile) as resource_url,
        _serve(
            authority, certfile=issuer_tls.certfile, keyfile=issuer_tls.keyfile
        ) as authority_url,
    ):
        resource.url = resource_url
        authority.url = authority_url.removesuffix("/mcp")
        resource.issuer = authority.url
        with anyio.fail_after(20):
            yield resource, authority


@asynccontextmanager
async def _http(
    resource: ProtectedServer,
    authority: AuthorizationServer,
    tls: TLSMaterial,
    *,
    tenant: str = "one",
    method: str = "client_secret_basic",
    secret: str | None = None,
    context: ssl.SSLContext | None = None,
    max_response_bytes: int = 4194304,
    store: MemoryTokens | None = None,
    timeout: float = 5,
    auth_timeout_hook: bool = True,
    oauth: OAuthClientProvider | None = None,
) -> Any:
    store = store or MemoryTokens()
    oauth = oauth or ClientCredentialsOAuthProvider(
        server_url=resource.url,
        storage=store,
        client_id=f"support-{tenant}",
        client_secret=secret if secret is not None else authority.clients[f"support-{tenant}"][0],
        token_endpoint_auth_method=method,
        scope="support:tools",
    )
    bounded = create_mcp_http_transport(
        httpx2.AsyncHTTPTransport(
            verify=context or tls.client_context(), trust_env=False, retries=0
        ),
        max_response_bytes=max_response_bytes,
    )

    async def supply_missing_timeout(request: httpx2.Request) -> None:
        # Auth-generated requests can bypass AsyncClient's default timeout insertion.
        request.extensions.setdefault("timeout", httpx2.Timeout(timeout).as_dict())

    async with httpx2.AsyncClient(
        transport=bounded,
        auth=oauth,
        trust_env=False,
        follow_redirects=False,
        timeout=timeout,
        event_hooks={"request": [supply_missing_timeout]} if auth_timeout_hook else None,
    ) as http:
        yield http, bounded, store


@asynccontextmanager
async def _client(
    resource: ProtectedServer,
    authority: AuthorizationServer,
    tls: TLSMaterial,
    *,
    mode: str = "auto",
    **options: Any,
) -> Any:
    async with (
        _http(resource, authority, tls, **options) as (http, bounded, store),
        Client(
            streamable_http_client(resource.url, http_client=http),
            mode=mode,
            read_timeout_seconds=5,
        ) as client,
    ):
        yield client, bounded, store


async def _rejected(http: httpx2.AsyncClient, url: str, expected: type[Exception]) -> BaseException:
    with pytest.raises(ExceptionGroup) as error:
        async with Client(streamable_http_client(url, http_client=http), read_timeout_seconds=5):
            pytest.fail("Invalid TLS/authentication must not establish an MCP client")
    leaves = _leaves(error.value)
    assert any(isinstance(leaf, expected) for leaf in leaves)
    assert all(isinstance(leaf, (expected, MCPError)) for leaf in leaves)
    return error.value


@pytest.mark.parametrize("method", ["client_secret_basic", "client_secret_post"])
@pytest.mark.parametrize("json_response", [True, False], ids=["json", "sse"])
@pytest.mark.parametrize("mode", ["auto", "legacy"])
def test_tls_oauth_support_workflow(
    tmp_path: Path, method: str, json_response: bool, mode: str
) -> None:
    tls = _tls(tmp_path)

    async def scenario() -> None:
        records: list[Any] = []

        async def approve(review: Any) -> Any:
            return review.approval(approved=True)

        with anyio.fail_after(20):
            async with _deployment(tls, json_response=json_response) as (resource, authority):
                async with _client(resource, authority, tls, method=method, mode=mode) as (
                    client,
                    bounded,
                    store,
                ):
                    adapter = await create_mcp_client_tool_policy(
                        _bindings(records),
                        client,
                        server_id="support",
                        approval_provider=approve,
                    )
                    result = await adapter.call_tool("first", {"mode": "read"})
                    assert result.structured_content == {"received": {"mode": "read"}}
                    await adapter.call_tool("second", {"mode": "send"}, meta={"tenant": "two"})
                    with pytest.raises(ToolCallDeniedError):
                        await adapter.call_tool("second", {"mode": "delete"})
                    assert bounded.failure_reason is None
                    assert store.writes == 1
                assert resource.handler_principals == ["one", "one"]
                assert not resource.basic_seen
                assert any(body for body in resource.request_bodies)
                assert all(
                    secret.encode() not in body
                    for secret, _ in authority.clients.values()
                    for body in resource.request_bodies
                )
                assert authority.grants == [("one", resource.url, "support:tools")]
                assert all(
                    scheme == "none" for path, scheme in authority.events if path != "/token"
                )
                assert [r.outcome for r in records] == ["allow", "allow", "deny"]
                serialized = json.dumps([r.to_dict() for r in records])
                assert all(secret not in serialized for secret, _ in authority.clients.values())
                assert all(token not in serialized for token in resource.tokens)

    anyio.run(scenario)


@pytest.mark.parametrize("target", ["resource", "issuer"])
@pytest.mark.parametrize("failure", ["untrusted", "hostname", "expired"])
def test_tls_verification_rejects_before_http_credentials(
    tmp_path: Path,
    target: str,
    failure: str,
) -> None:
    resource_tls = _tls(
        tmp_path / "resource",
        hostname=target != "resource" or failure != "hostname",
        expired=target == "resource" and failure == "expired",
    )
    issuer_tls = _tls(
        tmp_path / "issuer",
        hostname=target != "issuer" or failure != "hostname",
        expired=target == "issuer" and failure == "expired",
    )
    context = ssl.create_default_context()
    if target != "resource" or failure != "untrusted":
        context.load_verify_locations(cadata=resource_tls.ca_pem)
    if target != "issuer" or failure != "untrusted":
        context.load_verify_locations(cadata=issuer_tls.ca_pem)

    async def scenario() -> None:
        async with _deployment(resource_tls, issuer_tls=issuer_tls) as (resource, authority):
            async with _http(resource, authority, resource_tls, context=context) as (
                http,
                bounded,
                store,
            ):
                error = await _rejected(http, resource.url, httpx2.ConnectError)
                assert any("CERTIFICATE_VERIFY_FAILED" in str(leaf) for leaf in _leaves(error))
                assert store.tokens is None and bounded.failure_reason is None
            assert authority.events == [] and resource.calls == []
            assert resource.metadata_requests == (0 if target == "resource" else 1)

    anyio.run(scenario)


@pytest.mark.parametrize("method", ["client_secret_basic", "client_secret_post"])
def test_invalid_client_credentials_never_reach_a_tool(
    tmp_path: Path, method: str, caplog: Any
) -> None:
    tls = _tls(tmp_path)

    async def scenario() -> None:
        async with _deployment(tls) as (resource, authority):
            wrong_secret = secrets.token_urlsafe(32)
            async with _http(resource, authority, tls, method=method, secret=wrong_secret) as (
                http,
                bounded,
                store,
            ):
                await _rejected(http, resource.url, OAuthFlowError)
                assert store.tokens is None and bounded.failure_reason is None
            assert [path for path, _ in authority.events].count("/token") == 1
            assert authority.grants == [] and resource.calls == []
            assert wrong_secret not in caplog.text
            assert all(secret not in caplog.text for secret, _ in authority.clients.values())

    anyio.run(scenario)


@pytest.mark.parametrize("metadata", ["resource", "issuer"])
def test_metadata_identity_mismatch_stops_before_token_exchange(
    tmp_path: Path, metadata: str
) -> None:
    tls = _tls(tmp_path)

    async def scenario() -> None:
        async with _deployment(tls) as (resource, authority):
            if metadata == "resource":
                resource.metadata_resource = resource.url + "/different"
            else:
                authority.metadata_issuer = authority.url + "/different"
            async with _http(resource, authority, tls) as (http, bounded, store):
                await _rejected(http, resource.url, OAuthFlowError)
                assert store.tokens is None and bounded.failure_reason is None
            assert not any(path == "/token" for path, _ in authority.events)
            assert resource.calls == []

    anyio.run(scenario)


@pytest.mark.parametrize("stage", ["resource", "issuer", "token"])
def test_response_budget_also_bounds_oauth_metadata_and_tokens(tmp_path: Path, stage: str) -> None:
    tls = _tls(tmp_path)

    async def scenario() -> None:
        async with _deployment(tls) as (resource, authority):
            if stage == "resource":
                resource.metadata_padding = 10000
            elif stage == "issuer":
                authority.metadata_padding = 10000
            else:
                authority.token_padding = 10000
            async with _http(resource, authority, tls, max_response_bytes=2048) as (
                http,
                bounded,
                store,
            ):
                await _rejected(http, resource.url, MCPHTTPResponseError)
                assert store.tokens is None and bounded.failure_reason == "decoded_bytes"
                before = list(authority.events)
                with pytest.raises(MCPHTTPResponseError):
                    await http.get(resource.url)
                assert authority.events == before
            assert len(authority.grants) == (1 if stage == "token" else 0)
            assert resource.calls == []

    anyio.run(scenario)


@pytest.mark.parametrize("failure", ["service", "storage", "scope"])
def test_token_service_storage_and_scope_failures_prevent_dispatch(
    tmp_path: Path, failure: str
) -> None:
    tls = _tls(tmp_path)

    async def scenario() -> None:
        store = MemoryTokens()
        async with _deployment(tls) as (resource, authority):
            if failure == "service":
                authority.token_status = 503
            elif failure == "storage":
                store.fail_writes = True
            else:
                resource.challenge_scope = "support:admin"
            async with _http(resource, authority, tls, store=store) as (http, bounded, _):
                await _rejected(
                    http, resource.url, OSError if failure == "storage" else OAuthFlowError
                )
                assert store.tokens is None and bounded.failure_reason is None
            assert [path for path, _ in authority.events].count("/token") == 1
            assert resource.calls == []
            if failure == "scope":
                assert authority.scope_requests == ["support:admin"]
                assert authority.grants == []

    anyio.run(scenario)


def test_revoked_access_token_is_reacquired_without_duplicate_tool_execution(
    tmp_path: Path,
) -> None:
    tls = _tls(tmp_path)

    async def scenario() -> None:
        records: list[Any] = []
        async with _deployment(tls) as (resource, authority):
            async with _client(resource, authority, tls) as (client, bounded, store):
                adapter = await create_mcp_client_tool_policy(
                    _bindings(records), client, server_id="support"
                )
                await adapter.call_tool("first", {"mode": "read"})
                resource.tokens.clear()
                await adapter.call_tool("first", {"mode": "read"})
                assert store.writes == 2 and bounded.failure_reason is None
            assert len(authority.grants) == 2
            assert resource.handler_principals == ["one", "one"]
            assert [r.outcome for r in records] == ["allow", "allow"]
            assert resource.unauthorized == 2

    anyio.run(scenario)


def test_client_revocation_during_review_prevents_final_dispatch(tmp_path: Path) -> None:
    tls = _tls(tmp_path)

    async def scenario() -> None:
        records: list[Any] = []
        async with _deployment(tls) as (resource, authority):

            async def approve(review: Any) -> Any:
                resource.tokens.clear()
                del authority.clients["support-one"]
                return review.approval(approved=True)

            with pytest.raises(ExceptionGroup) as error:
                async with _client(resource, authority, tls) as (client, _bounded, _store):
                    adapter = await create_mcp_client_tool_policy(
                        _bindings(records),
                        client,
                        server_id="support",
                        approval_provider=approve,
                    )
                    await adapter.call_tool("second", {"mode": "send"})
                    pytest.fail("Revoked client must not pass final discovery")
            leaves = _leaves(error.value)
            assert any(isinstance(leaf, OAuthFlowError) for leaf in leaves)
            assert all(isinstance(leaf, (OAuthFlowError, MCPError)) for leaf in leaves)
            assert len(authority.grants) == 1 and resource.calls == [] and records == []

    anyio.run(scenario)


def test_separate_oauth_clients_keep_tenants_and_stores_isolated(tmp_path: Path) -> None:
    tls = _tls(tmp_path)

    async def scenario() -> None:
        stores: list[MemoryTokens] = []
        async with _deployment(tls) as (resource, authority):

            async def call(tenant: str) -> None:
                async with _client(resource, authority, tls, tenant=tenant) as (
                    client,
                    _bounded,
                    store,
                ):
                    stores.append(store)
                    adapter = await create_mcp_client_tool_policy(
                        _bindings([]), client, server_id=tenant
                    )
                    await adapter.call_tool("first", {"mode": "read"}, meta={"tenant": "forged"})

            async with anyio.create_task_group() as tasks:
                tasks.start_soon(call, "one")
                tasks.start_soon(call, "two")
            assert sorted(resource.handler_principals) == ["one", "two"]
            assert sorted(tenant for tenant, _, _ in authority.grants) == ["one", "two"]
            assert len({store.tokens.access_token for store in stores}) == 2
            assert all(store.writes == 1 for store in stores)

    anyio.run(scenario)


@pytest.mark.parametrize("interruption", ["timeout", "cancel"])
def test_token_exchange_interruption_closes_without_tool_effects(
    tmp_path: Path, interruption: str
) -> None:
    tls = _tls(tmp_path)

    async def scenario() -> None:
        async with _deployment(tls) as (resource, authority):
            authority.delay_token = True
            async with _http(
                resource, authority, tls, timeout=0.3 if interruption == "timeout" else 5
            ) as (http, bounded, store):
                if interruption == "timeout":
                    await _rejected(http, resource.url, httpx2.ReadTimeout)
                else:

                    async def connect() -> None:
                        async with Client(streamable_http_client(resource.url, http_client=http)):
                            pytest.fail("Token exchange did not finish")

                    async with anyio.create_task_group() as tasks:
                        tasks.start_soon(connect)
                        with anyio.fail_after(5):
                            await authority.token_entered.wait()
                        tasks.cancel_scope.cancel()
                with anyio.fail_after(5):
                    await authority.token_disconnected.wait()
                assert store.tokens is None and bounded.failure_reason is None
            assert resource.calls == [] and authority.grants == []
            assert [path for path, _ in authority.events].count("/token") == 1

    anyio.run(scenario)


def test_sdk_token_request_does_not_inherit_http_client_timeout(tmp_path: Path) -> None:
    tls = _tls(tmp_path)

    async def scenario() -> None:
        observed: list[tuple[str, Any]] = []

        async def observe(request: httpx2.Request) -> None:
            observed.append((request.url.path, request.extensions.get("timeout")))

        async with _deployment(tls) as (resource, authority):
            async with _http(resource, authority, tls, auth_timeout_hook=False) as (
                http,
                _bounded,
                _store,
            ):
                http.event_hooks["request"].append(observe)
                async with Client(streamable_http_client(resource.url, http_client=http)):
                    pass
            # Exact-version upstream behavior, not a recommendation to omit the hook.
            assert [timeout for path, timeout in observed if path == "/token"] == [None]
            assert all(timeout["read"] == 5 for path, timeout in observed if path == "/mcp")
            assert resource.calls == [] and len(authority.grants) == 1

    anyio.run(scenario)


def test_plain_403_is_replayed_by_sdk_auth_but_never_reaches_handler(tmp_path: Path) -> None:
    tls = _tls(tmp_path)

    async def scenario() -> None:
        records: list[Any] = []
        async with _deployment(tls) as (resource, authority):
            async with _client(resource, authority, tls) as (client, bounded, store):
                adapter = await create_mcp_client_tool_policy(
                    _bindings(records), client, server_id="support"
                )
                resource.forbidden = True
                with pytest.raises(MCPError):
                    await adapter.call_tool("first", {"mode": "read"})
                assert store.writes == 1 and bounded.failure_reason is None
            assert resource.forbidden_count == 2
            assert resource.calls == [] and records == [] and len(authority.grants) == 1

    anyio.run(scenario)
