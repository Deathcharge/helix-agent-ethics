"""Registration-time tool identity and capability binding."""

from __future__ import annotations

import asyncio
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest

from samsarix_ethics import (
    AuditRecord,
    BoundToolGate,
    InputValidationError,
    Outcome,
    ToolCallApproval,
    ToolCallDeniedError,
    ToolCallReviewRequiredError,
    ToolGate,
    load_policy,
)


def _baseline_gate(*, records: list[AuditRecord] | None = None) -> ToolGate:
    policy_path = Path(__file__).parents[1] / "examples/policies/tool-call-baseline.json"
    return ToolGate(
        load_policy(policy_path), audit_sink=None if records is None else records.append
    )


def test_bind_canonicalizes_and_detaches_trusted_metadata() -> None:
    capabilities = ["resource:read", "data:sensitive"]
    gate = _baseline_gate()
    bound = gate.bind("read_ticket", capabilities=reversed(capabilities))
    capabilities.append("destructive")

    assert isinstance(bound, BoundToolGate)
    assert bound.gate is gate
    assert bound.policy is gate.policy
    assert bound.tool_name == "read_ticket"
    assert bound.capabilities == ("data:sensitive", "resource:read")
    with pytest.raises(FrozenInstanceError):
        bound._tool_name = "delete_ticket"  # type: ignore[misc]


def test_bind_rejects_malformed_registration_metadata() -> None:
    gate = _baseline_gate()

    with pytest.raises(InputValidationError, match="tool name"):
        gate.bind("bad tool", capabilities=["resource:read"])
    with pytest.raises(InputValidationError, match="iterable of identifiers"):
        gate.bind("read_ticket", capabilities="resource:read")
    with pytest.raises(InputValidationError, match="duplicates"):
        gate.bind("read_ticket", capabilities=["resource:read", "resource:read"])
    with pytest.raises(TypeError, match="gate must be a ToolGate"):
        BoundToolGate(object(), "read_ticket", ())  # type: ignore[arg-type]


def test_bound_gate_evaluates_and_enforces_without_per_call_capabilities() -> None:
    read = _baseline_gate().bind("read_ticket", capabilities=["resource:read"])
    delete = _baseline_gate().bind("delete_ticket", capabilities=["destructive"])

    assert read.evaluate({"ticket_id": "T-100"}).outcome is Outcome.ALLOW
    assert read.enforce({"ticket_id": "T-100"}).outcome is Outcome.ALLOW
    with pytest.raises(ToolCallDeniedError):
        delete.enforce({"ticket_id": "T-100"})
    with pytest.raises(TypeError, match="unexpected keyword argument 'capabilities'"):
        read.evaluate({"ticket_id": "T-100"}, capabilities=[])  # type: ignore[call-arg]


def test_bound_gate_executes_with_detached_arguments_and_audits() -> None:
    records: list[AuditRecord] = []
    bound = _baseline_gate(records=records).bind(
        "read_ticket",
        capabilities=["resource:read"],
    )
    arguments = {"ticket_id": "T-100"}

    result = bound.execute(
        arguments,
        lambda prepared: {"ticket_id": prepared["ticket_id"], "status": "open"},
        actor={"id": "support-agent"},
    )

    assert result.value == {"ticket_id": "T-100", "status": "open"}
    assert result.decision.outcome is Outcome.ALLOW
    assert len(records) == 1


def test_bound_gate_fingerprint_and_approval_share_registered_metadata() -> None:
    called = False
    bound = _baseline_gate().bind("send_email", capabilities=["external:write"])
    arguments = {"to": "customer@example.com"}
    actor = {"id": "support-agent"}
    call_id = "email-call-100"

    with pytest.raises(ToolCallReviewRequiredError):
        bound.enforce(arguments, actor=actor)

    approval = ToolCallApproval(
        call_id,
        True,
        bound.fingerprint(call_id, arguments, actor=actor),
    )

    def send(prepared: dict[str, Any]) -> str:
        nonlocal called
        called = True
        return f"sent to {prepared['to']}"

    result = bound.execute(
        arguments,
        send,
        actor=actor,
        tool_call_id=call_id,
        approval=approval,
    )

    assert result.value == "sent to customer@example.com"
    assert called is True


def test_bound_gate_rejects_approval_after_actor_mutation() -> None:
    records: list[AuditRecord] = []
    called = False
    bound = _baseline_gate(records=records).bind(
        "send_email",
        capabilities=["external:write"],
    )
    arguments = {"to": "customer@example.com"}
    call_id = "email-call-100"
    approval = ToolCallApproval(
        call_id,
        True,
        bound.fingerprint(call_id, arguments, actor={"id": "agent-1"}),
    )

    def send(_prepared: dict[str, Any]) -> None:
        nonlocal called
        called = True

    with pytest.raises(InputValidationError, match="does not match"):
        bound.execute(
            arguments,
            send,
            actor={"id": "agent-2"},
            tool_call_id=call_id,
            approval=approval,
        )

    assert called is False
    assert records == []


def test_bound_gate_supports_async_execution() -> None:
    bound = _baseline_gate().bind("read_ticket", capabilities=["resource:read"])

    async def read(prepared: dict[str, Any]) -> str:
        return f"read {prepared['ticket_id']}"

    result = asyncio.run(bound.execute_async({"ticket_id": "T-100"}, read))

    assert result.value == "read T-100"
    assert result.decision.outcome is Outcome.ALLOW
