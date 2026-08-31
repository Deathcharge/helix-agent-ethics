"""Real loopback TCP contracts; ephemeral test credentials, never a hosted service."""

from __future__ import annotations

import json
import secrets
import socket
from contextlib import asynccontextmanager, nullcontext
from contextvars import ContextVar
from typing import Any

import anyio
import httpx2
import pytest
import uvicorn
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError
from test_mcp_client_sdk import Harness, _bindings

from samsarix_ethics import (
    AuditLogError,
    MCPClientIntegrationError,
    ToolCallDeniedError,
    create_mcp_client_tool_policy,
)

_principal: ContextVar[str] = ContextVar("http_contract_principal")


def _leaves(error: BaseException) -> list[BaseException]:
    if isinstance(error, BaseExceptionGroup):
        return [leaf for child in error.exceptions for leaf in _leaves(child)]
    return [error]


class HTTPHarness(Harness):
    def __init__(self, *, json_response: bool = False) -> None:
        super().__init__()
        self.tokens = {secrets.token_urlsafe(32): tenant for tenant in ("one", "two")}
        self.wire_calls: list[tuple[str, str]] = []
        self.handler_principals: list[str] = []
        self.statuses: list[int] = []
        self.entered = anyio.Event()
        self.finished = anyio.Event()
        self.drop_response = False
        self.app = self.server.streamable_http_app(json_response=json_response)

    async def call_tool(self, ctx: Any, params: Any) -> Any:
        self.handler_principals.append(_principal.get())
        self.entered.set()
        try:
            return await super().call_tool(ctx, params)
        finally:
            self.finished.set()

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        # Test-only bearer middleware, NOT an OAuth implementation or production template.
        header = dict(scope["headers"]).get(b"authorization", b"").decode("ascii")
        tenant = (
            self.tokens.get(header.removeprefix("Bearer "))
            if header.startswith("Bearer ")
            else None
        )
        if tenant is None:
            self.statuses.append(401)
            await send({"type": "http.response.start", "status": 401, "headers": []})
            await send({"type": "http.response.body", "body": b"Unauthorized"})
            return
        body = bytearray()
        method = None

        async def observed_receive() -> Any:
            nonlocal method
            message = await receive()
            if message["type"] == "http.request":
                body.extend(message.get("body", b""))
                if not message.get("more_body", False) and body:
                    method = json.loads(body).get("method")
                    self.wire_calls.append((tenant, method))
            return message

        async def observed_send(message: Any) -> None:
            if message["type"] == "http.response.start":
                self.statuses.append(message["status"])
            if (
                self.drop_response
                and method == "tools/call"
                and message["type"] == "http.response.body"
                and self.finished.is_set()
            ):
                # The handler has executed; simulate loss before its result reaches the caller.
                raise ConnectionResetError("Injected test response disconnect")
            await send(message)

        token = _principal.set(tenant)
        try:
            await self.app(scope, observed_receive, observed_send)
        finally:
            _principal.reset(token)


@asynccontextmanager
async def _serve(harness: HTTPHarness) -> Any:
    """Own one loopback socket and task, with bounded startup and teardown."""
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        address = listener.getsockname()
        server = uvicorn.Server(
            uvicorn.Config(
                harness,
                lifespan="on",
                access_log=False,
                log_level="critical",
                timeout_graceful_shutdown=1,
            )
        )
        # An in-process fixture must not replace pytest's process signal handlers.
        server.capture_signals = nullcontext
        stopped = anyio.Event()

        async def run() -> None:
            try:
                await server.serve(sockets=[listener])
            finally:
                stopped.set()

        async with anyio.create_task_group() as tasks:
            tasks.start_soon(run)
            try:
                with anyio.fail_after(5):
                    while not server.started:
                        if stopped.is_set():
                            raise RuntimeError("Loopback server exited before startup")
                        await anyio.sleep(0.01)
                yield f"http://{address[0]}:{address[1]}/mcp"
            finally:
                server.should_exit = True
                with anyio.fail_after(5, shield=True):
                    await stopped.wait()
                tasks.cancel_scope.cancel()
    assert listener.fileno() == -1


