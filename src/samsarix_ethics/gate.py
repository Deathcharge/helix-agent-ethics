# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Fail-closed policy enforcement for in-process agent tool calls."""

from __future__ import annotations

import hmac
import inspect
import re
from collections.abc import Awaitable, Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Generic, TypeVar, cast

from .approval import ToolCallApproval, _fingerprint_prepared_tool_call
from .audit import AuditSink, JsonlAuditSink, _emit_audit_record, _validated_sink
from .catalog import ToolCatalog, validate_tool_catalog_registration
from .contracts import ContextContract
from .deployment import DeploymentLock
from .engine import MAX_BATCH_ITEMS, PolicyEngine
from .errors import InputValidationError, ToolCallDeniedError, ToolCallReviewRequiredError
from .explanation import PolicyExplanation
from .models import Decision, Outcome, Policy
from .provenance import fingerprint_tool_catalog
from .runtime import PolicyRuntime, PolicyRuntimeStatus
from .validation import freeze_json_value, thaw_json_value, validate_context

MAX_TOOL_CAPABILITIES = 64
MAX_TOOL_BATCH_ITEMS = MAX_BATCH_ITEMS
TOOL_CONTEXT_VERSION = 1
_TOOL_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_ResultT = TypeVar("_ResultT")


def _json_object(value: Mapping[str, Any], *, label: str) -> dict[str, Any]:
    validated = validate_context(value, label=label)
    return cast(dict[str, Any], thaw_json_value(validated))


def _capability_list(capabilities: Iterable[str]) -> list[str]:
    if isinstance(capabilities, (str, bytes, bytearray)):
        raise InputValidationError("tool capabilities must be an iterable of identifiers")
    try:
        iterator = iter(capabilities)
    except TypeError as exc:
        raise InputValidationError("tool capabilities must be iterable") from exc

    values: list[str] = []
    for index, capability in enumerate(iterator):
        if index >= MAX_TOOL_CAPABILITIES:
            raise InputValidationError(
                f"tool capabilities exceed the limit of {MAX_TOOL_CAPABILITIES}"
            )
        if not isinstance(capability, str) or not _TOOL_IDENTIFIER.fullmatch(capability):
            raise InputValidationError(
                f"tool capabilities[{index}] must be a 1-128 character identifier"
            )
        values.append(capability)
    if len(set(values)) != len(values):
        raise InputValidationError("tool capabilities must not contain duplicates")
    return sorted(values)


