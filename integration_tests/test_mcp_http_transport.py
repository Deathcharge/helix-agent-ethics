"""Response budgets against actual HTTPX2 decoders and loopback MCP/HTTP servers."""

from __future__ import annotations

import gzip
import zlib
from contextlib import asynccontextmanager
from typing import Any

import anyio
import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError
from test_mcp_client_http import HTTPHarness, _leaves, _serve
from test_mcp_client_sdk import _bindings

import samsarix_ethics.mcp_http as http_module
from samsarix_ethics import (
    MCPHTTPResponseError,
    ToolCallDeniedError,
    create_mcp_client_tool_policy,
    create_mcp_http_transport,
)


class EncodedServer(HTTPHarness):
    def __init__(self, encoding: str = "identity", *, json_response: bool = True) -> None:
        super().__init__(json_response=json_response)
        self.encoding = encoding
        self.payload = b"ordinary response"
        self.wire_override: bytes | None = None
        self.declare_length = False
        self.payload_requests = 0
        self.slow_disconnected = anyio.Event()
        self.continue_body = anyio.Event()

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await super().__call__(scope, receive, send)
            return
        if scope["path"] in {"/payload", "/slow", "/controlled"}:
            self.payload_requests += 1
            body = self.payload
            if self.encoding == "gzip":
                body = gzip.compress(body)
            elif self.encoding == "deflate":
                body = zlib.compress(body)
            if self.wire_override is not None:
                body = self.wire_override
            headers = [(b"content-encoding", self.encoding.encode())]
            if self.declare_length:
                headers.append((b"content-length", str(len(body)).encode()))
            await send({"type": "http.response.start", "status": 200, "headers": headers})
            if scope["path"] == "/controlled":
                await send({"type": "http.response.body", "body": b"start", "more_body": True})
                with anyio.fail_after(5):
                    await self.continue_body.wait()
                await send({"type": "http.response.body", "body": b"finish", "more_body": False})
            elif scope["path"] == "/slow":
                await send({"type": "http.response.body", "body": b"start", "more_body": True})
                while (await receive())["type"] != "http.disconnect":
                    pass
                self.slow_disconnected.set()
            else:
                for offset in range(0, len(body), 4096):
                    await send(
                        {
                            "type": "http.response.body",
                            "body": body[offset : offset + 4096],
                            "more_body": True,
                        }
                    )
                await send({"type": "http.response.body", "body": b"", "more_body": False})
            return

        compressor = (
            None
            if self.encoding == "identity"
            else zlib.compressobj(wbits=31 if self.encoding == "gzip" else 15)
        )

        async def encode(message: Any) -> None:
            if compressor is not None:
                message = dict(message)
                if message["type"] == "http.response.start":
                    message["headers"] = [
                        (k, v) for k, v in message["headers"] if k.lower() != b"content-length"
                    ]
                    message["headers"].append((b"content-encoding", self.encoding.encode()))
                elif message["type"] == "http.response.body":
                    message["body"] = compressor.compress(
                        message.get("body", b"")
                    ) + compressor.flush(
                        zlib.Z_SYNC_FLUSH if message.get("more_body", False) else zlib.Z_FINISH
                    )
            await send(message)

        await super().__call__(scope, receive, encode)


@asynccontextmanager
async def _bounded_client(
    url: str, server: EncodedServer, *, mode: str = "auto", **limits: Any
) -> Any:
    transport = create_mcp_http_transport(httpx2.AsyncHTTPTransport(trust_env=False), **limits)
    async with (
        httpx2.AsyncClient(
            transport=transport,
            trust_env=False,
            timeout=5,
            headers={"Authorization": f"Bearer {next(iter(server.tokens))}"},
        ) as http,
        Client(streamable_http_client(url, http_client=http), mode=mode) as client,
    ):
        yield client, transport


@pytest.mark.parametrize("encoding", ["identity", "gzip", "deflate"])
@pytest.mark.parametrize("json_response", [False, True], ids=["sse", "json"])
@pytest.mark.parametrize("mode", ["auto", "legacy"])
def test_bounded_real_mcp_support_workflow(encoding: str, json_response: bool, mode: str) -> None:
    async def scenario() -> None:
        server, records = EncodedServer(encoding, json_response=json_response), []

        async def approve(review: Any) -> Any:
            return review.approval(approved=True)

        async with (
            _serve(server) as url,
            _bounded_client(url, server, mode=mode) as (client, transport),
        ):
            adapter = await create_mcp_client_tool_policy(
                _bindings(records), client, server_id="support", approval_provider=approve
            )
            result = await adapter.call_tool("first", {"mode": "read"})
            assert result.structured_content == {"received": {"mode": "read"}}
            await adapter.call_tool("second", {"mode": "send"})
            with pytest.raises(ToolCallDeniedError):
                await adapter.call_tool("second", {"mode": "delete"})
            assert transport.failure_reason is None
        assert len(server.calls) == 2
        assert [record.outcome for record in records] == ["allow", "allow", "deny"]

    anyio.run(scenario)


