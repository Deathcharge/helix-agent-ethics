# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Fail-closed OpenAI Agents SDK function-tool integration."""

from __future__ import annotations

import copy
import inspect
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib import import_module
from threading import Lock
from typing import Any, Protocol, cast

from .approval import ToolCallApproval
from .errors import SamsarixEthicsError
from .gate import BoundToolGate
from .io import MAX_INPUT_BYTES, _parse_json
from .models import Outcome

OPENAI_AGENTS_ADAPTER_VERSION = 1
MAX_PENDING_OPENAI_APPROVALS = 4096
_GUARDRAIL_NAME = "samsarix_agent_ethics_v1"
_PROTECTED_MARKER = "_samsarix_agent_ethics_adapter_version"
_FactsProvider = Callable[[Any], Mapping[str, Any] | None]


class OpenAIAgentsApprovalStore(Protocol):
    """Application-owned first-write store for pre-review call fingerprints."""

    def remember(
        self,
        application_context: Any,
        tool_name: str,
        tool_call_id: str,
        tool_call_fingerprint: str,
    ) -> str:
        """Atomically retain and return the first fingerprint for this exact call ID."""

    def get(
        self,
        application_context: Any,
        tool_name: str,
        tool_call_id: str,
    ) -> str | None:
        """Return the retained fingerprint without creating or replacing it."""


class _InMemoryApprovalStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._fingerprints: dict[tuple[str, str], str] = {}

    def remember(
        self,
        _application_context: Any,
        tool_name: str,
        tool_call_id: str,
        tool_call_fingerprint: str,
    ) -> str:
        key = (tool_name, tool_call_id)
        with self._lock:
            existing = self._fingerprints.get(key)
            if existing is not None:
                return existing
            if len(self._fingerprints) >= MAX_PENDING_OPENAI_APPROVALS:
                raise OpenAIAgentsIntegrationError("in-memory OpenAI Agents approval store is full")
            self._fingerprints[key] = tool_call_fingerprint
            return tool_call_fingerprint

    def get(
        self,
        _application_context: Any,
        tool_name: str,
        tool_call_id: str,
    ) -> str | None:
        with self._lock:
            return self._fingerprints.get((tool_name, tool_call_id))


class OpenAIAgentsIntegrationError(SamsarixEthicsError):
    """Raised when an OpenAI Agents SDK tool cannot be protected safely."""


def _empty_facts(_application_context: Any) -> Mapping[str, Any]:
    return {}


def _validate_provider(provider: _FactsProvider | None, *, label: str) -> _FactsProvider:
    if provider is None:
        return _empty_facts
    if not callable(provider) or inspect.iscoroutinefunction(provider):
        raise TypeError(f"{label} must be a synchronous callable")
    return provider


def _application_context(wrapper: Any) -> Any:
    if not hasattr(wrapper, "context"):
        raise OpenAIAgentsIntegrationError("OpenAI Agents context wrapper has no context field")
    return wrapper.context


def _raw_arguments(tool_context: Any) -> dict[str, Any]:
    raw = getattr(tool_context, "tool_arguments", None)
    if not isinstance(raw, str):
        raise OpenAIAgentsIntegrationError(
            "OpenAI Agents tool context has no string tool_arguments field"
        )
    try:
        encoded = raw.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise OpenAIAgentsIntegrationError("OpenAI Agents tool arguments must be UTF-8") from exc
    if len(encoded) > MAX_INPUT_BYTES:
        raise OpenAIAgentsIntegrationError(
            f"OpenAI Agents tool arguments exceed the byte limit of {MAX_INPUT_BYTES}"
        )
    return _parse_json(encoded, label="OpenAI Agents tool arguments")


def _tool_call_id(tool_context: Any) -> str:
    call_id = getattr(tool_context, "tool_call_id", None)
    if not isinstance(call_id, str):
        raise OpenAIAgentsIntegrationError(
            "OpenAI Agents tool context has no string tool_call_id field"
        )
    return call_id


