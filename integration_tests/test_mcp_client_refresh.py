"""Pinned SDK post-grant refresh contracts over TLS, not an OAuth/credential service.

The fixture seeds a prior grant and cached, trusted issuer metadata. Expiry is advanced
explicitly on the SDK context; no browser flow, wall-clock sleep or durable store is implied.
"""

from __future__ import annotations

import json
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import anyio
import httpx2
import pytest
from mcp import Client
from mcp.client.auth import OAuthClientProvider, OAuthFlowError
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.auth import (
    OAuthClientInformationFull,
    OAuthClientMetadata,
    OAuthMetadata,
    OAuthToken,
    ProtectedResourceMetadata,
)
from mcp.shared.exceptions import MCPError
from test_mcp_client_http import _leaves
from test_mcp_client_oauth import (
    AuthorizationServer,
    MemoryTokens,
    ProtectedServer,
    TLSMaterial,
    _deployment,
    _http,
    _json,
    _tls,
)
from test_mcp_client_sdk import _bindings

from samsarix_ethics import (
    MCPHTTPResponseError,
    ToolCallDeniedError,
    create_mcp_client_tool_policy,
)


class RefreshAuthority(AuthorizationServer):
    """Ephemeral confidential-client grants; no full token-family replay implementation."""

    def __init__(self, resource: ProtectedServer) -> None:
        super().__init__(resource)
        self.grant_types = ["authorization_code", "refresh_token"]
        self.refresh_tokens: dict[str, str] = {}
        self.rotate = True
        self.malformed = False
        self.refresh_count = 0
        self.issued_secrets: list[str] = []

    async def issue_token(self, fields: dict[str, list[str]], tenant: str, send: Any) -> None:
        assert fields["grant_type"] == ["refresh_token"]
        assert "scope" not in fields  # Same grant, never an implicit scope expansion.
        self.refresh_count += 1
        prior = fields["refresh_token"][0]
        if self.refresh_tokens.get(prior) != tenant:
            await _json(send, 400, {"error": "invalid_grant"})
            return
        if self.token_status != 200:
            await _json(send, self.token_status, {"error": "temporarily_unavailable"})
            return
        if self.malformed:
            await _json(send, 200, {"token_type": "Bearer"})
            return
        token = secrets.token_urlsafe(32)
        self.resource.tokens[token] = tenant
        self.issued_secrets.append(token)
        response: dict[str, Any] = {
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": 3600,
            "test_padding": "x" * self.token_padding,
        }
        # Intentionally omit scope in both cases; RFC 6749 section 6 preserves it.
        if self.rotate:
            del self.refresh_tokens[prior]
            replacement = secrets.token_urlsafe(32)
            self.refresh_tokens[replacement] = tenant
            self.issued_secrets.append(replacement)
            response["refresh_token"] = replacement
        await _json(send, 200, response)


def _seed(
    resource: ProtectedServer, authority: RefreshAuthority, *, method: str = "client_secret_basic"
) -> tuple[OAuthClientProvider, MemoryTokens]:
    """Model an existing grant; metadata priming is test-only SDK-state setup."""
    store = MemoryTokens()
    access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    resource.tokens[access] = "one"
    authority.refresh_tokens[refresh] = "one"
    authority.issued_secrets.extend([access, refresh])
    metadata = OAuthClientMetadata(
        redirect_uris=["http://127.0.0.1/callback"],
        scope="support:tools",
        grant_types=["authorization_code", "refresh_token"],
        token_endpoint_auth_method=method,
    )
    store.client_info = OAuthClientInformationFull(
        **metadata.model_dump(),
        client_id="support-one",
        client_secret=authority.clients["support-one"][0],
        issuer=authority.url,
    )
    store.tokens = OAuthToken(
        access_token=access,
        refresh_token=refresh,
        token_type="Bearer",  # noqa: S106 -- OAuth token scheme, not a credential.
        expires_in=3600,
        scope="support:tools",
    )
    oauth = OAuthClientProvider(resource.url, metadata, store)
    oauth.context.oauth_metadata = OAuthMetadata(
        issuer=authority.url,
        authorization_endpoint=authority.url + "/authorize",
        token_endpoint=authority.url + "/token",
        response_types_supported=["code"],
        token_endpoint_auth_methods_supported=[method],
    )
    oauth.context.protected_resource_metadata = ProtectedResourceMetadata(
        resource=resource.url, authorization_servers=[authority.url]
    )
    return oauth, store


@asynccontextmanager
async def _session(
    resource: ProtectedServer,
    authority: RefreshAuthority,
    tls: TLSMaterial,
    oauth: OAuthClientProvider,
    store: MemoryTokens,
    **options: Any,
) -> Any:
    async with (
        _http(resource, authority, tls, oauth=oauth, store=store, **options) as (
            http,
            bounded,
            _,
        ),
        Client(streamable_http_client(resource.url, http_client=http)) as client,
    ):
        yield client, bounded


