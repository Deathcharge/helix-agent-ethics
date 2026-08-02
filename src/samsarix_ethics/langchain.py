# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Fail-closed LangChain tool middleware with exact-call review binding."""

from __future__ import annotations

import hmac
import inspect
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from importlib import import_module
from typing import Any, cast

from .approval import TOOL_CALL_APPROVAL_VERSION, ToolCallApproval
from .catalog import MAX_TOOL_CATALOG_TOOLS, validate_tool_catalog_registration
from .errors import SamsarixEthicsError
from .explanation import PolicyExplanation
from .gate import BoundToolCatalog, BoundToolGate
from .models import Outcome
from .validation import freeze_json_value, thaw_json_value, validate_context

LANGCHAIN_ADAPTER_VERSION = 1
LANGCHAIN_REVIEW_INTERRUPT_TYPE = "samsarix.tool_call.review"
_REJECTION_MESSAGE = "Tool call rejected by human review."

_FactsProvider = Callable[[Any], Mapping[str, Any] | None]


class LangChainIntegrationError(SamsarixEthicsError):
    """Raised when LangChain cannot enforce a tool policy safely."""


def _empty_facts(_application_context: Any) -> Mapping[str, Any]:
    return {}


def _validate_provider(provider: _FactsProvider | None, *, label: str) -> _FactsProvider:
    if provider is None:
        return _empty_facts
    if not callable(provider) or inspect.iscoroutinefunction(provider):
        raise TypeError(f"{label} must be a synchronous callable")
    return provider


@dataclass(frozen=True, slots=True)
class _LangChainRequest:
    binding: BoundToolGate
    tool_name: str
    tool_call_id: str
    arguments: dict[str, Any]
    actor: Mapping[str, Any] | None
    context: Mapping[str, Any] | None
    fingerprint: str