@pytest.mark.parametrize("failure", ["wire", "codec", "corrupt"])
@pytest.mark.parametrize("declared", [False, True])
def test_wire_budget_and_invalid_encodings_are_terminal(failure: str, declared: bool) -> None:
    async def scenario() -> None:
        server = EncodedServer({"wire": "identity", "codec": "br", "corrupt": "gzip"}[failure])
        server.declare_length = declared
        server.payload = b"x" * 1000
        if failure == "corrupt":
            server.wire_override = b"invalid gzip data"
        wrapped = create_mcp_http_transport(
            httpx2.AsyncHTTPTransport(trust_env=False), max_wire_bytes=100
        )
        expected = {
            "wire": "wire_bytes",
            "codec": "unsupported_encoding",
            "corrupt": "invalid_content_encoding",
        }[failure]
        async with (
            _serve(server) as url,
            httpx2.AsyncClient(transport=wrapped, trust_env=False) as http,
        ):
            with pytest.raises(MCPHTTPResponseError, match=expected):
                await http.get(url.replace("/mcp", "/payload"))
            with pytest.raises(MCPHTTPResponseError, match=expected):
                await http.get(url.replace("/mcp", "/payload"))
        assert server.payload_requests == 1 and wrapped.failure_reason == expected

    anyio.run(scenario)


@pytest.mark.parametrize("encoding", ["identity", "gzip", "deflate"])
@pytest.mark.parametrize("declared", [False, True])
def test_actual_decoded_budget_and_failure_latch(encoding: str, declared: bool) -> None:
    async def scenario() -> None:
        server = EncodedServer(encoding)
        server.payload = b"sensitive" * 32768
        server.declare_length = declared
        transport = create_mcp_http_transport(
            httpx2.AsyncHTTPTransport(trust_env=False),
            max_wire_bytes=1024 * 1024,
            max_response_bytes=8192,
        )
        async with (
            _serve(server) as url,
            httpx2.AsyncClient(transport=transport, trust_env=False) as http,
        ):
            with pytest.raises(MCPHTTPResponseError) as error:
                await http.get(url.replace("/mcp", "/payload"))
            assert error.value.reason == "decoded_bytes"
            assert "sensitive" not in str(error.value)
            with pytest.raises(MCPHTTPResponseError):
                await http.get(url.replace("/mcp", "/payload"))
        assert server.payload_requests == 1
        assert transport.failure_reason == "decoded_bytes"

    anyio.run(scenario)


@pytest.mark.parametrize("encoding", ["identity", "gzip", "deflate"])
def test_exact_decoded_boundary_is_accepted(encoding: str) -> None:
    async def scenario() -> None:
        server = EncodedServer(encoding)
        server.payload = b"a" * 8192
        transport = create_mcp_http_transport(
            httpx2.AsyncHTTPTransport(trust_env=False), max_response_bytes=8192
        )
        async with (
            _serve(server) as url,
            httpx2.AsyncClient(transport=transport, trust_env=False) as http,
        ):
            response = await http.get(url.replace("/mcp", "/payload"))
            assert response.content == server.payload
            assert "content-encoding" not in response.headers
            assert "content-length" not in response.headers
        assert transport.failure_reason is None

    anyio.run(scenario)


@pytest.mark.parametrize("stage", ["discovery", "result"])
@pytest.mark.parametrize("encoding", ["identity", "gzip"])
def test_mcp_budget_failure_before_discovery_or_after_authorized_effect(
    stage: str, encoding: str
) -> None:
    async def scenario() -> None:
        server, records = EncodedServer(encoding), []
        transport = None
        async with _serve(server) as url:
            with pytest.raises((ExceptionGroup, MCPError)) as error:
                async with _bounded_client(
                    url, server, max_wire_bytes=1048576, max_response_bytes=4096
                ) as (client, transport):
                    if stage == "discovery":
                        server.definitions[0].description = "x" * 20000
                    adapter = await create_mcp_client_tool_policy(
                        _bindings(records), client, server_id="support"
                    )
                    await adapter.call_tool("first", {"mode": "read", "echo": "x" * 20000})
            assert all(
                isinstance(leaf, (MCPError, MCPHTTPResponseError)) for leaf in _leaves(error.value)
            )
        assert transport.failure_reason == "decoded_bytes"
        assert len(server.calls) == (0 if stage == "discovery" else 1)
        assert [record.outcome for record in records] == ([] if stage == "discovery" else ["allow"])

    anyio.run(scenario)