@asynccontextmanager
async def _client(
    url: str, credential: str, *, mode: str = "auto", origin: str | None = None
) -> Any:
    headers = {"Authorization": f"Bearer {credential}"}
    if origin is not None:
        headers["Origin"] = origin
    async with httpx2.AsyncClient(
        headers=headers, trust_env=False, follow_redirects=False, timeout=5
    ) as http:
        async with Client(streamable_http_client(url, http_client=http), mode=mode) as client:
            yield client, http
        assert not http.is_closed  # Caller-supplied HTTP lifetime stays application-owned.
    assert http.is_closed


@pytest.mark.parametrize("json_response", [False, True], ids=["sse", "json"])
@pytest.mark.parametrize("mode", ["auto", "legacy"])
def test_http_support_workflow_and_metadata_is_not_identity(json_response: bool, mode: str) -> None:
    async def scenario() -> None:
        harness, records, reviews = HTTPHarness(json_response=json_response), [], []

        async def approve(review: Any) -> Any:
            reviews.append(review)
            return review.approval(approved=True)

        async with (
            _serve(harness) as url,
            _client(url, next(iter(harness.tokens)), mode=mode) as pair,
        ):
            adapter = await create_mcp_client_tool_policy(
                _bindings(records),
                pair[0],
                server_id="support",
                approval_provider=approve,
                actor_provider=lambda: {"tenant": "one"},
            )
            result = await adapter.call_tool("first", {"mode": "read"})
            assert result.structured_content == {"received": {"mode": "read"}}
            with pytest.raises(ToolCallDeniedError):
                await adapter.call_tool("second", {"mode": "delete"})
            await adapter.call_tool("second", {"mode": "send"}, meta={"tenant": "two"})
        assert harness.handler_principals == ["one", "one"]
        assert [method for _, method in harness.wire_calls].count("tools/call") == 2
        assert len(reviews) == 1
        assert [record.outcome for record in records] == ["allow", "deny", "allow"]
        serialized = json.dumps([record.to_dict() for record in records])
        assert all(credential not in serialized for credential in harness.tokens)

    anyio.run(scenario)


@pytest.mark.parametrize("failure", ["unknown", "audit"])
def test_http_local_rejection_cannot_reach_remote_handler(failure: str) -> None:
    class FailedSink(list[Any]):
        def append(self, _record: Any) -> None:
            raise OSError("Injected test audit outage")

    async def scenario() -> None:
        harness = HTTPHarness()
        async with _serve(harness) as url, _client(url, next(iter(harness.tokens))) as pair:
            adapter = await create_mcp_client_tool_policy(
                _bindings(FailedSink()), pair[0], server_id="support"
            )
            before = len(harness.wire_calls)
            with pytest.raises(
                MCPClientIntegrationError if failure == "unknown" else AuditLogError
            ):
                await adapter.call_tool(
                    "unknown" if failure == "unknown" else "first", {"mode": "read"}
                )
            if failure == "unknown":
                assert len(harness.wire_calls) == before
        assert harness.calls == []
        assert not any(method == "tools/call" for _, method in harness.wire_calls)

    anyio.run(scenario)


@pytest.mark.parametrize("failure", ["credential", "origin"])
def test_http_transport_rejects_bad_credentials_or_origin(failure: str) -> None:
    async def scenario() -> None:
        harness = HTTPHarness()
        credential = (
            next(iter(harness.tokens)) if failure == "origin" else secrets.token_urlsafe(32)
        )
        async with _serve(harness) as url:
            with pytest.raises(ExceptionGroup) as error:
                async with _client(
                    url,
                    credential,
                    origin="https://untrusted.invalid" if failure == "origin" else None,
                ):
                    pytest.fail("Rejected transport must not establish a client")
        assert all(isinstance(leaf, MCPError) for leaf in _leaves(error.value))
        assert harness.statuses and set(harness.statuses) == {403 if failure == "origin" else 401}
        assert harness.calls == []

    anyio.run(scenario)