@pytest.mark.parametrize("rotate", [True, False], ids=["rotation", "omitted-refresh-token"])
@pytest.mark.parametrize("method", ["client_secret_basic", "client_secret_post"])
def test_refresh_preserves_grant_and_exact_policy_dispatch(
    tmp_path: Path, rotate: bool, method: str
) -> None:
    tls = _tls(tmp_path)

    async def scenario() -> None:
        records: list[Any] = []
        async with _deployment(tls, authority_type=RefreshAuthority) as (resource, authority):
            authority.rotate = rotate
            oauth, store = _seed(resource, authority, method=method)
            original_refresh = store.tokens.refresh_token

            async def approve(review: Any) -> Any:
                oauth.context.token_expiry_time = -1  # Expire while a human reviews.
                return review.approval(approved=True)

            async with _session(resource, authority, tls, oauth, store) as (client, bounded):
                adapter = await create_mcp_client_tool_policy(
                    _bindings(records), client, server_id="support", approval_provider=approve
                )
                oauth.context.token_expiry_time = -1
                result = await adapter.call_tool("first", {"mode": "read"})
                assert result.structured_content == {"received": {"mode": "read"}}
                first_refresh = store.tokens.refresh_token
                await adapter.call_tool("second", {"mode": "send"})
                with pytest.raises(ToolCallDeniedError):
                    await adapter.call_tool("second", {"mode": "delete"})
                assert authority.refresh_count == 2 and store.writes == 2
                assert store.tokens.scope == "support:tools"
                assert (first_refresh != original_refresh) is rotate
                assert (store.tokens.refresh_token != first_refresh) is rotate
                assert store.tokens.refresh_token in authority.refresh_tokens
                if rotate:
                    assert original_refresh not in authority.refresh_tokens
                    assert first_refresh not in authority.refresh_tokens
                assert bounded.failure_reason is None
            assert resource.handler_principals == ["one", "one"]
            assert [r.outcome for r in records] == ["allow", "allow", "deny"]
            assert not resource.basic_seen and resource.unauthorized == 0
            evidence = json.dumps([r.to_dict() for r in records])
            for secret in [*authority.issued_secrets, authority.clients["support-one"][0]]:
                assert secret not in evidence
            for body in resource.request_bodies:
                assert authority.clients["support-one"][0].encode() not in body
                assert all(secret.encode() not in body for secret in authority.issued_secrets)

    anyio.run(scenario)


@pytest.mark.parametrize(
    "failure", ["revoked", "wrong-tenant", "unavailable", "malformed", "store"]
)
def test_refresh_failure_during_review_prevents_dispatch(tmp_path: Path, failure: str) -> None:
    tls = _tls(tmp_path)

    async def scenario() -> None:
        records: list[Any] = []
        async with _deployment(tls, authority_type=RefreshAuthority) as (resource, authority):
            oauth, store = _seed(resource, authority)
            prior = store.tokens

            async def approve(review: Any) -> Any:
                oauth.context.token_expiry_time = -1
                if failure == "revoked":
                    authority.refresh_tokens.clear()
                elif failure == "wrong-tenant":
                    authority.refresh_tokens[prior.refresh_token] = "two"
                elif failure == "unavailable":
                    authority.token_status = 503
                elif failure == "malformed":
                    authority.malformed = True
                else:
                    store.fail_writes = True
                return review.approval(approved=True)

            with pytest.raises(ExceptionGroup) as error:
                async with _session(resource, authority, tls, oauth, store) as (client, _):
                    adapter = await create_mcp_client_tool_policy(
                        _bindings(records), client, server_id="support", approval_provider=approve
                    )
                    await adapter.call_tool("second", {"mode": "send"})
                    pytest.fail("Failed refresh must not dispatch the reviewed tool")
            expected = OSError if failure == "store" else OAuthFlowError
            leaves = _leaves(error.value)
            assert any(isinstance(leaf, expected) for leaf in leaves)
            assert all(isinstance(leaf, (expected, MCPError)) for leaf in leaves)
            assert authority.refresh_count == 1
            assert resource.calls == [] and records == [] and store.writes == 0
            assert store.tokens is prior
            if failure == "store":
                # Issuer rotated and provider updated before the store raised. Discard both
                # provider/client; a retry with stale persisted credentials is not recovery.
                assert oauth.context.current_tokens is not prior
                assert prior.refresh_token not in authority.refresh_tokens
                assert oauth.context.current_tokens.refresh_token in authority.refresh_tokens

    anyio.run(scenario)


