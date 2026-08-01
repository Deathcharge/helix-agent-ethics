"""Run one allowed and one blocked tool call through the baseline policy."""

from __future__ import annotations

from pathlib import Path

from samsarix_ethics import ToolCallDeniedError, ToolGate, load_policy


def main() -> None:
    root = Path(__file__).parent
    gate = ToolGate(load_policy(root / "policies/tool-call-baseline.json"))

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


if __name__ == "__main__":
    main()