@dataclass(frozen=True, slots=True)
class LangChainToolPolicy:
    """Protect one exact LangChain tool registry with Samsarix middleware."""

    _bindings: BoundToolCatalog
    _actor_provider: _FactsProvider
    _context_provider: _FactsProvider
    _request_type: type[Any]
    _base_tool_type: type[Any]
    _tool_message_type: type[Any]
    _interrupt: Callable[[Any], Any]
    _middleware: Any

    @property
    def bindings(self) -> BoundToolCatalog:
        """Return the exact trusted Samsarix catalog bindings."""

        return self._bindings

    @property
    def middleware(self) -> Any:
        """Return the middleware instance to place last in LangChain's middleware list."""

        return self._middleware

    def validate_tools(self, tools: Iterable[Any]) -> tuple[Any, ...]:
        """Require LangChain ``BaseTool`` objects to exactly match the bound catalog."""

        if isinstance(tools, (str, bytes, bytearray)):
            raise TypeError("tools must be an iterable of LangChain BaseTool objects")
        try:
            iterator = iter(tools)
        except TypeError as exc:
            raise TypeError("tools must be an iterable of LangChain BaseTool objects") from exc

        validated: list[Any] = []
        names: list[str] = []
        for index, tool in enumerate(iterator):
            if index >= MAX_TOOL_CATALOG_TOOLS:
                raise LangChainIntegrationError(
                    f"LangChain tools exceed the limit of {MAX_TOOL_CATALOG_TOOLS}"
                )
            if not isinstance(tool, self._base_tool_type):
                raise TypeError(f"tools[{index}] must be a LangChain BaseTool")
            name = getattr(tool, "name", None)
            if not isinstance(name, str):
                raise LangChainIntegrationError("LangChain tool name must be a string")
            validated.append(tool)
            names.append(name)
        validate_tool_catalog_registration(self._bindings.catalog, names)
        return tuple(validated)

    @staticmethod
    def _provider_value(
        provider: _FactsProvider,
        application_context: Any,
        *,
        label: str,
    ) -> Mapping[str, Any] | None:
        value = provider(application_context)
        if value is not None and not isinstance(value, Mapping):
            raise LangChainIntegrationError(f"{label} must return a mapping or None")
        return value

    def _request(self, request: Any) -> _LangChainRequest:
        if not isinstance(request, self._request_type):
            raise TypeError("request must be a LangChain ToolCallRequest")
        tool_call = getattr(request, "tool_call", None)
        if not isinstance(tool_call, Mapping):
            raise LangChainIntegrationError("LangChain tool_call must be a mapping")
        tool_name = tool_call.get("name")
        tool_call_id = tool_call.get("id")
        arguments = tool_call.get("args")
        if not isinstance(tool_name, str):
            raise LangChainIntegrationError("LangChain tool call name must be a string")
        if not isinstance(tool_call_id, str):
            raise LangChainIntegrationError("LangChain tool call ID must be a string")
        if not isinstance(arguments, Mapping):
            raise LangChainIntegrationError("LangChain tool call args must be a mapping")
        try:
            binding = self._bindings[tool_name]
        except KeyError as exc:
            raise LangChainIntegrationError(
                "LangChain tool call is not present in the trusted catalog"
            ) from exc

        tool = getattr(request, "tool", None)
        if not isinstance(tool, self._base_tool_type):
            raise LangChainIntegrationError(
                "LangChain tool call has no registered BaseTool instance"
            )
        if getattr(tool, "name", None) != tool_name:
            raise LangChainIntegrationError(
                "LangChain resolved tool name does not match the requested tool"
            )
        runtime = getattr(request, "runtime", None)
        if runtime is None or not hasattr(runtime, "context"):
            raise LangChainIntegrationError("LangChain tool runtime has no context field")
        application_context = runtime.context
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
        validated_arguments = validate_context(arguments, label="LangChain tool arguments")
        detached_arguments = cast(
            dict[str, Any], thaw_json_value(freeze_json_value(validated_arguments))
        )
        fingerprint = binding.fingerprint(
            tool_call_id,
            detached_arguments,
            actor=actor,
        )
        return _LangChainRequest(
            binding=binding,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            arguments=detached_arguments,
            actor=actor,
            context=context,
            fingerprint=fingerprint,
        )

    def explain(self, request: Any) -> PolicyExplanation:
        """Explain one final LangChain request without emitting an audit record."""

        value = self._request(request)
        return value.binding.explain(
            value.arguments,
            actor=value.actor,
            context=value.context,
        )

    def approval_for(self, request: Any, *, approved: bool) -> ToolCallApproval:
        """Build unsigned exact-call evidence after caller-owned reviewer authentication."""

        value = self._request(request)
        return ToolCallApproval(
            tool_call_id=value.tool_call_id,
            approved=approved,
            tool_call_fingerprint=value.fingerprint,
        )

    @staticmethod
    def _review_payload(
        value: _LangChainRequest,
        explanation: PolicyExplanation,
    ) -> dict[str, Any]:
        return {
            "type": LANGCHAIN_REVIEW_INTERRUPT_TYPE,
            "adapter_version": LANGCHAIN_ADAPTER_VERSION,
            "approval_binding": {
                "approval_version": TOOL_CALL_APPROVAL_VERSION,
                "tool_call_id": value.tool_call_id,
                "tool_call_fingerprint": value.fingerprint,
            },
            "tool": {
                "name": value.tool_name,
                "arguments": value.arguments,
            },
            "policy": {
                "id": explanation.policy_id,
                "version": explanation.policy_version,
                "fingerprint": explanation.policy_fingerprint,
                "decisive_rule_ids": list(explanation.decisive_rule_ids),
            },
        }

    @staticmethod
    def _verify_response(
        value: _LangChainRequest,
        response: Any,
    ) -> ToolCallApproval:
        approval = ToolCallApproval.from_dict(response)
        if not hmac.compare_digest(
            value.tool_call_id.encode("utf-8"), approval.tool_call_id.encode("utf-8")
        ) or not hmac.compare_digest(
            value.fingerprint.encode("utf-8"),
            approval.tool_call_fingerprint.encode("utf-8"),
        ):
            raise LangChainIntegrationError(
                "LangChain review response does not match the interrupted tool call"
            )
        return approval

    def _authorize(self, request: Any) -> tuple[_LangChainRequest, bool]:
        value = self._request(request)
        explanation = value.binding.explain(
            value.arguments,
            actor=value.actor,
            context=value.context,
        )
        approval: ToolCallApproval | None = None
        if explanation.outcome is Outcome.REVIEW:
            response = self._interrupt(self._review_payload(value, explanation))
            approval = self._verify_response(value, response)
            if not approval.approved:
                return value, False
        value.binding.enforce(
            value.arguments,
            actor=value.actor,
            context=value.context,
            tool_call_id=value.tool_call_id if approval is not None else None,
            approval=approval,
        )
        return value, True

    def _rejection(self, value: _LangChainRequest) -> Any:
        return self._tool_message_type(
            content=_REJECTION_MESSAGE,
            tool_call_id=value.tool_call_id,
            name=value.tool_name,
            status="error",
        )

    def _wrap_tool_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        value, authorized = self._authorize(request)
        if not authorized:
            return self._rejection(value)
        return handler(request)

    async def _awrap_tool_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        value, authorized = self._authorize(request)
        if not authorized:
            return self._rejection(value)
        return await handler(request)


