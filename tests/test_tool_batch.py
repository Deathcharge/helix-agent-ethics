"""Prepared tool calls and all-calls-before-dispatch authorization."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest

from samsarix_ethics import (
    MAX_TOOL_BATCH_ITEMS,
    AuditRecord,
    ContextContract,
    InputValidationError,
    Outcome,
    PreparedToolCall,
    ToolCallApproval,
    ToolCallDeniedError,
    ToolGate,
    load_context_contract,
    load_policy,
)

_ROOT = Path(__file__).parents[1]
_POLICY_PATH = _ROOT / "examples/policies/tool-call-baseline.json"
_CONTRACT_PATH = _ROOT / "examples/contracts/tool-call-context.json"


def _gate(*, records: list[AuditRecord] | None = None) -> ToolGate:
    return ToolGate(
        load_policy(_POLICY_PATH),
        audit_sink=None if records is None else records.append,
    )


def test_prepared_call_is_gate_created_immutable_and_detached() -> None:
    gate = _gate()
    bound = gate.bind(
        "read_file",
        capabilities=["resource:read", "data:sensitive"],
    )
    arguments = {"path": "README.md", "options": ["metadata"]}

    call = bound.prepare(arguments, actor={"id": "coding-agent"})
    arguments["path"] = "secrets.env"
    arguments["options"].append("contents")

    assert call.tool_name == "read_file"
    assert call.capabilities == ("data:sensitive", "resource:read")
    assert call.arguments == {"path": "README.md", "options": ["metadata"]}
    assert repr(call) == (
        "PreparedToolCall(tool_name='read_file', capabilities=('data:sensitive', 'resource:read'))"
    )
    assert "README.md" not in repr(call)
    equivalent = bound.prepare({"path": "README.md", "options": ["metadata"]})
    assert call != equivalent
    assert len({call, equivalent}) == 2
    returned = call.arguments
    returned["path"] = "changed"
    assert call.arguments["path"] == "README.md"
    with pytest.raises(FrozenInstanceError):
        call._gate = _gate()  # type: ignore[misc]
    with pytest.raises(TypeError, match=r"created by ToolGate\.prepare"):
        PreparedToolCall()


def test_gate_evaluates_prepared_batch_in_order_and_audits_every_decision() -> None:
    records: list[AuditRecord] = []
    gate = _gate(records=records)
    read = gate.bind("read_file", capabilities=["resource:read"])
    delete = gate.bind("delete_file", capabilities=["destructive"])
    send = gate.bind("send_message", capabilities=["external:write"])

    decisions = gate.evaluate_many(
        [
            read.prepare({"path": "README.md"}),
            delete.prepare({"path": "old.log"}),
            send.prepare({"channel": "ops"}),
        ]
    )

    assert tuple(decision.outcome for decision in decisions) == (
        Outcome.ALLOW,
        Outcome.DENY,
        Outcome.REVIEW,
    )
    assert records == [AuditRecord.from_decision(decision) for decision in decisions]


def test_enforce_many_authorizes_only_an_all_allow_batch() -> None:
    records: list[AuditRecord] = []
    gate = _gate(records=records)
    read = gate.bind("read_file", capabilities=["resource:read"])
    blocked = gate.bind("delete_file", capabilities=["destructive"])

    allowed = gate.enforce_many(
        [read.prepare({"path": "README.md"}), read.prepare({"path": "pyproject.toml"})]
    )
    assert all(decision.allowed for decision in allowed)

    with pytest.raises(ToolCallDeniedError) as captured:
        gate.enforce_many(
            [read.prepare({"path": "README.md"}), blocked.prepare({"path": "old.log"})]
        )

    assert captured.value.decision.outcome is Outcome.DENY
    assert len(records) == 4


def test_batch_rejects_invalid_or_foreign_prepared_calls_before_evaluation() -> None:
    gate = _gate()
    other_gate = _gate()
    call = gate.bind("read_file", capabilities=["resource:read"]).prepare({})
    foreign = other_gate.bind("read_file", capabilities=["resource:read"]).prepare({})

    with pytest.raises(InputValidationError, match="batch must be iterable"):
        gate.evaluate_many(None)  # type: ignore[arg-type]
    with pytest.raises(InputValidationError, match="item 1 must be a PreparedToolCall"):
        gate.evaluate_many([call, object()])  # type: ignore[list-item]
    with pytest.raises(InputValidationError, match="item 0 was prepared by a different"):
        gate.evaluate_many([foreign])
    with pytest.raises(InputValidationError, match=f"limit of {MAX_TOOL_BATCH_ITEMS}"):
        gate.evaluate_many(
            gate.prepare(
                "read_file",
                {"index": index},
                capabilities=["resource:read"],
            )
            for index in range(MAX_TOOL_BATCH_ITEMS + 1)
        )


def test_batch_rejects_repeated_call_objects_and_approval_ids() -> None:
    gate = _gate()
    read = gate.bind("read_file", capabilities=["resource:read"])
    call = read.prepare({"path": "README.md"})

    with pytest.raises(InputValidationError, match="repeats a PreparedToolCall"):
        gate.evaluate_many([call, call])

    send = gate.bind("send_message", capabilities=["external:write"])
    arguments = {"channel": "ops"}
    call_id = "send-duplicate"
    approval = ToolCallApproval(
        call_id,
        True,
        send.fingerprint(call_id, arguments),
    )
    first = send.prepare(arguments, tool_call_id=call_id, approval=approval)
    second = send.prepare(arguments, tool_call_id=call_id, approval=approval)

    with pytest.raises(InputValidationError, match="repeats approval tool_call_id"):
        gate.enforce_many([first, second])


def test_entire_batch_is_contract_validated_before_any_audit_delivery() -> None:
    contract_value = load_context_contract(_CONTRACT_PATH).to_dict()
    contract_value["fields"]["context.session_id"] = {"type": "string"}
    contract = ContextContract.from_dict(contract_value)
    records: list[AuditRecord] = []
    gate = ToolGate(load_policy(_POLICY_PATH), context_contract=contract, audit_sink=records.append)
    read = gate.bind("read_file", capabilities=["resource:read"])

    with pytest.raises(InputValidationError, match=r"batch item 1.*context.session_id"):
        gate.evaluate_many(
            [
                read.prepare({}, context={"session_id": "session-1"}),
                read.prepare({}),
            ]
        )

    assert records == []


def test_empty_prepared_batch_is_allowed_without_audit_records() -> None:
    records: list[AuditRecord] = []
    gate = _gate(records=records)

    assert gate.evaluate_many([]) == ()
    assert gate.enforce_many([]) == ()
    assert records == []


def test_direct_prepare_supports_framework_owned_registration_metadata() -> None:
    gate = _gate()
    arguments: dict[str, Any] = {"path": "README.md"}

    call = gate.prepare(
        "read_file",
        arguments,
        capabilities=["resource:read"],
        actor={"id": "coding-agent"},
    )

    assert gate.enforce_many([call])[0].outcome is Outcome.ALLOW


def test_prepared_batch_preserves_exact_call_approval_binding() -> None:
    gate = _gate()
    send = gate.bind("send_message", capabilities=["external:write"])
    arguments = {"channel": "ops", "message": "ready"}
    actor = {"id": "coding-agent"}
    call_id = "send-1"
    approval = ToolCallApproval(
        call_id,
        True,
        send.fingerprint(call_id, arguments, actor=actor),
    )

    call = send.prepare(
        arguments,
        actor=actor,
        tool_call_id=call_id,
        approval=approval,
    )

    assert gate.enforce_many([call])[0].outcome is Outcome.ALLOW