@dataclass(frozen=True, slots=True)
class OpenAIAgentsToolPolicy:
    """Protect one OpenAI Agents SDK ``FunctionTool`` with a bound Samsarix gate."""

    _binding: BoundToolGate
    _actor_provider: _FactsProvider
    _context_provider: _FactsProvider
    _approval_store: OpenAIAgentsApprovalStore
    _function_tool_type: type[Any]
    _input_guardrail: Any
    _output_type: type[Any]

    @property
    def binding(self) -> BoundToolGate:
        """Return the immutable Samsarix tool binding used by this adapter."""

        return self._binding

    def _facts(self, wrapper: Any) -> tuple[Mapping[str, Any] | None, Mapping[str, Any] | None]:
        application_context = _application_context(wrapper)
        return (
            self._actor_provider(application_context),
            self._context_provider(application_context),
        )

    async def _needs_approval(
        self,
        run_context: Any,
        arguments: dict[str, Any],
        tool_call_id: str,
    ) -> bool:
        """Route review outcomes into the SDK workflow without authorizing execution."""

        try:
            actor, context = self._facts(run_context)
            explanation = self._binding.explain(arguments, actor=actor, context=context)
            if explanation.outcome is not Outcome.REVIEW:
                return False
            fingerprint = self._binding.fingerprint(tool_call_id, arguments, actor=actor)
            remembered = self._approval_store.remember(
                _application_context(run_context),
                self._binding.tool_name,
                tool_call_id,
                fingerprint,
            )
        except SamsarixEthicsError:
            return False
        return remembered == fingerprint

    def _sdk_approval(
        self,
        tool_context: Any,
    ) -> ToolCallApproval | None:
        call_id = _tool_call_id(tool_context)
        get_status = getattr(tool_context, "get_approval_status", None)
        if not callable(get_status):
            raise OpenAIAgentsIntegrationError(
                "OpenAI Agents tool context has no get_approval_status method"
            )
        status = get_status(self._binding.tool_name, call_id)
        if status is None:
            return None
        if not isinstance(status, bool):
            raise OpenAIAgentsIntegrationError(
                "OpenAI Agents approval status must be true, false, or null"
            )
        if not status:
            raise OpenAIAgentsIntegrationError("OpenAI Agents approval status is rejected")
        stored_fingerprint = self._approval_store.get(
            _application_context(tool_context),
            self._binding.tool_name,
            call_id,
        )
        if stored_fingerprint is None:
            return None
        return ToolCallApproval(
            tool_call_id=call_id,
            approved=True,
            tool_call_fingerprint=stored_fingerprint,
        )

    async def _guardrail(self, data: Any) -> Any:
        tool_context = getattr(data, "context", None)
        try:
            if tool_context is None:
                raise OpenAIAgentsIntegrationError(
                    "OpenAI Agents guardrail data has no tool context"
                )
            tool_name = getattr(tool_context, "tool_name", None)
            if tool_name != self._binding.tool_name:
                raise OpenAIAgentsIntegrationError(
                    "OpenAI Agents tool name does not match the Samsarix binding"
                )
            if getattr(tool_context, "tool_namespace", None) is not None:
                raise OpenAIAgentsIntegrationError(
                    "namespaced OpenAI Agents function tools are not supported"
                )
            arguments = _raw_arguments(tool_context)
            actor, context = self._facts(tool_context)
            approval = self._sdk_approval(tool_context)
            self._binding.enforce(
                arguments,
                actor=actor,
                context=context,
                tool_call_id=_tool_call_id(tool_context) if approval is not None else None,
                approval=approval,
            )
        except SamsarixEthicsError:
            return self._output_type.raise_exception(
                {"adapter": "samsarix-agent-ethics", "status": "blocked"}
            )
        return self._output_type.allow({"adapter": "samsarix-agent-ethics", "status": "allowed"})

    async def _combined_needs_approval(
        self,
        existing: Any,
        run_context: Any,
        arguments: dict[str, Any],
        tool_call_id: str,
    ) -> bool:
        if isinstance(existing, bool):
            existing_result = existing
        elif callable(existing):
            existing_value = existing(run_context, arguments, tool_call_id)
            existing_result = (
                bool(await existing_value)
                if inspect.isawaitable(existing_value)
                else bool(existing_value)
            )
        else:
            raise OpenAIAgentsIntegrationError(
                "OpenAI Agents needs_approval must be a boolean or callable"
            )
        samsarix_result = await self._needs_approval(run_context, arguments, tool_call_id)
        return existing_result or samsarix_result

    def protect(self, tool: Any) -> Any:
        """Return a protected copy of one strict, top-level SDK ``FunctionTool``."""

        if not isinstance(tool, self._function_tool_type):
            raise TypeError("tool must be an OpenAI Agents SDK FunctionTool")
        if getattr(tool, _PROTECTED_MARKER, None) is not None:
            raise OpenAIAgentsIntegrationError("tool is already protected by Samsarix")
        if getattr(tool, "name", None) != self._binding.tool_name:
            raise OpenAIAgentsIntegrationError(
                "OpenAI Agents tool name does not match the Samsarix binding"
            )
        if getattr(tool, "strict_json_schema", None) is not True:
            raise OpenAIAgentsIntegrationError(
                "OpenAI Agents function tools must use strict_json_schema=True"
            )
        if getattr(tool, "_is_agent_tool", False):
            raise OpenAIAgentsIntegrationError("Agent.as_tool() tools are not supported")
        if getattr(tool, "_tool_namespace", None) is not None:
            raise OpenAIAgentsIntegrationError("namespaced function tools are not supported")

        protected = copy.copy(tool)
        existing_guardrails = getattr(tool, "tool_input_guardrails", None)
        if existing_guardrails is not None and not isinstance(existing_guardrails, list):
            raise OpenAIAgentsIntegrationError("tool_input_guardrails must be a list or null")
        protected.tool_input_guardrails = [*(existing_guardrails or []), self._input_guardrail]
        existing_approval = getattr(tool, "needs_approval", False)

        async def needs_approval(
            run_context: Any,
            arguments: dict[str, Any],
            tool_call_id: str,
        ) -> bool:
            return await self._combined_needs_approval(
                existing_approval, run_context, arguments, tool_call_id
            )

        protected.needs_approval = needs_approval
        setattr(protected, _PROTECTED_MARKER, OPENAI_AGENTS_ADAPTER_VERSION)
        return protected