def test_cancelled_response_releases_single_connection_pool() -> None:
    async def scenario() -> None:
        server = EncodedServer()
        transport = create_mcp_http_transport(
            httpx2.AsyncHTTPTransport(
                trust_env=False,
                limits=httpx2.Limits(max_connections=1, max_keepalive_connections=1),
            )
        )
        async with (
            _serve(server) as url,
            httpx2.AsyncClient(transport=transport, trust_env=False, timeout=2) as http,
        ):
            started = anyio.Event()

            async def slow() -> None:
                async with http.stream("GET", url.replace("/mcp", "/slow")) as response:
                    async for chunk in response.aiter_bytes():
                        assert chunk == b"start"
                        started.set()

            async with anyio.create_task_group() as tasks:
                tasks.start_soon(slow)
                with anyio.fail_after(3):
                    await started.wait()
                tasks.cancel_scope.cancel()
            with anyio.fail_after(3):
                await server.slow_disconnected.wait()
            response = await http.get(url.replace("/mcp", "/payload"))
            assert response.content == server.payload
        assert transport.failure_reason is None
        assert server.payload_requests == 2

    anyio.run(scenario)


def test_latched_failure_stops_delivery_from_another_inflight_response() -> None:
    async def scenario() -> None:
        server = EncodedServer()
        server.payload = b"x" * 100
        wrapped = create_mcp_http_transport(
            httpx2.AsyncHTTPTransport(trust_env=False), max_response_bytes=8
        )
        received: list[bytes] = []
        first_chunk = anyio.Event()
        async with (
            _serve(server) as url,
            httpx2.AsyncClient(transport=wrapped, trust_env=False) as http,
        ):

            async def controlled() -> None:
                with pytest.raises(MCPHTTPResponseError, match="decoded_bytes"):
                    async with http.stream("GET", url.replace("/mcp", "/controlled")) as response:
                        async for chunk in response.aiter_bytes():
                            received.append(chunk)
                            first_chunk.set()

            async with anyio.create_task_group() as tasks:
                tasks.start_soon(controlled)
                with anyio.fail_after(3):
                    await first_chunk.wait()
                try:
                    with pytest.raises(MCPHTTPResponseError, match="decoded_bytes"):
                        await http.get(url.replace("/mcp", "/payload"))
                finally:
                    server.continue_body.set()
            assert received == [b"start"]
        assert server.payload_requests == 2

    anyio.run(scenario)


def test_pool_timeout_is_separate_and_does_not_latch_budget() -> None:
    async def scenario() -> None:
        server = EncodedServer()
        wrapped = create_mcp_http_transport(
            httpx2.AsyncHTTPTransport(
                trust_env=False,
                limits=httpx2.Limits(max_connections=1, max_keepalive_connections=1),
            )
        )
        async with (
            _serve(server) as url,
            httpx2.AsyncClient(transport=wrapped, trust_env=False) as http,
        ):
            async with http.stream("GET", url.replace("/mcp", "/controlled")) as response:
                chunks = response.aiter_bytes()
                assert await anext(chunks) == b"start"
                try:
                    with pytest.raises(httpx2.PoolTimeout):
                        await http.get(
                            url.replace("/mcp", "/payload"), timeout=httpx2.Timeout(1, pool=0.05)
                        )
                finally:
                    await chunks.aclose()
                    server.continue_body.set()
            assert (await http.get(url.replace("/mcp", "/payload"))).content == server.payload
        assert server.payload_requests == 2
        assert wrapped.failure_reason is None

    anyio.run(scenario)


@pytest.mark.parametrize("stage", ["iterate", "response_close", "header", "close", "exit"])
def test_cooperative_cleanup_deadline_covers_sdk_internal_close(
    stage: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(http_module, "_CLOSE_TIMEOUT", 0.05)

    async def scenario() -> None:
        closed: list[str] = []

        class HangingStream(httpx2.AsyncByteStream):
            async def __aiter__(self) -> Any:
                yield b"ok"

            async def aclose(self) -> None:
                closed.append("response")
                await anyio.sleep_forever()

        class HangingTransport(httpx2.AsyncBaseTransport):
            async def handle_async_request(self, request: Any) -> Any:
                return httpx2.Response(
                    200,
                    headers={"Content-Encoding": "br"} if stage == "header" else {},
                    stream=HangingStream(),
                )

            async def aclose(self) -> None:
                closed.append("transport")
                await anyio.sleep_forever()

        wrapped = create_mcp_http_transport(HangingTransport())
        # An outer watchdog timing out must fail the test, not satisfy raises().
        with anyio.fail_after(2):
            with pytest.raises(TimeoutError):
                if stage == "close":
                    await wrapped.aclose()
                elif stage == "exit":
                    await wrapped.__aexit__()
                else:
                    response = await wrapped.handle_async_request(
                        httpx2.Request("GET", "https://example.invalid")
                    )
                    if stage == "response_close":
                        await response.aclose()
                    else:
                        await response.aread()
        assert closed == ["transport" if stage in {"close", "exit"} else "response"]
        assert wrapped.failure_reason == ("unsupported_encoding" if stage == "header" else None)

    anyio.run(scenario)
