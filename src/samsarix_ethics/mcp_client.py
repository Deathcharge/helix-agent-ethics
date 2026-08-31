# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""One-round, fail-closed MCP v2 client enforcement with pinned discovery."""

from __future__ import annotations

import hashlib
import hmac
import inspect
import json
import math
import re
from collections.abc import Awaitable, Callable, Iterator, Mapping
from dataclasses import dataclass, field, replace
from importlib import import_module
from secrets import token_hex
from typing import Any, cast

from .approval import ToolCallApproval
from .catalog import MAX_TOOL_CATALOG_TOOLS, validate_tool_catalog_registration
from .errors import InputValidationError, SamsarixEthicsError
from .gate import BoundToolCatalog, BoundToolGate
from .models import Outcome
from .validation import MAX_CONTAINER_ITEMS, freeze_json_value, thaw_json_value, validate_context

MCP_CLIENT_ADAPTER_VERSION = 1
MAX_MCP_CLIENT_DISCOVERY_PAGES = 256
MAX_MCP_CLIENT_SNAPSHOT_BYTES = 1_048_576

_Provider = Callable[[], Mapping[str, Any] | None]
_Reviewer = Callable[["MCPClientReviewRequest"], Awaitable[ToolCallApproval | None]]


class MCPClientIntegrationError(SamsarixEthicsError):
    """The client cannot safely authorize or send the requested MCP call."""


def _seconds(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError("timeout must be a finite number of seconds in (0, 3600]")
    if not 0 < value <= 3600 or not math.isfinite(value):
        raise ValueError("timeout must be a finite number of seconds in (0, 3600]")
    return float(value)


def _copy(value: Any, *, label: str) -> dict[str, Any]:
    return cast(
        dict[str, Any], thaw_json_value(freeze_json_value(validate_context(value, label=label)))
    )


def _canonical_chunks(value: dict[str, Any], *, initial_size: int = 0) -> Iterator[bytes]:
    size = initial_size
    encoder = json.JSONEncoder(
        sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":")
    )
    for part in encoder.iterencode(value):
        chunk = part.encode("ascii")
        size += len(chunk)
        if size > MAX_MCP_CLIENT_SNAPSHOT_BYTES:
            raise MCPClientIntegrationError("MCP client snapshot exceeds the canonical byte limit")
        yield chunk


def _digest(value: dict[str, Any]) -> str:
    digest = hashlib.sha256()
    for chunk in _canonical_chunks(value):
        digest.update(chunk)
    return f"v1:sha256:{digest.hexdigest()}"


def _container_items(value: dict[str, Any]) -> int:
    """Count entries in an already shape-validated payload, including its outer key."""
    count = 0
    stack: list[Any] = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, Mapping):
            count += len(item)
            stack.extend(item.values())
        elif isinstance(item, list):
            count += len(item)
            stack.extend(item)
    return count


def _facts(provider: _Provider | None, *, label: str) -> dict[str, Any]:
    value = {} if provider is None else provider()
    if inspect.isawaitable(value):
        if inspect.iscoroutine(value):
            value.close()
        raise MCPClientIntegrationError(f"{label} must return synchronously")
    return _copy({} if value is None else value, label=label)