def create_openai_agents_tool_policy(
    binding: BoundToolGate,
    *,
    actor_provider: _FactsProvider | None = None,
    context_provider: _FactsProvider | None = None,
    approval_store: OpenAIAgentsApprovalStore | None = None,
) -> OpenAIAgentsToolPolicy:
    """Create an adapter without making the OpenAI Agents SDK a core dependency."""

    if not isinstance(binding, BoundToolGate):
        raise TypeError("binding must be a BoundToolGate")
    actor = _validate_provider(actor_provider, label="actor_provider")
    context = _validate_provider(context_provider, label="context_provider")
    selected_store = _InMemoryApprovalStore() if approval_store is None else approval_store
    remember = getattr(selected_store, "remember", None)
    get = getattr(selected_store, "get", None)
    if (
        not callable(remember)
        or not callable(get)
        or inspect.iscoroutinefunction(remember)
        or inspect.iscoroutinefunction(get)
    ):
        raise TypeError("approval_store must provide synchronous remember and get methods")
    try:
        agents_module = import_module("agents")
        guardrails_module = import_module("agents.tool_guardrails")
        function_tool_type = agents_module.FunctionTool
        guardrail_type = guardrails_module.ToolInputGuardrail
        output_type = guardrails_module.ToolGuardrailFunctionOutput
    except (AttributeError, ImportError) as exc:
        raise OpenAIAgentsIntegrationError(
            "install the compatible OpenAI Agents SDK with 'samsarix-agent-ethics[openai-agents]'"
        ) from exc

    adapter: OpenAIAgentsToolPolicy

    async def guardrail(data: Any) -> Any:
        return await adapter._guardrail(data)

    input_guardrail = guardrail_type(guardrail_function=guardrail, name=_GUARDRAIL_NAME)
    adapter = OpenAIAgentsToolPolicy(
        _binding=binding,
        _actor_provider=actor,
        _context_provider=context,
        _approval_store=selected_store,
        _function_tool_type=cast(type[Any], function_tool_type),
        _input_guardrail=input_guardrail,
        _output_type=cast(type[Any], output_type),
    )
    return adapter
