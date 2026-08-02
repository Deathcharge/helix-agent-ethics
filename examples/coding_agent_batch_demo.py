"""Authorize every proposed coding-agent call before caller-owned dispatch."""

from __future__ import annotations

from pathlib import Path

from samsarix_ethics import (
    Outcome,
    PolicyRuntime,
    ToolCallApproval,
    ToolCallBlockedError,
    ToolGate,
    load_policy_deployment,
)

ROOT = Path(__file__).parent


def main() -> None:
    deployment = load_policy_deployment(ROOT / "deployment/coding-agent-baseline.deployment.json")
    gate = ToolGate(PolicyRuntime.from_deployment(deployment))
    read_file = gate.bind("read_file", capabilities=["workspace:read"])
    run_command = gate.bind(
        "run_command",
        capabilities=["process:execute", "risk:elevated"],
    )
    actor = {"id": "coding-agent"}
    trusted_context = {"workspace_contained": True}
    read_call = read_file.prepare(
        {"path": "README.md"},
        actor=actor,
        context=trusted_context,
    )
    command_arguments = {"command": "python -m pytest"}
    command_call = run_command.prepare(
        command_arguments,
        actor=actor,
        context=trusted_context,
    )

    try:
        gate.enforce_many([read_call, command_call])
    except ToolCallBlockedError as exc:
        if exc.decision.outcome is not Outcome.REVIEW:
            raise AssertionError("the unapproved elevated call must require review") from exc
        outcomes = [decision.outcome.value for decision in exc.decisions]
        print(
            "batch blocked before dispatch: "
            f"call {exc.blocking_index} requires review; outcomes={outcomes}"
        )
    else:
        raise AssertionError("the unapproved elevated call must block the batch")

    call_id = "run-tests-1"
    approval = ToolCallApproval(
        call_id,
        True,
        run_command.fingerprint(call_id, command_arguments, actor=actor),
    )
    approved_command = run_command.prepare(
        command_arguments,
        actor=actor,
        context=trusted_context,
        tool_call_id=call_id,
        approval=approval,
    )
    calls = [read_call, approved_command]
    decisions = gate.enforce_many(calls)
    expected_outcomes = (
        Outcome.ALLOW,
        Outcome.ALLOW,
    )
    if tuple(decision.outcome for decision in decisions) != expected_outcomes:
        raise AssertionError("the approved batch must allow every call")

    # The embedding framework dispatches only after the complete batch is allowed.
    dispatch_plan = [{"tool": call.tool_name, "arguments": call.arguments} for call in calls]
    print(f"authorized {len(decisions)} calls: {dispatch_plan}")


if __name__ == "__main__":
    main()