def test_shared_provider_serializes_expired_token_refresh(tmp_path: Path) -> None:
    tls = _tls(tmp_path)

    async def scenario() -> None:
        records: list[Any] = []
        async with _deployment(tls, authority_type=RefreshAuthority) as (resource, authority):
            oauth, store = _seed(resource, authority)
            async with _session(resource, authority, tls, oauth, store) as (client, _):
                adapter = await create_mcp_client_tool_policy(
                    _bindings(records), client, server_id="support"
                )
                oauth.context.token_expiry_time = -1

                async def call() -> None:
                    result = await adapter.call_tool("first", {"mode": "read"})
                    assert result.structured_content == {"received": {"mode": "read"}}

                async with anyio.create_task_group() as tasks:
                    tasks.start_soon(call)
                    tasks.start_soon(call)
                assert authority.refresh_count == 1 and store.writes == 1
            assert resource.handler_principals == ["one", "one"]
            assert [r.outcome for r in records] == ["allow", "allow"]

    anyio.run(scenario)


def test_refresh_response_budget_stops_before_dispatch(tmp_path: Path) -> None:
    tls = _tls(tmp_path)

    async def scenario() -> None:
        async with _deployment(tls, authority_type=RefreshAuthority) as (resource, authority):
            oauth, store = _seed(resource, authority)
            with pytest.raises(ExceptionGroup) as error:
                async with _session(
                    resource, authority, tls, oauth, store, max_response_bytes=8192
                ) as (client, bounded):
                    adapter = await create_mcp_client_tool_policy(
                        _bindings([]), client, server_id="support"
                    )
                    authority.token_padding = 16384
                    oauth.context.token_expiry_time = -1
                    await adapter.call_tool("first", {"mode": "read"})
                    pytest.fail("Oversized refresh response must stop dispatch")
            assert any(isinstance(leaf, MCPHTTPResponseError) for leaf in _leaves(error.value))
            assert bounded.failure_reason is not None
            assert authority.refresh_count == 1 and store.writes == 0 and resource.calls == []

    anyio.run(scenario)


@pytest.mark.parametrize("interruption", ["timeout", "cancel"])
def test_refresh_interruption_has_no_tool_effects(tmp_path: Path, interruption: str) -> None:
    tls = _tls(tmp_path)

    async def scenario() -> None:
        records: list[Any] = []
        async with _deployment(tls, authority_type=RefreshAuthority) as (resource, authority):
            oauth, store = _seed(resource, authority)

            async def run() -> None:
                async with _session(
                    resource,
                    authority,
                    tls,
                    oauth,
                    store,
                    timeout=0.3 if interruption == "timeout" else 5,
                ) as (client, bounded):
                    adapter = await create_mcp_client_tool_policy(
                        _bindings(records), client, server_id="support"
                    )
                    authority.delay_token = True
                    oauth.context.token_expiry_time = -1
                    try:
                        await adapter.call_tool("first", {"mode": "read"})
                        pytest.fail("Interrupted refresh must not execute a tool")
                    finally:
                        assert bounded.failure_reason is None

            if interruption == "timeout":
                with pytest.raises(ExceptionGroup) as error:
                    await run()
                leaves = _leaves(error.value)
                assert any(isinstance(leaf, httpx2.ReadTimeout) for leaf in leaves)
                assert all(isinstance(leaf, (httpx2.ReadTimeout, MCPError)) for leaf in leaves)
            else:
                async with anyio.create_task_group() as tasks:
                    tasks.start_soon(run)
                    with anyio.fail_after(5):
                        await authority.token_entered.wait()
                    tasks.cancel_scope.cancel()
            with anyio.fail_after(5):
                await authority.token_disconnected.wait()
            assert [path for path, _ in authority.events].count("/token") == 1
            assert authority.refresh_count == 0 and store.writes == 0
            assert resource.calls == [] and records == []

    anyio.run(scenario)


def test_reloaded_relative_expiry_is_not_a_persisted_expiry_clock(tmp_path: Path) -> None:
    tls = _tls(tmp_path)

    async def scenario() -> None:
        async with _deployment(tls, authority_type=RefreshAuthority) as (resource, authority):
            oauth, store = _seed(resource, authority)
            store.tokens.expires_in = 0
            resource.tokens.clear()  # Server independently rejects the expired access token.
            with pytest.raises(ExceptionGroup) as error:
                async with _session(resource, authority, tls, oauth, store):
                    pytest.fail("Expired access token must not establish an authenticated session")
            assert any(isinstance(leaf, OAuthFlowError) for leaf in _leaves(error.value))
            # SDK initialization loads tokens but does not reconstruct an expiry timestamp.
            # The resource's 401 leads to full reauthorization, not a refresh-token exchange.
            assert resource.unauthorized == 1 and authority.refresh_count == 0
            assert store.writes == 0 and resource.calls == []

    anyio.run(scenario)
