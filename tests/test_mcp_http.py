"""Budget/lifecycle unit tests without optional HTTP or MCP dependencies."""

from __future__ import annotations

import asyncio
from contextlib import nullcontext
from types import SimpleNamespace
from typing import Any

import pytest

import samsarix_ethics.mcp_http as module
from samsarix_ethics import MCPHTTPResponseError, create_mcp_http_transport


class Stream:
    def __init__(self, chunks: list[Any]) -> None:
        self.chunks = chunks
        self.read = 0
        self.closed = 0

    async def __aiter__(self) -> Any:
        for chunk in self.chunks:
            self.read += 1
            if isinstance(chunk, BaseException):
                raise chunk
            yield chunk

    async def aclose(self) -> None:
        self.closed += 1


class Headers:
    def __init__(self, raw: list[tuple[bytes, bytes]]) -> None:
        self.raw = raw

    def get_list(self, name: str) -> list[str]:
        return [v.decode() for k, v in self.raw if k.decode().lower() == name.lower()]

    def get(self, name: str, default: str) -> str:
        values = self.get_list(name)
        return ", ".join(values) if values else default


class Response:
    def __init__(
        self, status: int = 200, *, headers: Any = (), stream: Any = None, extensions: Any = None
    ) -> None:
        self.status_code = status
        self.headers = Headers(list(headers))
        self.stream = Stream([]) if stream is None else stream
        self.extensions = extensions
        self.is_stream_consumed = False
        self.is_closed = False

    async def aiter_bytes(self) -> Any:
        self.is_stream_consumed = True
        async for chunk in self.stream:
            yield chunk

    async def aclose(self) -> None:
        if not self.is_closed:
            self.is_closed = True
            await self.stream.aclose()


class Transport:
    def __init__(self, response: Response | None = None) -> None:
        self.response = Response() if response is None else response
        self.calls = self.entered = self.exited = self.closed = 0
        self.fail: BaseException | None = None
        self.on_request: Any = None

    async def __aenter__(self) -> Any:
        self.entered += 1
        return self

    async def __aexit__(self, *_args: Any) -> None:
        self.exited += 1

    async def aclose(self) -> None:
        self.closed += 1

    async def handle_async_request(self, _request: Any) -> Response:
        self.calls += 1
        if self.fail:
            raise self.fail
        if self.on_request:
            self.on_request()
        return self.response


@pytest.fixture(autouse=True)
def sdk(monkeypatch: pytest.MonkeyPatch) -> Any:
    fake = SimpleNamespace(
        __version__="2.12.0",
        AsyncBaseTransport=Transport,
        AsyncByteStream=Stream,
        Response=Response,
        DecodingError=type("DecodingError", (Exception,), {}),
    )
    monkeypatch.setattr(
        module,
        "import_module",
        lambda name: (
            fake
            if name == "httpx2"
            else SimpleNamespace(fail_after=lambda *_args, **_kwargs: nullcontext())
        ),
    )
    return fake


def request(method: str = "POST") -> Any:
    return SimpleNamespace(method=method, headers={})


def collect(transport: Any, req: Any = None) -> bytes:
    async def run() -> bytes:
        response = await transport.handle_async_request(request() if req is None else req)
        return b"".join([chunk async for chunk in response.aiter_bytes()])

    return asyncio.run(run())


@pytest.mark.parametrize("field", ["max_wire_bytes", "max_response_bytes"])
@pytest.mark.parametrize("value", [0, -1, True, 1.0, "10", None, 67108865])
def test_configuration_rejected_before_import(field: str, value: Any, monkeypatch: Any) -> None:
    monkeypatch.setattr(
        module, "import_module", lambda _: pytest.fail("Invalid budget imported SDK")
    )
    with pytest.raises(ValueError, match="byte budgets"):
        create_mcp_http_transport(Transport(), **{field: value})


