"""Activate a reviewed policy candidate without rebuilding a live tool binding."""

from __future__ import annotations

from pathlib import Path

from samsarix_ethics import (
    PolicyRuntime,
    ToolGate,
    compose_policies,
    create_deployment_lock,
    load_context_contract,
    load_deployment_lock,
    load_policy,
)


def main() -> None:
    root = Path(__file__).parent
    baseline = load_policy(root / "policies/tool-call-baseline.json")
    baseline_contract = load_context_contract(root / "contracts/tool-call-context.json")
    baseline_lock = load_deployment_lock(root / "deployment/tool-call-baseline.lock.json")
    candidate_guardrail = load_policy(root / "policies/restricted-read-candidate-guardrail.json")
    candidate = compose_policies(
        (baseline, candidate_guardrail),
        policy_id="tool-call-baseline-restricted",
        policy_version="1.1.0-candidate",
    ).policy
    candidate_contract = load_context_contract(root / "contracts/tool-call-context-candidate.json")
    candidate_lock = create_deployment_lock(candidate, candidate_contract)
    runtime = PolicyRuntime(
        baseline,
        context_contract=baseline_contract,
        deployment_lock=baseline_lock,
    )
    read_resource = ToolGate(runtime).bind("read", capabilities=["resource:read"])
    private_context = {"data_sensitivity": "restricted"}

    before = read_resource.evaluate({}, context=private_context)
    generation = runtime.status.generation
    activated = runtime.activate(
        candidate,
        context_contract=candidate_contract,
        deployment_lock=candidate_lock,
        expected_generation=generation,
    )
    after = read_resource.evaluate({}, context=private_context)

    print(f"generation {generation}: {before.outcome.value}")
    print(f"generation {activated.generation}: {after.outcome.value}")
    if before.outcome.value != "allow" or after.outcome.value != "review":
        raise RuntimeError("checked-in rollout example no longer has its documented behavior")


if __name__ == "__main__":
    main()
