"""Fail-closed tool-call gate behavior."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from samsarix_ethics import (
    MAX_TOOL_CAPABILITIES,
    TOOL_CONTEXT_VERSION,
    AuditLogError,
    InputValidationError,
    Outcome,
    Policy,
    ToolCallDeniedError,
    ToolCallReviewRequiredError,
    ToolGate,
    build_tool_context,
    load_policy,
)


def _gate_policy() -> Policy:
    return Policy.from_dict(
        {
            "schema_version": 1,
            "id": "tool-gate-tests",
            "version": "1",
            "default_effect": "review",
            "rules": [
                {
                    "id": "deny-delete",
                    "effect": "deny",
                    "conditions": [
                        {"field": "action.capabilities", "operator": "contains", "value": "delete"}
                    ],
                },
                {
                    "id": "allow-read",
                    "effect": "allow",
                    "conditions": [
                        {"field": "action.capabilities", "operator": "contains", "value": "read"}
                    ],
                },
            ],
        }
    )


def test_build_tool_context_is_validated_and_detached() -> None:
    arguments = {"resource": {"id": "R-1"}}
    actor = {"id": "agent-1"}
    runtime_context = {"request_id": "request-1"}

    value = build_tool_context(
        "read_resource",
        arguments,
        capabilities=["resource:read", "data:sensitive"],
        actor=actor,
        context=runtime_context,
    )
    arguments["resource"]["id"] = "changed"
    actor["id"] = "changed"
    runtime_context["request_id"] = "changed"

    assert value == {
        "tool_context_version": 1,
        "actor": {"id": "agent-1"},
        "action": {
            "kind": "tool_call",
            "operation": "read_resource",
            "capabilities": ["data:sensitive", "resource:read"],
            "arguments": {"resource": {"id": "R-1"}},
        },
        "context": {"request_id": "request-1"},
    }
    assert TOOL_CONTEXT_VERSION == 1


@pytest.mark.parametrize(
    ("tool_name", "arguments", "capabilities", "message"),
    [
        ("bad name", {}, (), "tool name"),
        ("tool", {"value": object()}, (), "non-JSON value"),
        ("tool", {}, "read", "iterable of identifiers"),
        ("tool", {}, ["bad capability"], r"capabilities\[0\]"),
        ("tool", {}, ["read", "read"], "duplicates"),
        ("tool", {}, None, "must be iterable"),
    ],
)
def test_build_tool_context_rejects_invalid_values(
    tool_name: str,
    arguments: dict[str, Any],
    capabilities: Any,
    message: str,
) -> None:
    with pytest.raises(InputValidationError, match=message):
        build_tool_context(tool_name, arguments, capabilities=capabilities)


def test_build_tool_context_bounds_capabilities() -> None:
    with pytest.raises(InputValidationError, match=f"limit of {MAX_TOOL_CAPABILITIES}"):
        build_tool_context(
            "tool",
            {},
            capabilities=(f"capability:{index}" for index in range(MAX_TOOL_CAPABILITIES + 1)),
        )


def test_build_tool_context_rejects_falsey_non_object_metadata() -> None:
    with pytest.raises(InputValidationError, match="tool actor must be a JSON object"):
        build_tool_context("tool", {}, actor=[])  # type: ignore[arg-type]
    with pytest.raises(InputValidationError, match="tool context must be a JSON object"):
        build_tool_context("tool", {}, context=False)  # type: ignore[arg-type]


def test_tool_gate_executes_only_allow_decisions() -> None:
    called: list[str] = []
    gate = ToolGate(_gate_policy())
    arguments = {"resource_id": "R-1"}

    def execute(validated: dict[str, Any]) -> dict[str, Any]:
        assert validated == arguments
        assert validated is not arguments
        called.append("read")
        return {"value": 42}

    result = gate.execute(
        "read_resource",
        arguments,
        execute,
        capabilities=["read"],
    )

    assert result.value == {"value": 42}
    assert result.decision.outcome is Outcome.ALLOW
    assert called == ["read"]
    assert gate.policy.id == "tool-gate-tests"


def test_tool_gate_denial_never_calls_executor_or_exposes_arguments() -> None:
    called = False
    gate = ToolGate(_gate_policy())

    def execute(_validated: dict[str, Any]) -> None:
        nonlocal called
        called = True

    with pytest.raises(ToolCallDeniedError) as captured:
        gate.execute(
            "delete_resource",
            {"secret": "never-report-this"},
            execute,
            capabilities=["delete"],
        )

    assert called is False
    assert captured.value.decision.outcome is Outcome.DENY
    assert "never-report-this" not in str(captured.value)


def test_tool_gate_review_never_calls_executor() -> None:
    called = False
    gate = ToolGate(_gate_policy())

    def execute(_validated: dict[str, Any]) -> None:
        nonlocal called
        called = True

    with pytest.raises(ToolCallReviewRequiredError) as captured:
        gate.execute("unknown_tool", {}, execute)

    assert called is False
    assert captured.value.decision.outcome is Outcome.REVIEW


def test_tool_gate_enforce_returns_only_allow() -> None:
    gate = ToolGate(_gate_policy())

    assert gate.enforce("read_resource", {}, capabilities=["read"]).allowed is True
    with pytest.raises(ToolCallDeniedError):
        gate.enforce("delete_resource", {}, capabilities=["delete"])


def test_tool_gate_propagates_executor_errors() -> None:
    gate = ToolGate(_gate_policy())

    def execute(_validated: dict[str, Any]) -> None:
        raise RuntimeError("tool failed")

    with pytest.raises(RuntimeError, match="tool failed"):
        gate.execute("read_resource", {}, execute, capabilities=["read"])


def test_tool_gate_audit_is_metadata_only(tmp_path: Path) -> None:
    audit_log = tmp_path / "tool-decisions.jsonl"
    gate = ToolGate(_gate_policy(), audit_log=audit_log)

    decision = gate.evaluate(
        "read_resource",
        {"secret": "never-report-this"},
        capabilities=["read"],
    )
    record = json.loads(audit_log.read_text(encoding="utf-8"))

    assert record["decision_id"] == decision.decision_id
    assert record["outcome"] == "allow"
    assert "never-report-this" not in audit_log.read_text(encoding="utf-8")


def test_tool_gate_audit_failure_prevents_execution(tmp_path: Path) -> None:
    called = False
    gate = ToolGate(_gate_policy(), audit_log=tmp_path / "missing" / "audit.jsonl")

    def execute(_validated: dict[str, Any]) -> None:
        nonlocal called
        called = True

    with pytest.raises(AuditLogError):
        gate.execute("read_resource", {}, execute, capabilities=["read"])

    assert called is False


def test_tool_gate_executes_async_callback() -> None:
    gate = ToolGate(_gate_policy())

    async def execute(validated: dict[str, Any]) -> str:
        assert validated == {}
        await asyncio.sleep(0)
        return "complete"

    result = asyncio.run(gate.execute_async("read_resource", {}, execute, capabilities=["read"]))

    assert result.value == "complete"
    assert result.decision.allowed is True


def test_tool_gate_execute_async_denial_never_awaits_executor() -> None:
    called = False
    gate = ToolGate(_gate_policy())

    async def execute(_validated: dict[str, Any]) -> None:
        nonlocal called
        called = True

    with pytest.raises(ToolCallDeniedError):
        asyncio.run(gate.execute_async("delete_resource", {}, execute, capabilities=["delete"]))

    assert called is False


def test_tool_gate_execute_async_review_never_awaits_executor() -> None:
    called = False
    gate = ToolGate(_gate_policy())

    async def execute(_validated: dict[str, Any]) -> None:
        nonlocal called
        called = True

    with pytest.raises(ToolCallReviewRequiredError):
        asyncio.run(gate.execute_async("unknown_tool", {}, execute))

    assert called is False


def test_tool_gate_execute_async_audit_failure_never_awaits_executor(tmp_path: Path) -> None:
    called = False
    gate = ToolGate(_gate_policy(), audit_log=tmp_path / "missing" / "audit.jsonl")

    async def execute(_validated: dict[str, Any]) -> None:
        nonlocal called
        called = True

    with pytest.raises(AuditLogError):
        asyncio.run(gate.execute_async("read_resource", {}, execute, capabilities=["read"]))

    assert called is False


def test_tool_gate_rejects_programmer_errors() -> None:
    with pytest.raises(TypeError, match="policy must be"):
        ToolGate(object())  # type: ignore[arg-type]

    gate = ToolGate(_gate_policy())
    with pytest.raises(TypeError, match="synchronous callable"):
        gate.execute("read_resource", {}, None, capabilities=["read"])  # type: ignore[arg-type]

    async def async_executor(_validated: dict[str, Any]) -> None:
        return None

    class AsyncCallable:
        async def __call__(self, _validated: dict[str, Any]) -> None:
            return None

    for executor in (async_executor, AsyncCallable()):
        with pytest.raises(TypeError, match="use execute_async"):
            gate.execute("read_resource", {}, executor, capabilities=["read"])

    with pytest.raises(TypeError, match="executor must be callable"):
        asyncio.run(
            gate.execute_async(
                "read_resource",
                {},
                None,  # type: ignore[arg-type]
                capabilities=["read"],
            )
        )


def test_baseline_tool_policy_matches_gate_contract() -> None:
    root = Path(__file__).parents[1]
    gate = ToolGate(load_policy(root / "examples/policies/tool-call-baseline.json"))

    denied = gate.evaluate("delete_record", {"record_id": "R-1"}, capabilities=["destructive"])
    approved = gate.evaluate(
        "delete_record",
        {"record_id": "R-1"},
        capabilities=["destructive"],
        context={"human_approved": True},
    )

    assert denied.outcome is Outcome.DENY
    assert approved.outcome is Outcome.ALLOW
