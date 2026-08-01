"""Run one allowed and one blocked tool call through the baseline policy."""

from __future__ import annotations

from pathlib import Path

from samsarix_ethics import (
    AuditRecord,
    ToolCallApproval,
    ToolCallDeniedError,
    ToolGate,
    fingerprint_tool_call,
    load_policy,
)


def main() -> None:
    root = Path(__file__).parent
    audit_records: list[AuditRecord] = []
    gate = ToolGate(
        load_policy(root / "policies/tool-call-baseline.json"),
        audit_sink=audit_records.append,
    )

    read = gate.execute(
        "read_ticket",
        {"ticket_id": "T-100"},
        lambda arguments: {"ticket_id": arguments["ticket_id"], "status": "open"},
        capabilities=["resource:read"],
        actor={"id": "support-agent"},
    )
    print(f"allowed {read.decision.decision_id}: {read.value}")

    try:
        gate.execute(
            "delete_ticket",
            {"ticket_id": "T-100"},
            lambda _arguments: print("this callback must not run"),
            capabilities=["destructive"],
            actor={"id": "support-agent"},
        )
    except ToolCallDeniedError as exc:
        print(f"blocked {exc.decision.decision_id}: {exc.decision.outcome.value}")

    delete_arguments = {"ticket_id": "T-100"}
    delete_actor = {"id": "support-agent"}
    fingerprint = fingerprint_tool_call(
        "delete-call-100",
        "delete_ticket",
        delete_arguments,
        capabilities=["destructive"],
        actor=delete_actor,
    )
    approved = gate.execute(
        "delete_ticket",
        delete_arguments,
        lambda arguments: {"deleted": arguments["ticket_id"]},
        capabilities=["destructive"],
        actor=delete_actor,
        tool_call_id="delete-call-100",
        approval=ToolCallApproval("delete-call-100", True, fingerprint),
    )
    print(f"approved {approved.decision.decision_id}: {approved.value}")

    print(f"exported {len(audit_records)} metadata-only audit records")


if __name__ == "__main__":
    main()