def _prepare_tool_call(
    tool_name: str,
    arguments: Mapping[str, Any],
    *,
    capabilities: Iterable[str],
    actor: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(tool_name, str) or not _TOOL_IDENTIFIER.fullmatch(tool_name):
        raise InputValidationError("tool name must be a 1-128 character identifier")
    arguments_value = _json_object(arguments, label="tool arguments")
    actor_value = _json_object({} if actor is None else actor, label="tool actor")
    action = {
        "kind": "tool_call",
        "operation": tool_name,
        "capabilities": _capability_list(capabilities),
        "arguments": arguments_value,
    }
    return actor_value, action


def fingerprint_tool_call(
    tool_call_id: str,
    tool_name: str,
    arguments: Mapping[str, Any],
    *,
    capabilities: Iterable[str] = (),
    actor: Mapping[str, Any] | None = None,
) -> str:
    """Return a bounded v1 fingerprint for one exact normalized tool call."""

    actor_value, action = _prepare_tool_call(
        tool_name,
        arguments,
        capabilities=capabilities,
        actor=actor,
    )
    return _fingerprint_prepared_tool_call(
        tool_call_id,
        tool_context_version=TOOL_CONTEXT_VERSION,
        actor=actor_value,
        action=action,
    )


def build_tool_context(
    tool_name: str,
    arguments: Mapping[str, Any],
    *,
    capabilities: Iterable[str] = (),
    actor: Mapping[str, Any] | None = None,
    context: Mapping[str, Any] | None = None,
    tool_call_id: str | None = None,
    approval: ToolCallApproval | None = None,
) -> dict[str, Any]:
    """Build a validated, detached policy context for one proposed tool call."""

    actor_value, action = _prepare_tool_call(
        tool_name,
        arguments,
        capabilities=capabilities,
        actor=actor,
    )
    context_value = _json_object({} if context is None else context, label="tool context")
    if "approval" in context_value:
        raise InputValidationError(
            "tool context field 'approval' is reserved; use the approval argument"
        )
    if approval is None and tool_call_id is not None:
        raise InputValidationError("tool_call_id requires a tool-call approval")
    if approval is not None:
        if not isinstance(approval, ToolCallApproval):
            raise TypeError("approval must be a ToolCallApproval")
        if tool_call_id is None:
            raise InputValidationError("tool_call_id is required with a tool-call approval")
        current_fingerprint = _fingerprint_prepared_tool_call(
            tool_call_id,
            tool_context_version=TOOL_CONTEXT_VERSION,
            actor=actor_value,
            action=action,
        )
        call_id_matches = hmac.compare_digest(tool_call_id, approval.tool_call_id)
        fingerprint_matches = hmac.compare_digest(
            current_fingerprint, approval.tool_call_fingerprint
        )
        if not call_id_matches or not fingerprint_matches:
            raise InputValidationError("tool-call approval does not match the proposed tool call")
        context_value["approval"] = approval.to_dict()
    value = {
        "tool_context_version": TOOL_CONTEXT_VERSION,
        "actor": actor_value,
        "action": action,
        "context": context_value,
    }
    validate_context(value, label="tool-call policy context")
    return value


@dataclass(frozen=True, slots=True)
class ToolExecutionResult(Generic[_ResultT]):
    """An allowed tool result paired with the decision that authorized it."""

    decision: Decision
    value: _ResultT


@dataclass(frozen=True, slots=True, init=False, eq=False, repr=False)
class PreparedToolCall:
    """One immutable normalized call prepared by its enforcing ``ToolGate``."""

    _gate: ToolGate
    _context: Mapping[str, Any]

    def __init__(self) -> None:
        raise TypeError("PreparedToolCall objects are created by ToolGate.prepare")

    def __repr__(self) -> str:
        """Return registered metadata without arguments, actor, context, or approval."""

        return f"PreparedToolCall(tool_name={self.tool_name!r}, capabilities={self.capabilities!r})"

    @classmethod
    def _create(cls, gate: ToolGate, context: Mapping[str, Any]) -> PreparedToolCall:
        prepared = object.__new__(cls)
        object.__setattr__(prepared, "_gate", gate)
        object.__setattr__(
            prepared, "_context", cast(Mapping[str, Any], freeze_json_value(context))
        )
        return prepared

    @property
    def tool_name(self) -> str:
        """Return the normalized registered tool name."""

        action = cast(Mapping[str, Any], self._context["action"])
        return cast(str, action["operation"])

    @property
    def capabilities(self) -> tuple[str, ...]:
        """Return the canonical immutable capability labels."""

        action = cast(Mapping[str, Any], self._context["action"])
        return cast(tuple[str, ...], action["capabilities"])

    @property
    def arguments(self) -> dict[str, Any]:
        """Return fresh detached arguments for caller-owned dispatch after authorization."""

        action = cast(Mapping[str, Any], self._context["action"])
        return cast(dict[str, Any], thaw_json_value(action["arguments"]))

    def _thaw_context(self) -> dict[str, Any]:
        return cast(dict[str, Any], thaw_json_value(self._context))

    def _approval_call_id(self) -> str | None:
        context = cast(Mapping[str, Any], self._context["context"])
        approval = context.get("approval")
        if not isinstance(approval, Mapping):
            return None
        return cast(str, approval["tool_call_id"])


class ToolGate:
    """Evaluate and enforce policy immediately before an in-process tool call."""

    def __init__(
        self,
        policy: Policy | PolicyRuntime,
        *,
        context_contract: ContextContract | None = None,
        deployment_lock: DeploymentLock | None = None,
        audit_log: str | Path | None = None,
        audit_sink: AuditSink | None = None,
    ) -> None:
        if not isinstance(policy, (Policy, PolicyRuntime)):
            raise TypeError("policy must be a Policy or PolicyRuntime")
        if audit_log is not None and audit_sink is not None:
            raise ValueError("audit_log and audit_sink are mutually exclusive")
        self._engine: PolicyEngine | PolicyRuntime
        if isinstance(policy, PolicyRuntime):
            if context_contract is not None or deployment_lock is not None:
                raise ValueError(
                    "context_contract and deployment_lock must be configured on PolicyRuntime"
                )
            self._engine = policy
        else:
            self._engine = PolicyEngine(
                policy,
                context_contract=context_contract,
                deployment_lock=deployment_lock,
            )
        selected_sink: AuditSink | None = None
        if audit_log is not None:
            selected_sink = JsonlAuditSink(audit_log)
        elif audit_sink is not None:
            selected_sink = _validated_sink(audit_sink)
        self._audit_sink = selected_sink

    @property
    def policy(self) -> Policy:
        """Return the immutable policy used by this gate."""

        return self._engine.policy

    @property
    def policy_fingerprint(self) -> str:
        """Return the exact policy fingerprint used by this gate."""

        return self._engine.policy_fingerprint

    @property
    def context_contract(self) -> ContextContract | None:
        """Return the immutable application context contract, when configured."""

        return self._engine.context_contract

    @property
    def context_contract_fingerprint(self) -> str | None:
        """Return the exact context-contract fingerprint, when configured."""

        return self._engine.context_contract_fingerprint

    @property
    def deployment_lock(self) -> DeploymentLock | None:
        """Return the verified exact-content deployment lock, when configured."""

        return self._engine.deployment_lock

    @property
    def runtime_status(self) -> PolicyRuntimeStatus | None:
        """Return coherent live-generation metadata for a runtime-backed gate."""

        return self._engine.status if isinstance(self._engine, PolicyRuntime) else None

    def bind(
        self,
        tool_name: str,
        *,
        capabilities: Iterable[str] = (),
    ) -> BoundToolGate:
        """Bind trusted tool identity and capabilities once at registration time."""

        return BoundToolGate(self, tool_name, capabilities)

    def bind_catalog(
        self,
        catalog: ToolCatalog,
        *,
        registered_tools: Iterable[str],
    ) -> BoundToolCatalog:
        """Bind a catalog after exact comparison with a trusted registry name snapshot."""

        validate_tool_catalog_registration(catalog, registered_tools)
        return BoundToolCatalog._create(self, catalog)

    def prepare(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        *,
        capabilities: Iterable[str] = (),
        actor: Mapping[str, Any] | None = None,
        context: Mapping[str, Any] | None = None,
        tool_call_id: str | None = None,
        approval: ToolCallApproval | None = None,
    ) -> PreparedToolCall:
        """Normalize and freeze one call for immediate batch authorization."""

        return PreparedToolCall._create(
            self,
            build_tool_context(
                tool_name,
                arguments,
                capabilities=capabilities,
                actor=actor,
                context=context,
                tool_call_id=tool_call_id,
                approval=approval,
            ),
        )

    def _evaluate_context(self, value: Mapping[str, Any]) -> Decision:
        decision = self._engine.evaluate(value)
        if self._audit_sink is not None:
            _emit_audit_record(self._audit_sink, decision)
        return decision

    @staticmethod
    def _require_allow(
        decision: Decision,
        *,
        decisions: tuple[Decision, ...] | None = None,
        blocking_index: int = 0,
    ) -> Decision:
        if decision.outcome is Outcome.DENY:
            raise ToolCallDeniedError(
                decision,
                decisions=decisions,
                blocking_index=blocking_index,
            )
        if decision.outcome is Outcome.REVIEW:
            raise ToolCallReviewRequiredError(
                decision,
                decisions=decisions,
                blocking_index=blocking_index,
            )
        return decision

    def evaluate(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        *,
        capabilities: Iterable[str] = (),
        actor: Mapping[str, Any] | None = None,
        context: Mapping[str, Any] | None = None,
        tool_call_id: str | None = None,
        approval: ToolCallApproval | None = None,
    ) -> Decision:
        """Evaluate one proposed call and append its audit record when configured."""

        return self._evaluate_context(
            build_tool_context(
                tool_name,
                arguments,
                capabilities=capabilities,
                actor=actor,
                context=context,
                tool_call_id=tool_call_id,
                approval=approval,
            )
        )

    def evaluate_many(self, calls: Iterable[PreparedToolCall]) -> tuple[Decision, ...]:
        """Evaluate a prepared batch in order against one captured policy generation."""

        try:
            iterator = iter(calls)
        except TypeError as exc:
            raise InputValidationError("tool-call batch must be iterable") from exc

        prepared_calls: list[PreparedToolCall] = []
        seen_calls: set[int] = set()
        seen_approval_ids: set[str] = set()
        for index, call in enumerate(iterator):
            if index >= MAX_TOOL_BATCH_ITEMS:
                raise InputValidationError(
                    f"tool-call batch exceeds the limit of {MAX_TOOL_BATCH_ITEMS} items"
                )
            if not isinstance(call, PreparedToolCall):
                raise InputValidationError(
                    f"tool-call batch item {index} must be a PreparedToolCall"
                )
            if call._gate is not self:
                raise InputValidationError(
                    f"tool-call batch item {index} was prepared by a different ToolGate"
                )
            call_identity = id(call)
            if call_identity in seen_calls:
                raise InputValidationError(
                    f"tool-call batch item {index} repeats a PreparedToolCall object"
                )
            seen_calls.add(call_identity)
            approval_call_id = call._approval_call_id()
            if approval_call_id is not None:
                if approval_call_id in seen_approval_ids:
                    raise InputValidationError(
                        f"tool-call batch item {index} repeats approval tool_call_id"
                    )
                seen_approval_ids.add(approval_call_id)
            prepared_calls.append(call)

        decisions = self._engine.evaluate_many(call._thaw_context() for call in prepared_calls)
        if self._audit_sink is not None:
            for decision in decisions:
                _emit_audit_record(self._audit_sink, decision)
        return decisions

    def explain(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        *,
        capabilities: Iterable[str] = (),
        actor: Mapping[str, Any] | None = None,
        context: Mapping[str, Any] | None = None,
        tool_call_id: str | None = None,
        approval: ToolCallApproval | None = None,
    ) -> PolicyExplanation:
        """Explain a normalized tool call without emitting an authorization audit record."""

        return self._engine.explain(
            build_tool_context(
                tool_name,
                arguments,
                capabilities=capabilities,
                actor=actor,
                context=context,
                tool_call_id=tool_call_id,
                approval=approval,
            )
        )

    def enforce(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        *,
        capabilities: Iterable[str] = (),
        actor: Mapping[str, Any] | None = None,
        context: Mapping[str, Any] | None = None,
        tool_call_id: str | None = None,
        approval: ToolCallApproval | None = None,
    ) -> Decision:
        """Return an allow decision or raise a typed fail-closed exception."""

        decision = self.evaluate(
            tool_name,
            arguments,
            capabilities=capabilities,
            actor=actor,
            context=context,
            tool_call_id=tool_call_id,
            approval=approval,
        )
        return self._require_allow(decision)

    def enforce_many(self, calls: Iterable[PreparedToolCall]) -> tuple[Decision, ...]:
        """Require every prepared call to be allowed before caller-owned dispatch."""

        decisions = self.evaluate_many(calls)
        for index, decision in enumerate(decisions):
            self._require_allow(
                decision,
                decisions=decisions,
                blocking_index=index,
            )
        return decisions

    def _authorize(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        *,
        capabilities: Iterable[str],
        actor: Mapping[str, Any] | None,
        context: Mapping[str, Any] | None,
        tool_call_id: str | None,
        approval: ToolCallApproval | None,
    ) -> tuple[Decision, dict[str, Any]]:
        prepared = build_tool_context(
            tool_name,
            arguments,
            capabilities=capabilities,
            actor=actor,
            context=context,
            tool_call_id=tool_call_id,
            approval=approval,
        )
        decision = self._require_allow(self._evaluate_context(prepared))
        action = cast(dict[str, Any], prepared["action"])
        return decision, cast(dict[str, Any], action["arguments"])

    def execute(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        executor: Callable[[dict[str, Any]], _ResultT],
        *,
        capabilities: Iterable[str] = (),
        actor: Mapping[str, Any] | None = None,
        context: Mapping[str, Any] | None = None,
        tool_call_id: str | None = None,
        approval: ToolCallApproval | None = None,
    ) -> ToolExecutionResult[_ResultT]:
        """Authorize and execute a callback with the detached validated arguments."""

        if not callable(executor):
            raise TypeError(
                "executor must be a synchronous callable; use execute_async for async callbacks"
            )
        async_call = inspect.iscoroutinefunction(executor) or inspect.iscoroutinefunction(
            type(executor).__call__
        )
        if async_call:
            raise TypeError(
                "executor must be a synchronous callable; use execute_async for async callbacks"
            )
        decision, prepared_arguments = self._authorize(
            tool_name,
            arguments,
            capabilities=capabilities,
            actor=actor,
            context=context,
            tool_call_id=tool_call_id,
            approval=approval,
        )
        return ToolExecutionResult(decision=decision, value=executor(prepared_arguments))

    async def execute_async(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        executor: Callable[[dict[str, Any]], Awaitable[_ResultT]],
        *,
        capabilities: Iterable[str] = (),
        actor: Mapping[str, Any] | None = None,
        context: Mapping[str, Any] | None = None,
        tool_call_id: str | None = None,
        approval: ToolCallApproval | None = None,
    ) -> ToolExecutionResult[_ResultT]:
        """Authorize and await a callback with the detached validated arguments."""

        if not callable(executor):
            raise TypeError("executor must be callable")
        decision, prepared_arguments = self._authorize(
            tool_name,
            arguments,
            capabilities=capabilities,
            actor=actor,
            context=context,
            tool_call_id=tool_call_id,
            approval=approval,
        )
        return ToolExecutionResult(
            decision=decision,
            value=await executor(prepared_arguments),
        )


@dataclass(frozen=True, slots=True, init=False)
class BoundToolGate:
    """A gate with immutable application-owned tool identity and capabilities."""

    _gate: ToolGate
    _tool_name: str
    _capabilities: tuple[str, ...]

    def __init__(
        self,
        gate: ToolGate,
        tool_name: str,
        capabilities: Iterable[str] = (),
    ) -> None:
        if not isinstance(gate, ToolGate):
            raise TypeError("gate must be a ToolGate")
        if not isinstance(tool_name, str) or not _TOOL_IDENTIFIER.fullmatch(tool_name):
            raise InputValidationError("tool name must be a 1-128 character identifier")
        object.__setattr__(self, "_gate", gate)
        object.__setattr__(self, "_tool_name", tool_name)
        object.__setattr__(self, "_capabilities", tuple(_capability_list(capabilities)))

    @property
    def gate(self) -> ToolGate:
        """Return the parent policy gate."""

        return self._gate

    @property
    def policy(self) -> Policy:
        """Return the immutable policy used by the parent gate."""

        return self._gate.policy

    @property
    def policy_fingerprint(self) -> str:
        """Return the exact policy fingerprint used by the parent gate."""

        return self._gate.policy_fingerprint

    @property
    def context_contract(self) -> ContextContract | None:
        """Return the application context contract used by the parent gate."""

        return self._gate.context_contract

    @property
    def context_contract_fingerprint(self) -> str | None:
        """Return the exact contract fingerprint used by the parent gate."""

        return self._gate.context_contract_fingerprint

    @property
    def deployment_lock(self) -> DeploymentLock | None:
        """Return the deployment lock verified by the parent gate."""

        return self._gate.deployment_lock

    @property
    def runtime_status(self) -> PolicyRuntimeStatus | None:
        """Return coherent live-generation metadata for a runtime-backed parent gate."""

        return self._gate.runtime_status

    @property
    def tool_name(self) -> str:
        """Return the registered tool name."""

        return self._tool_name

    @property
    def capabilities(self) -> tuple[str, ...]:
        """Return the canonical immutable capability labels."""

        return self._capabilities

    def fingerprint(
        self,
        tool_call_id: str,
        arguments: Mapping[str, Any],
        *,
        actor: Mapping[str, Any] | None = None,
    ) -> str:
        """Fingerprint one call using this binding's trusted metadata."""

        return fingerprint_tool_call(
            tool_call_id,
            self._tool_name,
            arguments,
            capabilities=self._capabilities,
            actor=actor,
        )

    def prepare(
        self,
        arguments: Mapping[str, Any],
        *,
        actor: Mapping[str, Any] | None = None,
        context: Mapping[str, Any] | None = None,
        tool_call_id: str | None = None,
        approval: ToolCallApproval | None = None,
    ) -> PreparedToolCall:
        """Prepare one immutable call using this binding's trusted metadata."""

        return self._gate.prepare(
            self._tool_name,
            arguments,
            capabilities=self._capabilities,
            actor=actor,
            context=context,
            tool_call_id=tool_call_id,
            approval=approval,
        )

    def evaluate(
        self,
        arguments: Mapping[str, Any],
        *,
        actor: Mapping[str, Any] | None = None,
        context: Mapping[str, Any] | None = None,
        tool_call_id: str | None = None,
        approval: ToolCallApproval | None = None,
    ) -> Decision:
        """Evaluate one call using this binding's trusted metadata."""

        return self._gate.evaluate(
            self._tool_name,
            arguments,
            capabilities=self._capabilities,
            actor=actor,
            context=context,
            tool_call_id=tool_call_id,
            approval=approval,
        )

    def explain(
        self,
        arguments: Mapping[str, Any],
        *,
        actor: Mapping[str, Any] | None = None,
        context: Mapping[str, Any] | None = None,
        tool_call_id: str | None = None,
        approval: ToolCallApproval | None = None,
    ) -> PolicyExplanation:
        """Explain one call using this binding's trusted metadata."""

        return self._gate.explain(
            self._tool_name,
            arguments,
            capabilities=self._capabilities,
            actor=actor,
            context=context,
            tool_call_id=tool_call_id,
            approval=approval,
        )

    def enforce(
        self,
        arguments: Mapping[str, Any],
        *,
        actor: Mapping[str, Any] | None = None,
        context: Mapping[str, Any] | None = None,
        tool_call_id: str | None = None,
        approval: ToolCallApproval | None = None,
    ) -> Decision:
        """Require an allow decision using this binding's trusted metadata."""

        return self._gate.enforce(
            self._tool_name,
            arguments,
            capabilities=self._capabilities,
            actor=actor,
            context=context,
            tool_call_id=tool_call_id,
            approval=approval,
        )

    def execute(
        self,
        arguments: Mapping[str, Any],
        executor: Callable[[dict[str, Any]], _ResultT],
        *,
        actor: Mapping[str, Any] | None = None,
        context: Mapping[str, Any] | None = None,
        tool_call_id: str | None = None,
        approval: ToolCallApproval | None = None,
    ) -> ToolExecutionResult[_ResultT]:
        """Authorize and execute with immutable registered tool metadata."""

        return self._gate.execute(
            self._tool_name,
            arguments,
            executor,
            capabilities=self._capabilities,
            actor=actor,
            context=context,
            tool_call_id=tool_call_id,
            approval=approval,
        )

    async def execute_async(
        self,
        arguments: Mapping[str, Any],
        executor: Callable[[dict[str, Any]], Awaitable[_ResultT]],
        *,
        actor: Mapping[str, Any] | None = None,
        context: Mapping[str, Any] | None = None,
        tool_call_id: str | None = None,
        approval: ToolCallApproval | None = None,
    ) -> ToolExecutionResult[_ResultT]:
        """Authorize and await execution with immutable registered tool metadata."""

        return await self._gate.execute_async(
            self._tool_name,
            arguments,
            executor,
            capabilities=self._capabilities,
            actor=actor,
            context=context,
            tool_call_id=tool_call_id,
            approval=approval,
        )


@dataclass(frozen=True, slots=True, init=False, eq=False, repr=False)
class BoundToolCatalog(Mapping[str, BoundToolGate]):
    """Immutable gate-specific bindings created from one verified tool catalog."""

    _gate: ToolGate
    _catalog: ToolCatalog
    _catalog_fingerprint: str
    _bindings: Mapping[str, BoundToolGate]

    def __init__(self) -> None:
        raise TypeError("BoundToolCatalog objects are created by ToolGate.bind_catalog")

    def __repr__(self) -> str:
        """Return catalog identity metadata without capability or call values."""

        return (
            f"BoundToolCatalog(catalog_id={self.catalog.id!r}, "
            f"catalog_version={self.catalog.version!r}, tool_count={len(self)})"
        )

    @classmethod
    def _create(cls, gate: ToolGate, catalog: ToolCatalog) -> BoundToolCatalog:
        bound = object.__new__(cls)
        object.__setattr__(bound, "_gate", gate)
        object.__setattr__(bound, "_catalog", catalog)
        object.__setattr__(bound, "_catalog_fingerprint", fingerprint_tool_catalog(catalog))
        object.__setattr__(
            bound,
            "_bindings",
            MappingProxyType(
                {
                    tool.name: gate.bind(tool.name, capabilities=tool.capabilities)
                    for tool in catalog.tools
                }
            ),
        )
        return bound

    @property
    def gate(self) -> ToolGate:
        """Return the enforcing gate used for every catalog binding."""

        return self._gate

    @property
    def catalog(self) -> ToolCatalog:
        """Return the immutable catalog used to create these bindings."""

        return self._catalog

    @property
    def catalog_fingerprint(self) -> str:
        """Return the exact catalog fingerprint bound to this mapping."""

        return self._catalog_fingerprint

    @property
    def tool_names(self) -> tuple[str, ...]:
        """Return canonical registered names in this binding map."""

        return self.catalog.tool_names

    def __getitem__(self, tool_name: str) -> BoundToolGate:
        return self._bindings[tool_name]

    def __iter__(self) -> Iterator[str]:
        return iter(self.tool_names)

    def __len__(self) -> int:
        return len(self._bindings)
