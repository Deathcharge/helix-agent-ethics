# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Fail-closed MCP Python SDK server tool-call integration."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from importlib import import_module
from secrets import token_hex
from typing import Any, cast

from .approval import ToolCallApproval
from .catalog import MAX_TOOL_CATALOG_TOOLS, validate_tool_catalog_registration
from .errors import SamsarixEthicsError
from .gate import BoundToolCatalog, BoundToolGate
from .models import Outcome
from .validation import freeze_json_value, thaw_json_value, validate_context

MCP_SERVER_ADAPTER_VERSION = 1

_FactsProvider = Callable[[Any], Mapping[str, Any] | None]
_ApplicationContextProvider = Callable[[], Any]
_ToolHandler = Callable[[str, dict[str, Any]], Awaitable[Any]]
_ApprovalProvider = Callable[[Any, "MCPToolReviewRequest"], Awaitable[ToolCallApproval | None]]


class MCPServerIntegrationError(SamsarixEthicsError):
    """Raised when an MCP server tool call cannot be protected safely."""


def _empty_facts(_application_context: Any) -> Mapping[str, Any]:
    return {}


def _empty_application_context() -> None:
    return None


def _validate_provider(provider: _FactsProvider | None, *, label: str) -> _FactsProvider:
    if provider is None:
        return _empty_facts
    if not callable(provider) or inspect.iscoroutinefunction(provider):
        raise TypeError(f"{label} must be a synchronous callable")
    return provider