@dataclass(frozen=True, slots=True, repr=False)
class MCPClientReviewRequest:
    """Sensitive review payload binding target, registry, actor and full request.

    Its approval fingerprint belongs to the client adapter, not directly to ToolGate.
    Only the adapter can translate verified evidence to the final gate invocation.
    """

    server_id: str
    tool_name: str
    tool_call_id: str
    tool_call_fingerprint: str
    registry_fingerprint: str
    capabilities: tuple[str, ...]
    policy_id: str
    policy_version: str
    policy_fingerprint: str
    _request: Any = field(repr=False)

    def __repr__(self) -> str:
        return f"MCPClientReviewRequest(server_id={self.server_id!r}, tool_name={self.tool_name!r})"

    @property
    def request(self) -> dict[str, Any]:
        """Return detached arguments, metadata and continuation data for trusted UI."""
        return cast(dict[str, Any], thaw_json_value(self._request))

    def approval(self, *, approved: bool) -> ToolCallApproval:
        """Create unsigned, one-call evidence after the application verifies its reviewer."""
        return ToolCallApproval(self.tool_call_id, approved, self.tool_call_fingerprint)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the sensitive review request, never intended for ordinary logs."""
        return {
            "adapter_version": MCP_CLIENT_ADAPTER_VERSION,
            "server_id": self.server_id,
            "registry_fingerprint": self.registry_fingerprint,
            "tool_name": self.tool_name,
            "capabilities": list(self.capabilities),
            "request": self.request,
            "approval_binding": {
                "tool_call_id": self.tool_call_id,
                "tool_call_fingerprint": self.tool_call_fingerprint,
            },
            "policy": {
                "id": self.policy_id,
                "version": self.policy_version,
                "fingerprint": self.policy_fingerprint,
            },
        }


@dataclass(frozen=True, slots=True, repr=False)
class MCPClientToolPolicy:
    """Authorize each outbound tools/call round on one application-owned MCP v2 session."""

    server_id: str
    registry_fingerprint: str
    _bindings: BoundToolCatalog
    _session: Any
    _list_tools: Any
    _call_tool: Any
    _types: Any
    _fail_after: Any
    _request_type: Any
    _tools: tuple[Any, ...]
    _actor_provider: _Provider | None
    _context_provider: _Provider | None
    _approval_provider: _Reviewer | None
    _timeout: float
    _review_timeout: float

    def __repr__(self) -> str:
        return f"MCPClientToolPolicy(server_id={self.server_id!r}, tool_count={len(self._tools)})"

    @property
    def bindings(self) -> BoundToolCatalog:
        """Return the trusted catalog; remote annotations never create capabilities."""
        return self._bindings

    @property
    def tools(self) -> tuple[Any, ...]:
        """Return copies of the pinned definitions for advertisement to a model."""
        return tuple(tool.model_copy(deep=True) for tool in self._tools)

    async def _discover(self) -> tuple[tuple[Any, ...], str]:
        definitions: list[Any] = []
        payloads: dict[str, Any] = {}
        canonical_size = len(b'{"mcp_client_registry_version":1,"tools":{}}')
        container_items = 0
        cursor: str | None = None
        seen: set[str] = set()
        with self._fail_after(self._timeout):
            for _ in range(MAX_MCP_CLIENT_DISCOVERY_PAGES):
                page = await self._list_tools(
                    params=self._types.PaginatedRequestParams(cursor=cursor)
                )
                if not isinstance(page, self._types.ListToolsResult) or not isinstance(
                    page.tools, list
                ):
                    raise MCPClientIntegrationError("MCP discovery must return ListToolsResult")
                for tool in page.tools:
                    if len(definitions) >= MAX_TOOL_CATALOG_TOOLS:
                        raise MCPClientIntegrationError("MCP discovery exceeds the tool limit")
                    if not isinstance(tool, self._types.Tool):
                        raise MCPClientIntegrationError("MCP discovery contains a non-Tool entry")
                    if not isinstance(tool.name, str) or tool.name in payloads:
                        raise MCPClientIntegrationError(
                            "MCP discovery contains invalid or duplicate names"
                        )
                    entry = {
                        tool.name: tool.model_dump(mode="json", by_alias=True, exclude_none=True)
                    }
                    # The one-key envelope preserves the full registry's depth accounting.
                    validate_context(entry, label="MCP discovery")
                    container_items += _container_items(entry)
                    if container_items > MAX_CONTAINER_ITEMS:
                        raise InputValidationError(
                            "MCP discovery exceeds aggregate container items"
                        )
                    # Count only the new entry (minus its braces, plus a comma after the first).
                    # Streaming retains the aggregate byte bound without re-encoding old tools.
                    next_size = canonical_size - 2 + bool(payloads)
                    for chunk in _canonical_chunks(entry, initial_size=next_size):
                        next_size += len(chunk)
                    canonical_size = next_size
                    payloads.update(entry)
                    definitions.append(tool.model_copy(deep=True))
                cursor = page.next_cursor
                if cursor is None:
                    validate_tool_catalog_registration(self._bindings.catalog, payloads)
                    return tuple(definitions), _digest(
                        {"mcp_client_registry_version": 1, "tools": payloads}
                    )
                if not isinstance(cursor, str) or not 0 < len(cursor) <= 4096 or cursor in seen:
                    raise MCPClientIntegrationError(
                        "MCP discovery returned an invalid or repeated cursor"
                    )
                seen.add(cursor)
        raise MCPClientIntegrationError("MCP discovery exceeds the page limit")

    async def _check_registry(self) -> None:
        _, current = await self._discover()
        if not hmac.compare_digest(current, self.registry_fingerprint):
            raise MCPClientIntegrationError(
                "MCP tool definitions changed; review and rebind the client"
            )

    def _current_facts(self, request: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        actor = _facts(self._actor_provider, label="actor_provider")
        context = _facts(self._context_provider, label="context_provider")
        if "mcp" in context:
            raise InputValidationError("context.mcp is reserved for MCP client request facts")
        context["mcp"] = {
            "server_id": self.server_id,
            "registry_fingerprint": self.registry_fingerprint,
            "meta": request["meta"],
            "input_responses": request["input_responses"],
            "request_state": request["request_state"],
        }
        return actor, context

    def _call_fingerprint(
        self, binding: BoundToolGate, call_id: str, request: dict[str, Any], actor: dict[str, Any]
    ) -> str:
        return _digest(
            {
                "mcp_client_call_version": MCP_CLIENT_ADAPTER_VERSION,
                "server_id": self.server_id,
                "registry_fingerprint": self.registry_fingerprint,
                "gate_fingerprint": binding.fingerprint(call_id, request["arguments"], actor=actor),
                "request": request,
            }
        )

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        read_timeout_seconds: float | None = None,
        progress_callback: Any = None,
        *,
        input_responses: dict[str, Any] | None = None,
        request_state: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> Any:
        """Send at most one authorized round, returning SDK tool/input-required results.

        Continuations must call this method again and obtain fresh authorization.
        This adapter does not drive retries, input resolution or rollback. Existing
        session callbacks and transport behavior remain application responsibilities.
        """
        if not isinstance(name, str) or name not in self._bindings:
            raise MCPClientIntegrationError("MCP tool name is not in the trusted catalog")
        timeout = self._timeout if read_timeout_seconds is None else _seconds(read_timeout_seconds)
        if progress_callback is not None and not callable(progress_callback):
            raise TypeError("progress_callback must be callable")
        request = _copy(
            {
                "arguments": {} if arguments is None else arguments,
                "input_responses": input_responses,
                "request_state": request_state,
                "meta": meta,
            },
            label="MCP client request",
        )
        # Validate transport fields before review; use exactly this normalized representation.
        params = self._request_type.model_validate({"name": name, **request}, strict=True)
        wire = params.model_dump(mode="json", by_alias=False, exclude_none=False)
        request = _copy({key: wire[key] for key in request}, label="MCP client request")
        await self._check_registry()
        binding = self._bindings[name]
        actor, context = self._current_facts(request)
        approval: ToolCallApproval | None = None
        call_id = f"mcp-client:{token_hex(16)}"
        if (
            self._approval_provider is not None
            and binding.explain(request["arguments"], actor=actor, context=context).outcome
            is Outcome.REVIEW
        ):
            review = MCPClientReviewRequest(
                self.server_id,
                name,
                call_id,
                self._call_fingerprint(binding, call_id, request, actor),
                self.registry_fingerprint,
                binding.capabilities,
                binding.policy.id,
                binding.policy.version,
                binding.policy_fingerprint,
                freeze_json_value(request),
            )
            with self._fail_after(self._review_timeout):
                pending = self._approval_provider(review)
                if not inspect.isawaitable(pending):
                    raise MCPClientIntegrationError("approval_provider must return an awaitable")
                approval = await pending
            if approval is not None and not isinstance(approval, ToolCallApproval):
                raise MCPClientIntegrationError(
                    "approval_provider must return ToolCallApproval or None"
                )
            if approval is None or not approval.approved:
                raise MCPClientIntegrationError("MCP client review was rejected or not approved")
            await self._check_registry()
            actor, context = self._current_facts(request)
            if not hmac.compare_digest(call_id, approval.tool_call_id) or not hmac.compare_digest(
                approval.tool_call_fingerprint,
                self._call_fingerprint(binding, call_id, request, actor),
            ):
                raise InputValidationError("MCP client approval does not match the proposed call")
            approval = ToolCallApproval(
                call_id,
                approval.approved,
                binding.fingerprint(call_id, request["arguments"], actor=actor),
            )

        async def send(prepared: dict[str, Any]) -> Any:
            with self._fail_after(timeout):
                return await self._call_tool(
                    name,
                    prepared,
                    read_timeout_seconds=timeout,
                    progress_callback=progress_callback,
                    input_responses=params.input_responses,
                    request_state=params.request_state,
                    meta=params.meta,
                    allow_input_required=True,
                    allow_claimed=False,
                )

        result = await binding.execute_async(
            request["arguments"],
            send,
            actor=actor,
            context=context,
            tool_call_id=call_id if approval is not None else None,
            approval=approval,
        )
        return result.value


async def create_mcp_client_tool_policy(
    bindings: BoundToolCatalog,
    client: Any,
    *,
    server_id: str,
    actor_provider: _Provider | None = None,
    context_provider: _Provider | None = None,
    approval_provider: _Reviewer | None = None,
    timeout_seconds: float = 30.0,
    review_timeout_seconds: float = 300.0,
) -> MCPClientToolPolicy:
    """Discover and pin a complete registry on an already connected MCP 2.1.1 Client.

    server_id is an application-assigned identity, not a server-supplied trust assertion.
    The application retains transport/authentication, connection lifecycle and callback ownership.
    """
    if not isinstance(bindings, BoundToolCatalog):
        raise TypeError("bindings must be a BoundToolCatalog")
    if not isinstance(server_id, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", server_id
    ):
        raise ValueError("server_id must be a 1-128 character application-owned identifier")
    timeout = _seconds(timeout_seconds)
    review_timeout = _seconds(review_timeout_seconds)
    for label, provider in (
        ("actor_provider", actor_provider),
        ("context_provider", context_provider),
        ("approval_provider", approval_provider),
    ):
        if provider is not None and not callable(provider):
            raise TypeError(f"{label} must be callable")
    try:
        sdk = import_module("mcp")
        types = import_module("mcp.types")
        fail_after = import_module("anyio").fail_after
        client_type = sdk.Client
    except (ImportError, AttributeError) as exc:
        raise MCPClientIntegrationError(
            "install 'samsarix-agent-ethics[mcp-client]' in an MCP v2 environment"
        ) from exc
    if not isinstance(client, client_type):
        raise TypeError("client must be a connected MCP v2 Client")
    session = client.session
    # Capture the selected session and bound methods, not a future mutable Client lookup.
    adapter = MCPClientToolPolicy(
        server_id,
        "",
        bindings,
        session,
        session.list_tools,
        session.call_tool,
        types,
        fail_after,
        types.CallToolRequestParams,
        (),
        actor_provider,
        context_provider,
        approval_provider,
        timeout,
        review_timeout,
    )
    definitions, fingerprint = await adapter._discover()
    return replace(adapter, registry_fingerprint=fingerprint, _tools=definitions)