def test_factory_optional_dependency_version_and_type(sdk: Any, monkeypatch: Any) -> None:
    with pytest.raises(TypeError, match="AsyncBaseTransport"):
        create_mcp_http_transport(object())
    sdk.__version__ = "2.11.0"
    with pytest.raises(MCPHTTPResponseError, match="unsupported_httpx2_version"):
        create_mcp_http_transport(Transport())

    def missing(_: str) -> Any:
        raise ImportError("missing")

    monkeypatch.setattr(module, "import_module", missing)
    with pytest.raises(MCPHTTPResponseError, match="install_mcp_client_extra"):
        create_mcp_http_transport(Transport())


def test_exact_limit_headers_streaming_and_owned_close() -> None:
    source = Stream([b"123", b"45"])
    raw = Response(
        headers=[
            (b"Content-Length", b" \t5\t "),
            (b"Content-Encoding", b" \tIDENTITY\t "),
            (b"x-keep", b"yes"),
        ],
        stream=source,
    )
    base = Transport(raw)
    wrapped = create_mcp_http_transport(base, max_wire_bytes=5, max_response_bytes=5)
    req = request()

    async def run() -> None:
        async with wrapped as entered:
            assert entered is wrapped
            response = await wrapped.handle_async_request(req)
            assert source.read == 0
            assert response.headers.raw == [(b"x-keep", b"yes")]
            assert [chunk async for chunk in response.aiter_bytes()] == [b"123", b"45"]
            await response.aclose()
        await wrapped.aclose()
        await wrapped.__aexit__()
        with pytest.raises(MCPHTTPResponseError, match="transport_closed"):
            await wrapped.handle_async_request(req)
        with pytest.raises(MCPHTTPResponseError, match="transport_closed"):
            await wrapped.__aenter__()

    asyncio.run(run())
    assert source.closed == 1
    assert (base.calls, base.entered, base.exited, base.closed) == (1, 1, 1, 0)
    assert wrapped.failure_reason is None
    assert req.headers["Accept-Encoding"] == "gzip, deflate, identity"


@pytest.mark.parametrize("kind", ["wire", "decoded"])
def test_cross_chunk_breach_stops_reading_and_latches(kind: str) -> None:
    source = Stream([b"123", b"456", b"must not read"])
    base = Transport(Response(stream=source))
    wrapped = create_mcp_http_transport(
        base,
        max_wire_bytes=5 if kind == "wire" else 10,
        max_response_bytes=5 if kind == "decoded" else 10,
    )
    with pytest.raises(MCPHTTPResponseError) as error:
        collect(wrapped)
    assert error.value.reason == f"{kind}_bytes"
    assert wrapped.failure_reason == error.value.reason
    with pytest.raises(MCPHTTPResponseError) as second:
        wrapped._fail("a_later_failure")
    assert second.value.reason == error.value.reason
    with pytest.raises(MCPHTTPResponseError):
        collect(wrapped)
    assert base.calls == 1 and source.read == 2 and source.closed == 1
    asyncio.run(wrapped.aclose())
    asyncio.run(wrapped.aclose())
    assert base.closed == 1


@pytest.mark.parametrize(
    "headers,reason",
    [
        ([(b"Content-Length", b"11")], "wire_bytes"),
        ([(b"Content-Length", b"6")], "decoded_bytes"),
        ([(b"Content-Length", b"-1")], "invalid_content_length"),
        ([(b"Content-Length", b"1, 1")], "invalid_content_length"),
        ([(b"Content-Length", b"")], "invalid_content_length"),
        ([(b"Content-Length", b"9" * 30)], "invalid_content_length"),
        ([(b"Content-Length", "\u0661".encode())], "invalid_content_length"),
        ([(b"Content-Length", "\u00a01".encode())], "invalid_content_length"),
        ([(b"Content-Length", b"1"), (b"Content-Length", b"1")], "invalid_content_length"),
        ([(b"Content-Encoding", b"br")], "unsupported_encoding"),
        ([(b"Content-Encoding", "gzip\u00a0".encode())], "unsupported_encoding"),
        ([(b"Content-Encoding", b"gzip, deflate")], "unsupported_encoding"),
    ],
)
def test_header_rejection_never_reads_body(headers: Any, reason: str) -> None:
    source = Stream([b"sensitive"])
    wrapped = create_mcp_http_transport(
        Transport(Response(headers=headers, stream=source)), max_wire_bytes=10, max_response_bytes=5
    )
    with pytest.raises(MCPHTTPResponseError) as error:
        collect(wrapped)
    assert error.value.reason == reason
    assert "sensitive" not in str(error.value)
    assert source.read == 0 and source.closed == 1


