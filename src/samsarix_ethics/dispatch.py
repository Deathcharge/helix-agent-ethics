# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Immutable framework-neutral dispatch bindings for trusted local tools."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .approval import ToolCallApproval
from .audit import AuditSink
from .authenticated_deployment import (
    ToolGateDeploymentEnvelope,
    verify_tool_gate_deployment_envelope,
)
from .catalog import MAX_TOOL_CATALOG_TOOLS, ToolCatalog, validate_tool_catalog_registration
from .errors import InputValidationError, ToolCatalogValidationError
from .gate import (
    MAX_TOOL_BATCH_ITEMS,
    BoundToolCatalog,
    BoundToolGate,
    PreparedToolCall,
    ToolExecutionResult,
    ToolGate,
)
from .tool_gate_deployment import ToolGateDeployment

ToolCallback = Callable[..., Any]


def _snapshot_callbacks(
    registered_tools: Mapping[str, ToolCallback],
) -> Mapping[str, ToolCallback]:
    if not isinstance(registered_tools, Mapping):
        raise ToolCatalogValidationError("registered tools must be a mapping of names to callables")

    callbacks: dict[str, ToolCallback] = {}
    try:
        items = iter(registered_tools.items())
    except (AttributeError, TypeError) as exc:
        raise ToolCatalogValidationError(
            "registered tools must be a mapping of names to callables"
        ) from exc
    for index, item in enumerate(items):
        if index >= MAX_TOOL_CATALOG_TOOLS:
            raise ToolCatalogValidationError(
                f"registered tools exceed the limit of {MAX_TOOL_CATALOG_TOOLS} tools"
            )
        try:
            name, callback = item
        except (TypeError, ValueError) as exc:
            raise ToolCatalogValidationError(
                f"registered tools item {index} must contain a name and callable"
            ) from exc
        if not isinstance(name, str):
            raise ToolCatalogValidationError(f"registered tools[{index}] must be a valid tool name")
        if name in callbacks:
            raise ToolCatalogValidationError("registered tools must not contain duplicate names")
        if not callable(callback):
            raise ToolCatalogValidationError(f"registered tool {name!r} must be callable")
        callbacks[name] = callback
    return MappingProxyType(callbacks)


def _close_awaitable(value: Awaitable[Any]) -> None:
    close = getattr(value, "close", None)
    if callable(close):
        close()


def _invoke_sync(callback: ToolCallback, arguments: dict[str, Any]) -> Any:
    value = callback(**arguments)
    if inspect.isawaitable(value):
        _close_awaitable(value)
        raise TypeError("registered tool returned an awaitable; use execute_async")
    return value


async def _invoke_async(callback: ToolCallback, arguments: dict[str, Any]) -> Any:
    value = callback(**arguments)
    if not inspect.isawaitable(value):
        raise TypeError("registered tool must return an awaitable for execute_async")
    return await value


