# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Fail-closed Pydantic AI toolset policy and exact-call review bridge."""

from __future__ import annotations

import hmac
import inspect
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib import import_module
from threading import Lock
from typing import Any, Protocol, cast

from .approval import TOOL_CALL_APPROVAL_VERSION, ToolCallApproval
from .catalog import MAX_TOOL_CATALOG_TOOLS, validate_tool_catalog_registration
from .errors import SamsarixEthicsError
from .explanation import PolicyExplanation
from .gate import BoundToolCatalog, BoundToolGate
from .models import Outcome
from .validation import freeze_json_value, thaw_json_value, validate_context

PYDANTIC_AI_ADAPTER_VERSION = 1
PYDANTIC_AI_REVIEW_METADATA_KEY = "samsarix.tool_call.review"
PYDANTIC_AI_APPROVAL_METADATA_KEY = "samsarix.tool_call.approval"
MAX_PENDING_PYDANTIC_AI_APPROVALS = 4096
_REJECTION_MESSAGE = "Tool call rejected by human review."

_FactsProvider = Callable[[Any], Mapping[str, Any] | None]


class PydanticAIIntegrationError(SamsarixEthicsError):
    """Raised when Pydantic AI cannot enforce a tool policy safely."""


class PydanticAIApprovalStore(Protocol):
    """Application-owned first-write and atomic-consume approval state."""

    def remember(
        self,
        tool_name: str,
        tool_call_id: str,
        tool_call_fingerprint: str,
    ) -> str:
        """Atomically retain and return the first fingerprint for this call."""

    def consume(
        self,
        tool_name: str,
        tool_call_id: str,
        tool_call_fingerprint: str,
    ) -> bool:
        """Atomically remove matching state, returning whether it existed."""


class _InMemoryApprovalStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._fingerprints: dict[tuple[str, str], str] = {}

    def remember(
        self,
        tool_name: str,
        tool_call_id: str,
        tool_call_fingerprint: str,
    ) -> str:
        key = (tool_name, tool_call_id)
        with self._lock:
            existing = self._fingerprints.get(key)
            if existing is not None:
                return existing
            if len(self._fingerprints) >= MAX_PENDING_PYDANTIC_AI_APPROVALS:
                raise PydanticAIIntegrationError("in-memory Pydantic AI approval store is full")
            self._fingerprints[key] = tool_call_fingerprint
            return tool_call_fingerprint

    def consume(
        self,
        tool_name: str,
        tool_call_id: str,
        tool_call_fingerprint: str,
    ) -> bool:
        key = (tool_name, tool_call_id)
        with self._lock:
            existing = self._fingerprints.get(key)
            if existing is None or not hmac.compare_digest(
                existing.encode("utf-8"), tool_call_fingerprint.encode("utf-8")
            ):
                return False
            del self._fingerprints[key]
            return True


def _empty_facts(_application_context: Any) -> Mapping[str, Any]:
    return {}


def _validate_provider(provider: _FactsProvider | None, *, label: str) -> _FactsProvider:
    if provider is None:
        return _empty_facts
    if not callable(provider) or inspect.iscoroutinefunction(provider):
        raise TypeError(f"{label} must be a synchronous callable")
    return provider


@dataclass(frozen=True, slots=True)
class _PydanticAICall:
    binding: BoundToolGate
    tool_name: str
    tool_call_id: str
    arguments: dict[str, Any]
    actor: Mapping[str, Any] | None
    context: Mapping[str, Any] | None
    fingerprint: str