@pytest.mark.parametrize("method,status", [("HEAD", 200), ("GET", 304), ("POST", 204)])
def test_no_body_response_allows_representation_length(method: str, status: int) -> None:
    wrapped = create_mcp_http_transport(
        Transport(Response(status, headers=[(b"Content-Length", b"999")])), max_wire_bytes=1
    )
    assert collect(wrapped, request(method)) == b""


@pytest.mark.parametrize("failure", [RuntimeError("source failed"), asyncio.CancelledError()])
def test_source_failure_or_cancellation_closes_response(failure: BaseException) -> None:
    source = Stream([failure])
    wrapped = create_mcp_http_transport(Transport(Response(stream=source)))
    with pytest.raises(type(failure)):
        collect(wrapped)
    assert source.closed == 1 and wrapped.failure_reason is None


@pytest.mark.parametrize("state", ["consumed", "invalid_stream", "invalid_chunk", "other_failure"])
def test_invalid_stream_state_and_concurrent_failure_fail_closed(state: str) -> None:
    source = Stream([b"ok"] if state != "invalid_chunk" else ["not bytes"])
    response = Response(stream=source)
    if state == "consumed":
        response.is_stream_consumed = True
    if state == "invalid_stream":
        response.stream = SimpleNamespace(aclose=source.aclose)
    base = Transport(response)
    wrapped = create_mcp_http_transport(base)
    if state == "other_failure":
        base.on_request = lambda: setattr(wrapped, "_failure_reason", "decoded_bytes")
    with pytest.raises(MCPHTTPResponseError):
        collect(wrapped)
    assert source.closed == 1


def test_transport_error_propagates_without_retry() -> None:
    base = Transport()
    base.fail = OSError("connection failed")
    wrapped = create_mcp_http_transport(base)
    with pytest.raises(OSError):
        collect(wrapped)
    assert base.calls == 1 and wrapped.failure_reason is None


def test_decoder_failure_is_latched(sdk: Any) -> None:
    wrapped = create_mcp_http_transport(Transport(Response(stream=Stream([sdk.DecodingError()]))))
    with pytest.raises(MCPHTTPResponseError, match="invalid_content_encoding"):
        collect(wrapped)
    assert wrapped.failure_reason == "invalid_content_encoding"


@pytest.mark.parametrize("has_primary", [False, True])
def test_cleanup_failure_preserves_primary_error(has_primary: bool) -> None:
    primary = RuntimeError("original")

    class ClosingErrorStream(Stream):
        async def aclose(self) -> None:
            await super().aclose()
            raise OSError("secondary close failure")

    source = ClosingErrorStream([primary] if has_primary else [b"ok"])
    wrapped = create_mcp_http_transport(Transport(Response(stream=source)))
    with pytest.raises(RuntimeError if has_primary else OSError) as error:
        collect(wrapped)
    if has_primary:
        assert error.value is primary
        assert any("cleanup failed" in note for note in primary.__notes__)
    assert source.closed == 1


def test_context_exit_preserves_supplied_primary_error() -> None:
    primary = RuntimeError("caller primary")

    class ClosingErrorTransport(Transport):
        async def __aexit__(self, *_args: Any) -> None:
            raise OSError("secondary close failure")

    wrapped = create_mcp_http_transport(ClosingErrorTransport())

    async def run() -> None:
        async with wrapped:
            raise primary

    with pytest.raises(RuntimeError) as error:
        asyncio.run(run())
    assert error.value is primary
    assert any("cleanup failed" in note for note in primary.__notes__)