@dataclass(frozen=True, slots=True, init=False, eq=False, repr=False)
class ToolDispatcher:
    """A verified catalog bound to one immutable snapshot of Python callables.

    Registered callbacks receive the validated tool arguments as keyword arguments.
    """

    _bindings: BoundToolCatalog
    _callbacks: Mapping[str, ToolCallback]

    def __init__(self) -> None:
        raise TypeError(
            "ToolDispatcher objects are created by bind_catalog, bind_deployment, "
            "or bind_authenticated_deployment"
        )

    def __repr__(self) -> str:
        """Return catalog identity without callback or capability details."""

        return (
            f"ToolDispatcher(catalog_id={self.catalog.id!r}, "
            f"catalog_version={self.catalog.version!r}, tool_count={len(self)})"
        )

    @classmethod
    def _create(
        cls,
        bindings: BoundToolCatalog,
        callbacks: Mapping[str, ToolCallback],
    ) -> ToolDispatcher:
        dispatcher = object.__new__(cls)
        object.__setattr__(dispatcher, "_bindings", bindings)
        object.__setattr__(dispatcher, "_callbacks", callbacks)
        return dispatcher

    @classmethod
    def bind_catalog(
        cls,
        gate: ToolGate,
        catalog: ToolCatalog,
        *,
        registered_tools: Mapping[str, ToolCallback],
    ) -> ToolDispatcher:
        """Freeze callbacks after exact matching against one trusted catalog."""

        if not isinstance(gate, ToolGate):
            raise TypeError("gate must be a ToolGate")
        callbacks = _snapshot_callbacks(registered_tools)
        validate_tool_catalog_registration(catalog, callbacks)
        bindings = gate.bind_catalog(catalog, registered_tools=callbacks)
        return cls._create(bindings, callbacks)

    @classmethod
    def bind_deployment(
        cls,
        deployment: ToolGateDeployment,
        *,
        registered_tools: Mapping[str, ToolCallback],
        audit_log: str | Path | None = None,
        audit_sink: AuditSink | None = None,
    ) -> ToolDispatcher:
        """Construct a gate and freeze callbacks from one coherent deployment."""

        callbacks = _snapshot_callbacks(registered_tools)
        bindings = ToolGate.bind_deployment(
            deployment,
            registered_tools=callbacks,
            audit_log=audit_log,
            audit_sink=audit_sink,
        )
        return cls._create(bindings, callbacks)

    @classmethod
    def bind_authenticated_deployment(
        cls,
        envelope: ToolGateDeploymentEnvelope,
        *,
        authentication_keys: Mapping[str, bytes | bytearray | memoryview],
        expected_audience: str,
        registered_tools: Mapping[str, ToolCallback],
        minimum_sequence: int = 1,
        now: datetime | None = None,
        clock_skew_seconds: int = 0,
        audit_log: str | Path | None = None,
        audit_sink: AuditSink | None = None,
    ) -> ToolDispatcher:
        """Authenticate an envelope immediately before freezing its callbacks."""

        verified = verify_tool_gate_deployment_envelope(
            envelope,
            authentication_keys,
            expected_audience=expected_audience,
            minimum_sequence=minimum_sequence,
            now=now,
            clock_skew_seconds=clock_skew_seconds,
        )
        return cls.bind_deployment(
            verified.deployment,
            registered_tools=registered_tools,
            audit_log=audit_log,
            audit_sink=audit_sink,
        )

    @property
    def bindings(self) -> BoundToolCatalog:
        """Return immutable authorization bindings for approval and inspection flows."""

        return self._bindings

    @property
    def catalog(self) -> ToolCatalog:
        """Return the exact trusted catalog used at registration."""

        return self.bindings.catalog

    @property
    def catalog_fingerprint(self) -> str:
        """Return the exact catalog fingerprint used at registration."""

        return self.bindings.catalog_fingerprint

    @property
    def tool_names(self) -> tuple[str, ...]:
        """Return the canonical registered tool names."""

        return self.bindings.tool_names

    def __len__(self) -> int:
        return len(self._callbacks)

    def _binding(self, tool_name: str) -> BoundToolGate:
        if not isinstance(tool_name, str) or tool_name not in self._callbacks:
            raise InputValidationError("tool name is not registered in this dispatcher")
        return self.bindings[tool_name]

    def prepare(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        *,
        actor: Mapping[str, Any] | None = None,
        context: Mapping[str, Any] | None = None,
        tool_call_id: str | None = None,
        approval: ToolCallApproval | None = None,
    ) -> PreparedToolCall:
        """Normalize and freeze one model-selected call using trusted metadata."""

        return self._binding(tool_name).prepare(
            arguments,
            actor=actor,
            context=context,
            tool_call_id=tool_call_id,
            approval=approval,
        )

    def execute(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        *,
        actor: Mapping[str, Any] | None = None,
        context: Mapping[str, Any] | None = None,
        tool_call_id: str | None = None,
        approval: ToolCallApproval | None = None,
    ) -> ToolExecutionResult[Any]:
        """Authorize and invoke the frozen synchronous callback by trusted name."""

        binding = self._binding(tool_name)
        callback = self._callbacks[tool_name]
        return binding.execute(
            arguments,
            lambda prepared: _invoke_sync(callback, prepared),
            actor=actor,
            context=context,
            tool_call_id=tool_call_id,
            approval=approval,
        )

    async def execute_async(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        *,
        actor: Mapping[str, Any] | None = None,
        context: Mapping[str, Any] | None = None,
        tool_call_id: str | None = None,
        approval: ToolCallApproval | None = None,
    ) -> ToolExecutionResult[Any]:
        """Authorize and await the frozen callback by trusted name."""

        binding = self._binding(tool_name)
        callback = self._callbacks[tool_name]

        async def invoke(prepared: dict[str, Any]) -> Any:
            return await _invoke_async(callback, prepared)

        return await binding.execute_async(
            arguments,
            invoke,
            actor=actor,
            context=context,
            tool_call_id=tool_call_id,
            approval=approval,
        )

    @staticmethod
    def _materialize_batch(calls: Iterable[PreparedToolCall]) -> tuple[PreparedToolCall, ...]:
        if isinstance(calls, (str, bytes, bytearray)):
            raise InputValidationError("tool-call batch must be iterable")
        try:
            iterator = iter(calls)
        except TypeError as exc:
            raise InputValidationError("tool-call batch must be iterable") from exc
        batch: list[PreparedToolCall] = []
        for index, call in enumerate(iterator):
            if index >= MAX_TOOL_BATCH_ITEMS:
                raise InputValidationError(
                    f"tool-call batch exceeds the limit of {MAX_TOOL_BATCH_ITEMS} items"
                )
            batch.append(call)
        return tuple(batch)

    def _validate_batch_bindings(self, batch: tuple[PreparedToolCall, ...]) -> None:
        for index, call in enumerate(batch):
            if not isinstance(call, PreparedToolCall):
                raise InputValidationError(
                    f"tool-call batch item {index} must be a PreparedToolCall"
                )
            if call.tool_name not in self._callbacks:
                raise InputValidationError(
                    f"tool-call batch item {index} is not registered in this dispatcher"
                )
            if call.capabilities != self.bindings[call.tool_name].capabilities:
                raise InputValidationError(
                    f"tool-call batch item {index} does not match dispatcher capabilities"
                )

    def execute_many(
        self,
        calls: Iterable[PreparedToolCall],
    ) -> tuple[ToolExecutionResult[Any], ...]:
        """Authorize the complete batch, then invoke frozen callbacks in order."""

        batch = self._materialize_batch(calls)
        self._validate_batch_bindings(batch)
        decisions = self.bindings.gate.enforce_many(batch)
        results: list[ToolExecutionResult[Any]] = []
        for call, decision in zip(batch, decisions, strict=True):
            callback = self._callbacks[call.tool_name]
            results.append(
                ToolExecutionResult(
                    decision=decision,
                    value=_invoke_sync(callback, call.arguments),
                )
            )
        return tuple(results)

    async def execute_many_async(
        self,
        calls: Iterable[PreparedToolCall],
    ) -> tuple[ToolExecutionResult[Any], ...]:
        """Authorize the complete batch, then await frozen callbacks in order."""

        batch = self._materialize_batch(calls)
        self._validate_batch_bindings(batch)
        decisions = self.bindings.gate.enforce_many(batch)
        results: list[ToolExecutionResult[Any]] = []
        for call, decision in zip(batch, decisions, strict=True):
            callback = self._callbacks[call.tool_name]
            results.append(
                ToolExecutionResult(
                    decision=decision,
                    value=await _invoke_async(callback, call.arguments),
                )
            )
        return tuple(results)