@dataclass(frozen=True, slots=True, repr=False)
class MCPToolReviewRequest:
    """Detached exact-call information for an application-owned MCP reviewer."""

    tool_name: str
    tool_call_id: str
    tool_call_fingerprint: str
    capabilities: tuple[str, ...]
    policy_id: str
    policy_version: str
    policy_fingerprint: str
    _arguments: Any = field(repr=False)

    def __repr__(self) -> str:
        """Return identity metadata without proposed arguments or capabilities."""

        return (
            f"MCPToolReviewRequest(tool_name={self.tool_name!r}, "
            f"tool_call_id={self.tool_call_id!r}, policy_id={self.policy_id!r})"
        )

    @property
    def arguments(self) -> dict[str, Any]:
        """Return a detached copy of the proposed arguments for trusted review UI."""

        return cast(dict[str, Any], thaw_json_value(self._arguments))

    def approval(self, *, approved: bool) -> ToolCallApproval:
        """Build unsigned evidence after application-owned reviewer authorization."""

        return ToolCallApproval(
            tool_call_id=self.tool_call_id,
            approved=approved,
            tool_call_fingerprint=self.tool_call_fingerprint,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the complete sensitive review payload for a trusted application."""

        return {
            "adapter_version": MCP_SERVER_ADAPTER_VERSION,
            "approval_binding": {
                "tool_call_id": self.tool_call_id,
                "tool_call_fingerprint": self.tool_call_fingerprint,
            },
            "tool": {
                "name": self.tool_name,
                "arguments": self.arguments,
                "capabilities": list(self.capabilities),
            },
            "policy": {
                "id": self.policy_id,
                "version": self.policy_version,
                "fingerprint": self.policy_fingerprint,
            },
        }


@dataclass(frozen=True, slots=True)
class MCPServerToolPolicy:
    """Protect one exact stable MCP Python SDK server tool registry."""

    _bindings: BoundToolCatalog
    _tools: tuple[Any, ...]
    _tool_handler: _ToolHandler
    _application_context_provider: _ApplicationContextProvider
    _actor_provider: _FactsProvider
    _context_provider: _FactsProvider
    _approval_provider: _ApprovalProvider | None

    @property
    def bindings(self) -> BoundToolCatalog:
        """Return the exact trusted Samsarix catalog bindings."""

        return self._bindings

    @property
    def tool_names(self) -> tuple[str, ...]:
        """Return the exact MCP tool names in advertised order."""

        return tuple(cast(str, tool.name) for tool in self._tools)

    @property
    def tools(self) -> tuple[Any, ...]:
        """Return fresh deep copies of the validated MCP tool definitions."""

        return tuple(tool.model_copy(deep=True) for tool in self._tools)

    @staticmethod
    def _provider_value(
        provider: _FactsProvider,
        application_context: Any,
        *,
        label: str,
    ) -> Mapping[str, Any] | None:
        value = provider(application_context)
        if inspect.isawaitable(value):
            if inspect.iscoroutine(value):
                value.close()
            raise MCPServerIntegrationError(f"{label} must return synchronously")
        if value is not None and not isinstance(value, Mapping):
            raise MCPServerIntegrationError(f"{label} must return a mapping or None")
        return value

    def _application_context(self) -> Any:
        try:
            value = self._application_context_provider()
        except LookupError as exc:
            raise MCPServerIntegrationError(
                "MCP application context is unavailable outside a server request"
            ) from exc
        if inspect.isawaitable(value):
            if inspect.iscoroutine(value):
                value.close()
            raise MCPServerIntegrationError(
                "application_context_provider must return synchronously"
            )
        return value

    @staticmethod
    def _review_request(
        binding: BoundToolGate,
        arguments: dict[str, Any],
        actor: Mapping[str, Any] | None,
        tool_call_id: str,
    ) -> MCPToolReviewRequest:
        return MCPToolReviewRequest(
            tool_name=binding.tool_name,
            tool_call_id=tool_call_id,
            tool_call_fingerprint=binding.fingerprint(
                tool_call_id,
                arguments,
                actor=actor,
            ),
            capabilities=binding.capabilities,
            policy_id=binding.policy.id,
            policy_version=binding.policy.version,
            policy_fingerprint=binding.policy_fingerprint,
            _arguments=freeze_json_value(arguments),
        )

    async def _approval(
        self,
        binding: BoundToolGate,
        arguments: dict[str, Any],
        actor: Mapping[str, Any] | None,
        context: Mapping[str, Any] | None,
        application_context: Any,
        tool_call_id: str,
    ) -> ToolCallApproval | None:
        if self._approval_provider is None:
            return None
        explanation = binding.explain(
            arguments,
            actor=actor,
            context=context,
        )
        if explanation.outcome is not Outcome.REVIEW:
            return None
        review = self._review_request(binding, arguments, actor, tool_call_id)
        pending = self._approval_provider(application_context, review)
        if not inspect.isawaitable(pending):
            raise MCPServerIntegrationError("approval_provider must return an awaitable")
        approval = await pending
        if approval is not None and not isinstance(approval, ToolCallApproval):
            raise MCPServerIntegrationError(
                "approval_provider must return ToolCallApproval or None"
            )
        return approval

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Authorize and invoke the bound MCP tool handler exactly once."""

        if not isinstance(tool_name, str):
            raise MCPServerIntegrationError("MCP tool call name must be a string")
        try:
            binding = self._bindings[tool_name]
        except KeyError as exc:
            raise MCPServerIntegrationError(
                "MCP tool call is not present in the trusted catalog"
            ) from exc
        validated_arguments = validate_context(arguments, label="MCP tool arguments")
        detached_arguments = cast(
            dict[str, Any],
            thaw_json_value(freeze_json_value(validated_arguments)),
        )
        application_context = self._application_context()
        actor = self._provider_value(
            self._actor_provider,
            application_context,
            label="actor_provider",
        )
        context = self._provider_value(
            self._context_provider,
            application_context,
            label="context_provider",
        )
        tool_call_id = f"mcp:{token_hex(16)}"
        approval = await self._approval(
            binding,
            detached_arguments,
            actor,
            context,
            application_context,
            tool_call_id,
        )
        if approval is not None:
            application_context = self._application_context()
            actor = self._provider_value(
                self._actor_provider,
                application_context,
                label="actor_provider",
            )
            context = self._provider_value(
                self._context_provider,
                application_context,
                label="context_provider",
            )

        async def execute(prepared_arguments: dict[str, Any]) -> Any:
            result = self._tool_handler(tool_name, prepared_arguments)
            if not inspect.isawaitable(result):
                raise MCPServerIntegrationError("MCP tool_handler must return an awaitable")
            return await result

        execution = await binding.execute_async(
            detached_arguments,
            execute,
            actor=actor,
            context=context,
            tool_call_id=tool_call_id if approval is not None else None,
            approval=approval,
        )
        return execution.value


def create_mcp_server_tool_policy(
    bindings: BoundToolCatalog,
    tools: Iterable[Any],
    tool_handler: _ToolHandler,
    *,
    application_context_provider: _ApplicationContextProvider | None = None,
    actor_provider: _FactsProvider | None = None,
    context_provider: _FactsProvider | None = None,
    approval_provider: _ApprovalProvider | None = None,
) -> MCPServerToolPolicy:
    """Create a stable MCP server adapter without adding a core dependency."""

    if not isinstance(bindings, BoundToolCatalog):
        raise TypeError("bindings must be a BoundToolCatalog")
    if not callable(tool_handler) or not (
        inspect.iscoroutinefunction(tool_handler)
        or inspect.iscoroutinefunction(type(tool_handler).__call__)
    ):
        raise TypeError("tool_handler must be an asynchronous callable")
    application_context = (
        _empty_application_context
        if application_context_provider is None
        else application_context_provider
    )
    if not callable(application_context) or inspect.iscoroutinefunction(application_context):
        raise TypeError("application_context_provider must be a synchronous callable")
    actor = _validate_provider(actor_provider, label="actor_provider")
    context = _validate_provider(context_provider, label="context_provider")
    if approval_provider is not None and not callable(approval_provider):
        raise TypeError("approval_provider must be callable")

    try:
        tool_type = import_module("mcp.types").Tool
    except (AttributeError, ImportError) as exc:
        raise MCPServerIntegrationError(
            "install the compatible MCP Python SDK with 'samsarix-agent-ethics[mcp]'"
        ) from exc

    if isinstance(tools, (str, bytes, bytearray)):
        raise TypeError("tools must be an iterable of MCP Tool objects")
    try:
        iterator = iter(tools)
    except TypeError as exc:
        raise TypeError("tools must be an iterable of MCP Tool objects") from exc

    validated: list[Any] = []
    names: list[str] = []
    for index, tool in enumerate(iterator):
        if index >= MAX_TOOL_CATALOG_TOOLS:
            raise MCPServerIntegrationError(
                f"MCP tools exceed the limit of {MAX_TOOL_CATALOG_TOOLS}"
            )
        if not isinstance(tool, tool_type):
            raise TypeError(f"tools[{index}] must be an MCP Tool")
        name = getattr(tool, "name", None)
        if not isinstance(name, str):
            raise MCPServerIntegrationError("MCP tool name must be a string")
        model_copy = getattr(tool, "model_copy", None)
        if not callable(model_copy):
            raise MCPServerIntegrationError("MCP Tool has no model_copy method")
        validated.append(model_copy(deep=True))
        names.append(name)
    validate_tool_catalog_registration(bindings.catalog, names)

    return MCPServerToolPolicy(
        _bindings=bindings,
        _tools=tuple(validated),
        _tool_handler=tool_handler,
        _application_context_provider=application_context,
        _actor_provider=actor,
        _context_provider=context,
        _approval_provider=approval_provider,
    )