def create_langchain_tool_policy(
    bindings: BoundToolCatalog,
    *,
    actor_provider: _FactsProvider | None = None,
    context_provider: _FactsProvider | None = None,
) -> LangChainToolPolicy:
    """Create exact-registry middleware without making LangChain a core dependency."""

    if not isinstance(bindings, BoundToolCatalog):
        raise TypeError("bindings must be a BoundToolCatalog")
    actor = _validate_provider(actor_provider, label="actor_provider")
    context = _validate_provider(context_provider, label="context_provider")
    try:
        middleware_module = import_module("langchain.agents.middleware")
        messages_module = import_module("langchain.messages")
        tools_module = import_module("langchain.tools")
        langgraph_types = import_module("langgraph.types")
        agent_middleware_type = middleware_module.AgentMiddleware
        request_type = middleware_module.ToolCallRequest
        tool_message_type = messages_module.ToolMessage
        base_tool_type = tools_module.BaseTool
        interrupt = langgraph_types.interrupt
    except (AttributeError, ImportError) as exc:
        raise LangChainIntegrationError(
            "install the compatible LangChain runtime with 'samsarix-agent-ethics[langchain]'"
        ) from exc
    if not all(
        isinstance(value, type)
        for value in (agent_middleware_type, request_type, tool_message_type, base_tool_type)
    ) or not callable(interrupt):
        raise LangChainIntegrationError("LangChain runtime has an incompatible API shape")

    policy: LangChainToolPolicy

    def wrap_tool_call(_middleware: Any, request: Any, handler: Callable[[Any], Any]) -> Any:
        return policy._wrap_tool_call(request, handler)

    async def awrap_tool_call(
        _middleware: Any,
        request: Any,
        handler: Callable[[Any], Any],
    ) -> Any:
        return await policy._awrap_tool_call(request, handler)

    concrete_middleware_type = type(
        "SamsarixLangChainToolMiddleware",
        (agent_middleware_type,),
        {
            "wrap_tool_call": wrap_tool_call,
            "awrap_tool_call": awrap_tool_call,
            "__module__": __name__,
        },
    )
    middleware = concrete_middleware_type()
    policy = LangChainToolPolicy(
        _bindings=bindings,
        _actor_provider=actor,
        _context_provider=context,
        _request_type=cast(type[Any], request_type),
        _base_tool_type=cast(type[Any], base_tool_type),
        _tool_message_type=cast(type[Any], tool_message_type),
        _interrupt=cast(Callable[[Any], Any], interrupt),
        _middleware=middleware,
    )
    return policy