def test_http_concurrent_clients_keep_credentials_and_calls_isolated() -> None:
    async def scenario() -> None:
        harness = HTTPHarness()

        async def call(url: str, credential: str, tenant: str) -> None:
            async with _client(url, credential) as pair:
                adapter = await create_mcp_client_tool_policy(
                    _bindings([]), pair[0], server_id=tenant
                )
                result = await adapter.call_tool("first", {"mode": "read", "tenant": tenant})
                assert result.structured_content["received"]["tenant"] == tenant

        async with _serve(harness) as url, anyio.create_task_group() as tasks:
            for credential, tenant in harness.tokens.items():
                tasks.start_soon(call, url, credential, tenant)
        assert sorted(harness.handler_principals) == ["one", "two"]
        assert sorted(
            tenant for tenant, method in harness.wire_calls if method == "tools/call"
        ) == ["one", "two"]

    anyio.run(scenario)


@pytest.mark.parametrize("change", ["credential", "registry"])
def test_http_change_during_review_blocks_dispatch(change: str) -> None:
    async def scenario() -> None:
        harness, records = HTTPHarness(), []
        credential = next(iter(harness.tokens))

        async def approve(review: Any) -> Any:
            if change == "credential":
                del harness.tokens[credential]
            else:
                harness.definitions[0].description = "Unreviewed definition"
            return review.approval(approved=True)

        async with _serve(harness) as url, _client(url, credential) as pair:
            adapter = await create_mcp_client_tool_policy(
                _bindings(records), pair[0], server_id="support", approval_provider=approve
            )
            with pytest.raises(MCPError if change == "credential" else MCPClientIntegrationError):
                await adapter.call_tool("second", {"mode": "send"})
        assert harness.calls == []
        assert not any(method == "tools/call" for _, method in harness.wire_calls)
        assert records == []  # Rejected preflight is not a final gate decision.

    anyio.run(scenario)


@pytest.mark.parametrize("interruption", ["timeout", "cancel", "disconnect"])
@pytest.mark.parametrize("json_response", [False, True], ids=["sse", "json"])
@pytest.mark.parametrize("mode", ["auto", "legacy"])
def test_http_interruption_never_retries_an_authorized_call(
    interruption: str, json_response: bool, mode: str
) -> None:
    async def scenario() -> None:
        harness, records = HTTPHarness(json_response=json_response), []
        harness.delay = interruption != "disconnect"
        harness.drop_response = interruption == "disconnect"

        async def exercise(url: str) -> None:
            async with _client(url, next(iter(harness.tokens)), mode=mode) as pair:
                await call(pair[0])

        async def call(client: Client) -> None:
            adapter = await create_mcp_client_tool_policy(
                _bindings(records), client, server_id="support"
            )
            if interruption == "cancel":
                async with anyio.create_task_group() as tasks:
                    tasks.start_soon(adapter.call_tool, "first", {"mode": "read"})
                    with anyio.fail_after(5):
                        await harness.entered.wait()
                    tasks.cancel_scope.cancel()
            elif interruption == "timeout":
                with pytest.raises((TimeoutError, MCPError)):
                    await adapter.call_tool("first", {"mode": "read"}, read_timeout_seconds=0.3)
            else:
                await adapter.call_tool("first", {"mode": "read"}, read_timeout_seconds=5)

        async with _serve(harness) as url:
            if interruption == "disconnect":
                with pytest.raises(ExceptionGroup) as error:
                    await exercise(url)
                assert all(
                    isinstance(leaf, (httpx2.RemoteProtocolError, MCPError))
                    for leaf in _leaves(error.value)
                )
                expected = (
                    MCPError
                    if mode == "legacy" and not json_response
                    else httpx2.RemoteProtocolError
                )
                assert any(isinstance(leaf, expected) for leaf in _leaves(error.value))
            else:
                await exercise(url)
        assert len(harness.calls) == 1
        assert [method for _, method in harness.wire_calls].count("tools/call") == 1
        assert [record.outcome for record in records] == ["allow"]
        assert harness.finished.is_set()

    anyio.run(scenario)
