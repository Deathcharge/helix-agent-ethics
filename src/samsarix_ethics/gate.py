# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Fail-closed policy enforcement for in-process agent tool calls."""

from __future__ import annotations

import inspect
import re
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generic, TypeVar, cast

from .engine import PolicyEngine
from .errors import InputValidationError, ToolCallDeniedError, ToolCallReviewRequiredError
from .io import append_audit_record
from .models import Decision, Outcome, Policy
from .validation import thaw_json_value, validate_context

MAX_TOOL_CAPABILITIES = 64
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


def build_tool_context(
    tool_name: str,
    arguments: Mapping[str, Any],
    *,
    capabilities: Iterable[str] = (),
    actor: Mapping[str, Any] | None = None,
    context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a validated, detached policy context for one proposed tool call."""

    if not isinstance(tool_name, str) or not _TOOL_IDENTIFIER.fullmatch(tool_name):
        raise InputValidationError("tool name must be a 1-128 character identifier")
    arguments_value = _json_object(arguments, label="tool arguments")
    actor_value = _json_object({} if actor is None else actor, label="tool actor")
    context_value = _json_object({} if context is None else context, label="tool context")
    value = {
        "tool_context_version": TOOL_CONTEXT_VERSION,
        "actor": actor_value,
        "action": {
            "kind": "tool_call",
            "operation": tool_name,
            "capabilities": _capability_list(capabilities),
            "arguments": arguments_value,
        },
        "context": context_value,
    }
    validate_context(value, label="tool-call policy context")
    return value


@dataclass(frozen=True, slots=True)
class ToolExecutionResult(Generic[_ResultT]):
    """An allowed tool result paired with the decision that authorized it."""

    decision: Decision
    value: _ResultT


class ToolGate:
    """Evaluate and enforce policy immediately before an in-process tool call."""

    def __init__(self, policy: Policy, *, audit_log: str | Path | None = None) -> None:
        if not isinstance(policy, Policy):
            raise TypeError("policy must be a Policy")
        self._engine = PolicyEngine(policy)
        self._audit_log = audit_log

    @property
    def policy(self) -> Policy:
        """Return the immutable policy used by this gate."""

        return self._engine.policy

    def _evaluate_context(self, value: Mapping[str, Any]) -> Decision:
        decision = self._engine.evaluate(value)
        if self._audit_log is not None:
            append_audit_record(self._audit_log, decision)
        return decision

    @staticmethod
    def _require_allow(decision: Decision) -> Decision:
        if decision.outcome is Outcome.DENY:
            raise ToolCallDeniedError(decision)
        if decision.outcome is Outcome.REVIEW:
            raise ToolCallReviewRequiredError(decision)
        return decision

    def evaluate(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        *,
        capabilities: Iterable[str] = (),
        actor: Mapping[str, Any] | None = None,
        context: Mapping[str, Any] | None = None,
    ) -> Decision:
        """Evaluate one proposed call and append its audit record when configured."""

        return self._evaluate_context(
            build_tool_context(
                tool_name,
                arguments,
                capabilities=capabilities,
                actor=actor,
                context=context,
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
    ) -> Decision:
        """Return an allow decision or raise a typed fail-closed exception."""

        decision = self.evaluate(
            tool_name,
            arguments,
            capabilities=capabilities,
            actor=actor,
            context=context,
        )
        return self._require_allow(decision)

    def _authorize(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        *,
        capabilities: Iterable[str],
        actor: Mapping[str, Any] | None,
        context: Mapping[str, Any] | None,
    ) -> tuple[Decision, dict[str, Any]]:
        prepared = build_tool_context(
            tool_name,
            arguments,
            capabilities=capabilities,
            actor=actor,
            context=context,
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
        )
        return ToolExecutionResult(
            decision=decision,
            value=await executor(prepared_arguments),
        )
