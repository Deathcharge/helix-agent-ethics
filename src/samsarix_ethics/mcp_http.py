# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Optional, fail-closed response budgets for application-owned MCP HTTP clients."""

from __future__ import annotations

from collections.abc import AsyncIterator
from importlib import import_module
from types import TracebackType
from typing import Any

from .errors import SamsarixEthicsError

MCP_HTTP_RESPONSE_BUDGET_VERSION = 1
DEFAULT_MCP_HTTP_RESPONSE_BYTES = 4 * 1024 * 1024
_MAX_BUDGET = 64 * 1024 * 1024
_CLOSE_TIMEOUT = 5.0


class MCPHTTPResponseError(SamsarixEthicsError):
    """A response breached a budget/encoding contract, or its transport is latched shut."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"MCP HTTP response rejected: {reason}")


def _limit(value: int) -> int:
    if type(value) is not int or not 1 <= value <= _MAX_BUDGET:
        raise ValueError("MCP HTTP byte budgets must be integers in [1, 67108864]")
    return value


class _Budget:
    def __init__(self, owner: MCPHTTPTransport) -> None:
        self.owner = owner
        self.wire = 0
        self.decoded = 0

    def take(self, kind: str, chunk: bytes) -> None:
        self.owner._check()
        if not isinstance(chunk, bytes):
            self.owner._fail("invalid_stream")
        if kind == "wire":
            self.wire += len(chunk)
            if self.wire > self.owner.max_wire_bytes:
                self.owner._fail("wire_bytes")
        else:
            self.decoded += len(chunk)
            if self.decoded > self.owner.max_response_bytes:
                self.owner._fail("decoded_bytes")


class _WireStream:
    def __init__(self, source: Any, budget: _Budget) -> None:
        self.source = source
        self.budget = budget

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for chunk in self.source:
            self.budget.take("wire", chunk)
            yield chunk

    async def aclose(self) -> None:
        # HTTPX2 also closes this stream internally at EOF or on iteration failure.
        with self.budget.owner._fail_after(_CLOSE_TIMEOUT, shield=True):
            await self.source.aclose()


class _DecodedStream:
    def __init__(self, response: Any, budget: _Budget) -> None:
        self.response = response
        self.budget = budget

    async def __aiter__(self) -> AsyncIterator[bytes]:
        try:
            # Keep the SDK's bounded decoder chunks: no re-chunking/aggregation here.
            async for chunk in self.response.aiter_bytes():
                self.budget.take("decoded", chunk)
                yield chunk
        except self.budget.owner._sdk.DecodingError:
            self.budget.owner._fail("invalid_content_encoding")
        finally:
            await self.aclose()

    async def aclose(self) -> None:
        with self.budget.owner._fail_after(_CLOSE_TIMEOUT, shield=True):
            await self.response.aclose()


class MCPHTTPTransport:
    """Own a wrapped async HTTP transport; construct with create_mcp_http_transport.

    Budgets apply per HTTP response, not per SSE event or whole workflow. Any local
    response-contract violation permanently latches this instance; create a fresh
    client/transport only after reconciling remote state. No retries or logs are added.
    """

    def __init__(self, transport: Any, sdk: Any, fail_after: Any, wire: int, decoded: int) -> None:
        self._transport = transport
        self._sdk = sdk
        self._fail_after = fail_after
        self._wire = wire
        self._decoded = decoded
        self._failure_reason: str | None = None
        self._closed = False
        self._wire_stream = type("_MCPWireStream", (_WireStream, sdk.AsyncByteStream), {})
        self._decoded_stream = type("_MCPDecodedStream", (_DecodedStream, sdk.AsyncByteStream), {})

    @property
    def max_wire_bytes(self) -> int:
        """Maximum encoded body bytes accepted from one wrapped response stream."""
        return self._wire

    @property
    def max_response_bytes(self) -> int:
        """Maximum decoded body bytes delivered for one HTTP response."""
        return self._decoded

    @property
    def failure_reason(self) -> str | None:
        """First latched rejection reason, containing no URL, credentials or body data."""
        return self._failure_reason

    def _check(self) -> None:
        if self._failure_reason is not None:
            raise MCPHTTPResponseError(self._failure_reason)
        if self._closed:
            raise MCPHTTPResponseError("transport_closed")

    def _fail(self, reason: str) -> None:
        if self._failure_reason is None:
            self._failure_reason = reason
        raise MCPHTTPResponseError(self._failure_reason) from None

    async def __aenter__(self) -> MCPHTTPTransport:
        self._check()
        await self._transport.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        if not self._closed:
            self._closed = True
            with self._fail_after(_CLOSE_TIMEOUT, shield=True):
                await self._transport.__aexit__(exc_type, exc_value, traceback)

    async def aclose(self) -> None:
        """Close the owned transport once, including after a budget rejection."""
        if not self._closed:
            self._closed = True
            with self._fail_after(_CLOSE_TIMEOUT, shield=True):
                await self._transport.aclose()

    async def handle_async_request(self, request: Any) -> Any:
        """Delegate once and wrap the body before HTTP/MCP consumers can aggregate it."""
        self._check()
        # Exact supported decoder contract; do not silently activate optional codecs.
        request.headers["Accept-Encoding"] = "gzip, deflate, identity"
        response = await self._transport.handle_async_request(request)
        try:
            self._check()  # Another in-flight response may have latched the transport.
            if response.is_stream_consumed or not isinstance(
                response.stream, self._sdk.AsyncByteStream
            ):
                self._fail("response_not_streaming")
            encoding = response.headers.get("content-encoding", "identity").strip(" \t").lower()
            if encoding not in {"identity", "gzip", "deflate"}:
                self._fail("unsupported_encoding")
            lengths = response.headers.get_list("content-length")
            if lengths:
                length = lengths[0].strip(" \t")
                if (
                    len(lengths) != 1
                    or not 1 <= len(length) <= 20
                    or not length.isascii()
                    or not length.isdecimal()
                ):
                    self._fail("invalid_content_length")
                if request.method != "HEAD" and response.status_code not in {204, 304}:
                    if int(length) > self.max_wire_bytes:
                        self._fail("wire_bytes")
                    if encoding == "identity" and int(length) > self.max_response_bytes:
                        self._fail("decoded_bytes")
            budget = _Budget(self)
            response.stream = self._wire_stream(response.stream, budget)
            headers = [
                (k, v)
                for k, v in response.headers.raw
                if k.lower() not in {b"content-encoding", b"content-length"}
            ]
            return self._sdk.Response(
                response.status_code,
                headers=headers,
                stream=self._decoded_stream(response, budget),
                extensions=response.extensions,
            )
        except BaseException:
            with self._fail_after(_CLOSE_TIMEOUT, shield=True):
                await response.aclose()
            raise


def create_mcp_http_transport(
    transport: Any,
    *,
    max_wire_bytes: int = DEFAULT_MCP_HTTP_RESPONSE_BYTES,
    max_response_bytes: int = DEFAULT_MCP_HTTP_RESPONSE_BYTES,
) -> MCPHTTPTransport:
    """Wrap an unshared httpx2 async transport with encoded/decoded response budgets.

    Requires the exact mcp-client extra. The caller configures TLS, proxies, retries
    and pool limits on the wrapped transport; authentication/timeouts belong on its
    HTTP client. The returned wrapper owns and closes the supplied transport.
    """
    wire, decoded = _limit(max_wire_bytes), _limit(max_response_bytes)
    try:
        sdk = import_module("httpx2")
        fail_after = import_module("anyio").fail_after
    except ImportError as exc:
        raise MCPHTTPResponseError("install_mcp_client_extra") from exc
    if getattr(sdk, "__version__", None) != "2.12.0":
        raise MCPHTTPResponseError("unsupported_httpx2_version")
    if not isinstance(transport, sdk.AsyncBaseTransport):
        raise TypeError("transport must be an httpx2.AsyncBaseTransport")
    concrete: type[MCPHTTPTransport] = type(
        "MCPHTTPTransport", (MCPHTTPTransport, sdk.AsyncBaseTransport), {}
    )
    return concrete(transport, sdk, fail_after, wire, decoded)