@dataclass(frozen=True, slots=True)
class PydanticAIToolPolicy:
    """Protect one exact Pydantic AI toolset registry with Samsarix policy."""

    _bindings: BoundToolCatalog
    _actor_provider: _FactsProvider
    _context_provider: _FactsProvider
    _approval_store: PydanticAIApprovalStore
    _abstract_toolset_type: type[Any]
    _toolset_tool_type: type[Any]
    _run_context_type: type[Any]
    _approval_required_type: type[Any]
    _deferred_requests_type: type[Any]
    _tool_denied_type: type[Any]
    _toolset: Any

    @property
    def bindings(self) -> BoundToolCatalog:
        """Return the exact trusted Samsarix catalog bindings."""

        return self._bindings

    @property
    def toolset(self) -> Any:
        """Return the Pydantic AI wrapper toolset to register on an agent."""

        return self._toolset

    @staticmethod
    def _provider_value(
        provider: _FactsProvider,
        application_context: Any,
        *,
        label: str,
    ) -> Mapping[str, Any] | None:
        value = provider(application_context)
        if value is not None and not isinstance(value, Mapping):
            raise PydanticAIIntegrationError(f"{label} must return a mapping or None")
        return value

    async def _get_tools(self, wrapper: Any, ctx: Any) -> dict[str, Any]:
        if not isinstance(ctx, self._run_context_type):
            raise TypeError("ctx must be a Pydantic AI RunContext")
        tools = await wrapper.wrapped.get_tools(ctx)
        if not isinstance(tools, dict):
            raise PydanticAIIntegrationError("Pydantic AI get_tools must return a dictionary")
        if len(tools) > MAX_TOOL_CATALOG_TOOLS:
            raise PydanticAIIntegrationError(
                f"Pydantic AI tools exceed the limit of {MAX_TOOL_CATALOG_TOOLS}"
            )

        names: list[str] = []
        for name, tool in tools.items():
            if not isinstance(name, str):
                raise PydanticAIIntegrationError("Pydantic AI tool name must be a string")
            if not isinstance(tool, self._toolset_tool_type):
                raise PydanticAIIntegrationError(f"Pydantic AI tool {name!r} is not a ToolsetTool")
            tool_definition = getattr(tool, "tool_def", None)
            if getattr(tool_definition, "name", None) != name:
                raise PydanticAIIntegrationError(
                    "Pydantic AI tool definition name does not match its registry key"
                )
            names.append(name)

        validate_tool_catalog_registration(self._bindings.catalog, names)
        wrapper._samsarix_verified_tools = dict(tools)
        return tools

    def _call(
        self, wrapper: Any, name: Any, tool_args: Any, ctx: Any, tool: Any
    ) -> _PydanticAICall:
        if not isinstance(ctx, self._run_context_type):
            raise TypeError("ctx must be a Pydantic AI RunContext")
        if not isinstance(name, str):
            raise PydanticAIIntegrationError("Pydantic AI tool call name must be a string")
        if not isinstance(tool_args, dict):
            raise PydanticAIIntegrationError("Pydantic AI tool arguments must be a dictionary")
        if not isinstance(tool, self._toolset_tool_type):
            raise PydanticAIIntegrationError("Pydantic AI tool call has no ToolsetTool")
        verified_tools = getattr(wrapper, "_samsarix_verified_tools", None)
        if not isinstance(verified_tools, dict) or verified_tools.get(name) is not tool:
            raise PydanticAIIntegrationError(
                "Pydantic AI tool call does not match the verified run-step registry"
            )
        tool_definition = getattr(tool, "tool_def", None)
        if getattr(tool_definition, "name", None) != name:
            raise PydanticAIIntegrationError(
                "Pydantic AI resolved tool name does not match the requested tool"
            )
        try:
            binding = self._bindings[name]
        except KeyError as exc:
            raise PydanticAIIntegrationError(
                "Pydantic AI tool call is not present in the trusted catalog"
            ) from exc

        tool_call_id = getattr(ctx, "tool_call_id", None)
        if not isinstance(tool_call_id, str):
            raise PydanticAIIntegrationError("Pydantic AI RunContext has no string tool_call_id")
        application_context = getattr(ctx, "deps", None)
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
        validated_arguments = validate_context(tool_args, label="Pydantic AI tool arguments")
        detached_arguments = cast(
            dict[str, Any], thaw_json_value(freeze_json_value(validated_arguments))
        )
        fingerprint = binding.fingerprint(tool_call_id, detached_arguments, actor=actor)
        return _PydanticAICall(
            binding=binding,
            tool_name=name,
            tool_call_id=tool_call_id,
            arguments=detached_arguments,
            actor=actor,
            context=context,
            fingerprint=fingerprint,
        )

    @staticmethod
    def _review_payload(
        value: _PydanticAICall,
        explanation: PolicyExplanation,
    ) -> dict[str, Any]:
        return {
            "type": PYDANTIC_AI_REVIEW_METADATA_KEY,
            "adapter_version": PYDANTIC_AI_ADAPTER_VERSION,
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
    def _verify_approval(value: _PydanticAICall, metadata: Any) -> ToolCallApproval:
        if not isinstance(metadata, Mapping):
            raise PydanticAIIntegrationError(
                "Pydantic AI approved call has no Samsarix approval metadata"
            )
        approval = ToolCallApproval.from_dict(metadata.get(PYDANTIC_AI_APPROVAL_METADATA_KEY))
        if not approval.approved:
            raise PydanticAIIntegrationError(
                "Pydantic AI approved call carries rejected Samsarix evidence"
            )
        if not hmac.compare_digest(
            value.tool_call_id.encode("utf-8"), approval.tool_call_id.encode("utf-8")
        ) or not hmac.compare_digest(
            value.fingerprint.encode("utf-8"),
            approval.tool_call_fingerprint.encode("utf-8"),
        ):
            raise PydanticAIIntegrationError(
                "Pydantic AI approval does not match the current tool call"
            )
        return approval

    async def _call_tool(
        self,
        wrapper: Any,
        name: Any,
        tool_args: Any,
        ctx: Any,
        tool: Any,
    ) -> Any:
        value = self._call(wrapper, name, tool_args, ctx, tool)
        explanation = value.binding.explain(
            value.arguments,
            actor=value.actor,
            context=value.context,
        )
        approval: ToolCallApproval | None = None
        if explanation.outcome is Outcome.REVIEW:
            approved = getattr(ctx, "tool_call_approved", None)
            if not isinstance(approved, bool):
                raise PydanticAIIntegrationError(
                    "Pydantic AI RunContext tool_call_approved must be a boolean"
                )
            if not approved:
                raise self._approval_required_type(
                    metadata={
                        PYDANTIC_AI_REVIEW_METADATA_KEY: self._review_payload(value, explanation)
                    }
                )
            approval = self._verify_approval(value, getattr(ctx, "tool_call_metadata", None))
            if not self._approval_store.consume(
                value.tool_name,
                value.tool_call_id,
                value.fingerprint,
            ):
                raise PydanticAIIntegrationError(
                    "Pydantic AI approval is missing, already consumed, or does not match"
                )

        value.binding.enforce(
            value.arguments,
            actor=value.actor,
            context=value.context,
            tool_call_id=value.tool_call_id if approval is not None else None,
            approval=approval,
        )
        return await wrapper.wrapped.call_tool(
            value.tool_name,
            value.arguments,
            ctx,
            tool,
        )

    def build_results(self, requests: Any, decisions: Mapping[str, bool]) -> Any:
        """Build exact-call Pydantic AI results after caller-owned reviewer authentication."""

        if not isinstance(requests, self._deferred_requests_type):
            raise TypeError("requests must be Pydantic AI DeferredToolRequests")
        if not isinstance(decisions, Mapping):
            raise TypeError("decisions must be a mapping of tool call IDs to booleans")
        if len(decisions) > MAX_TOOL_CATALOG_TOOLS:
            raise PydanticAIIntegrationError(
                f"Pydantic AI decisions exceed the limit of {MAX_TOOL_CATALOG_TOOLS}"
            )

        approvals = getattr(requests, "approvals", None)
        if not isinstance(approvals, list):
            raise PydanticAIIntegrationError("Pydantic AI deferred approvals must be a list")
        if len(approvals) > MAX_TOOL_CATALOG_TOOLS:
            raise PydanticAIIntegrationError(
                f"Pydantic AI deferred approvals exceed the limit of {MAX_TOOL_CATALOG_TOOLS}"
            )
        pending: dict[str, Any] = {}
        for call in approvals:
            call_id = getattr(call, "tool_call_id", None)
            if not isinstance(call_id, str):
                raise PydanticAIIntegrationError(
                    "Pydantic AI deferred approval has no string tool_call_id"
                )
            if call_id in pending:
                raise PydanticAIIntegrationError(
                    "Pydantic AI deferred approvals contain a duplicate tool call ID"
                )
            pending[call_id] = call

        results: dict[str, Any] = {}
        metadata: dict[str, dict[str, Any]] = {}
        request_metadata = getattr(requests, "metadata", None)
        if not isinstance(request_metadata, Mapping):
            raise PydanticAIIntegrationError(
                "Pydantic AI deferred requests metadata must be a mapping"
            )
        for call_id, approved in decisions.items():
            if not isinstance(call_id, str):
                raise PydanticAIIntegrationError(
                    "Pydantic AI decision tool call ID must be a string"
                )
            if type(approved) is not bool:
                raise PydanticAIIntegrationError("Pydantic AI review decision must be a boolean")
            try:
                call = pending[call_id]
            except KeyError as exc:
                raise PydanticAIIntegrationError(
                    "Pydantic AI decision does not identify a pending approval"
                ) from exc
            per_call_metadata = request_metadata.get(call_id)
            if not isinstance(per_call_metadata, Mapping):
                raise PydanticAIIntegrationError(
                    "Pydantic AI pending approval has no Samsarix review metadata"
                )
            payload = per_call_metadata.get(PYDANTIC_AI_REVIEW_METADATA_KEY)
            approval = self._approval_from_payload(call, payload, approved=approved)
            if approved:
                remembered = self._approval_store.remember(
                    cast(str, getattr(call, "tool_name", None)),
                    call_id,
                    approval.tool_call_fingerprint,
                )
                if not hmac.compare_digest(
                    remembered.encode("utf-8"),
                    approval.tool_call_fingerprint.encode("utf-8"),
                ):
                    raise PydanticAIIntegrationError(
                        "Pydantic AI approval store contains different call evidence"
                    )
                results[call_id] = True
                metadata[call_id] = {PYDANTIC_AI_APPROVAL_METADATA_KEY: approval.to_dict()}
            else:
                results[call_id] = self._tool_denied_type(_REJECTION_MESSAGE)

        build_results = getattr(requests, "build_results", None)
        if not callable(build_results):
            raise PydanticAIIntegrationError(
                "Pydantic AI DeferredToolRequests has no build_results method"
            )
        return build_results(approvals=results, metadata=metadata)

    def _approval_from_payload(
        self, call: Any, payload: Any, *, approved: bool
    ) -> ToolCallApproval:
        if not isinstance(payload, Mapping):
            raise PydanticAIIntegrationError(
                "Pydantic AI pending approval has malformed Samsarix review metadata"
            )
        if payload.get("type") != PYDANTIC_AI_REVIEW_METADATA_KEY:
            raise PydanticAIIntegrationError("Pydantic AI review metadata type is incompatible")
        if payload.get("adapter_version") != PYDANTIC_AI_ADAPTER_VERSION:
            raise PydanticAIIntegrationError("Pydantic AI review metadata version is incompatible")
        binding = payload.get("approval_binding")
        tool_payload = payload.get("tool")
        if not isinstance(binding, Mapping) or not isinstance(tool_payload, Mapping):
            raise PydanticAIIntegrationError("Pydantic AI review metadata is malformed")
        call_id = getattr(call, "tool_call_id", None)
        tool_name = getattr(call, "tool_name", None)
        args_as_dict = getattr(call, "args_as_dict", None)
        if not callable(args_as_dict):
            raise PydanticAIIntegrationError(
                "Pydantic AI deferred approval has no args_as_dict method"
            )
        try:
            arguments = args_as_dict()
        except (TypeError, ValueError) as exc:
            raise PydanticAIIntegrationError(
                "Pydantic AI deferred approval arguments are malformed"
            ) from exc
        if not isinstance(arguments, dict):
            raise PydanticAIIntegrationError(
                "Pydantic AI deferred approval arguments must be a dictionary"
            )
        arguments = validate_context(
            arguments,
            label="Pydantic AI deferred approval arguments",
        )
        if binding.get("tool_call_id") != call_id:
            raise PydanticAIIntegrationError(
                "Pydantic AI review metadata call ID does not match the pending call"
            )
        if tool_payload.get("name") != tool_name or tool_payload.get("arguments") != arguments:
            raise PydanticAIIntegrationError(
                "Pydantic AI review metadata tool call does not match the pending call"
            )
        try:
            self._bindings[cast(str, tool_name)]
        except (KeyError, TypeError) as exc:
            raise PydanticAIIntegrationError(
                "Pydantic AI pending approval is not present in the trusted catalog"
            ) from exc
        return ToolCallApproval.from_dict({**binding, "approved": approved})


def create_pydantic_ai_tool_policy(
    bindings: BoundToolCatalog,
    toolset: Any,
    *,
    actor_provider: _FactsProvider | None = None,
    context_provider: _FactsProvider | None = None,
    approval_store: PydanticAIApprovalStore | None = None,
) -> PydanticAIToolPolicy:
    """Wrap one exact Pydantic AI toolset without adding a core dependency."""

    if not isinstance(bindings, BoundToolCatalog):
        raise TypeError("bindings must be a BoundToolCatalog")
    actor = _validate_provider(actor_provider, label="actor_provider")
    context = _validate_provider(context_provider, label="context_provider")
    selected_store: PydanticAIApprovalStore = (
        _InMemoryApprovalStore() if approval_store is None else approval_store
    )
    remember = getattr(selected_store, "remember", None)
    consume = getattr(selected_store, "consume", None)
    if (
        not callable(remember)
        or inspect.iscoroutinefunction(remember)
        or not callable(consume)
        or inspect.iscoroutinefunction(consume)
    ):
        raise TypeError("approval_store must define synchronous remember and consume methods")
    try:
        pydantic_ai = import_module("pydantic_ai")
        abstract_toolset_type = pydantic_ai.AbstractToolset
        wrapper_toolset_type = pydantic_ai.WrapperToolset
        toolset_tool_type = pydantic_ai.ToolsetTool
        run_context_type = pydantic_ai.RunContext
        approval_required_type = pydantic_ai.ApprovalRequired
        deferred_requests_type = pydantic_ai.DeferredToolRequests
        tool_denied_type = pydantic_ai.ToolDenied
    except (AttributeError, ImportError) as exc:
        raise PydanticAIIntegrationError(
            "install the compatible Pydantic AI runtime with 'samsarix-agent-ethics[pydantic-ai]'"
        ) from exc
    runtime_types = (
        abstract_toolset_type,
        wrapper_toolset_type,
        toolset_tool_type,
        run_context_type,
        approval_required_type,
        deferred_requests_type,
        tool_denied_type,
    )
    if not all(isinstance(value, type) for value in runtime_types):
        raise PydanticAIIntegrationError("Pydantic AI runtime has an incompatible API shape")
    if not issubclass(approval_required_type, BaseException):
        raise PydanticAIIntegrationError("Pydantic AI ApprovalRequired is not an exception type")
    if not isinstance(toolset, abstract_toolset_type):
        raise TypeError("toolset must be a Pydantic AI AbstractToolset")

    policy: PydanticAIToolPolicy

    def initialize(wrapper: Any, wrapped: Any) -> None:
        wrapper_toolset_type.__init__(wrapper, wrapped)
        wrapper._samsarix_verified_tools = {}

    async def for_run(wrapper: Any, ctx: Any) -> Any:
        if not isinstance(ctx, run_context_type):
            raise TypeError("ctx must be a Pydantic AI RunContext")
        wrapped = await wrapper.wrapped.for_run(ctx)
        if not isinstance(wrapped, abstract_toolset_type):
            raise PydanticAIIntegrationError(
                "Pydantic AI toolset for_run returned an incompatible value"
            )
        return type(wrapper)(wrapped)

    async def get_tools(wrapper: Any, ctx: Any) -> dict[str, Any]:
        return await policy._get_tools(wrapper, ctx)

    async def call_tool(
        wrapper: Any,
        name: Any,
        tool_args: Any,
        ctx: Any,
        tool: Any,
    ) -> Any:
        return await policy._call_tool(wrapper, name, tool_args, ctx, tool)

    concrete_toolset_type = type(
        "SamsarixPydanticAIToolset",
        (wrapper_toolset_type,),
        {
            "__init__": initialize,
            "for_run": for_run,
            "get_tools": get_tools,
            "call_tool": call_tool,
            "__module__": __name__,
        },
    )
    protected_toolset = concrete_toolset_type(toolset)
    policy = PydanticAIToolPolicy(
        _bindings=bindings,
        _actor_provider=actor,
        _context_provider=context,
        _approval_store=selected_store,
        _abstract_toolset_type=cast(type[Any], abstract_toolset_type),
        _toolset_tool_type=cast(type[Any], toolset_tool_type),
        _run_context_type=cast(type[Any], run_context_type),
        _approval_required_type=cast(type[Any], approval_required_type),
        _deferred_requests_type=cast(type[Any], deferred_requests_type),
        _tool_denied_type=cast(type[Any], tool_denied_type),
        _toolset=protected_toolset,
    )
    return policy
