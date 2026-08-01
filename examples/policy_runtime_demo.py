"""Activate a reviewed policy candidate without rebuilding a live tool binding."""

from __future__ import annotations

from pathlib import Path

from samsarix_ethics import (
    PolicyRuntime,
    ToolGate,
    compose_policies,
    create_policy_deployment,
    load_context_contract,
    load_policy,
    load_policy_deployment,
)


def main() -> None:
    root = Path(__file__).parent
    baseline_deployment = load_policy_deployment(
        root / "deployment/tool-call-baseline.deployment.json"
    )
    baseline = baseline_deployment.policy
    candidate_guardrail = load_policy(root / "policies/restricted-read-candidate-guardrail.json")
    candidate = compose_policies(
        (baseline, candidate_guardrail),
        policy_id="tool-call-baseline-restricted",
        policy_version="1.1.0-candidate",
    ).policy
    candidate_contract = load_context_contract(root / "contracts/tool-call-context-candidate.json")
    candidate_deployment = create_policy_deployment(candidate, candidate_contract)
    runtime = PolicyRuntime.from_deployment(baseline_deployment)
    read_resource = ToolGate(runtime).bind("read", capabilities=["resource:read"])
    private_context = {"data_sensitivity": "restricted"}

    before = read_resource.evaluate({}, context=private_context)
    generation = runtime.status.generation
    activated = runtime.activate_deployment(
        candidate_deployment,
        expected_generation=generation,
    )
    after = read_resource.evaluate({}, context=private_context)

    print(f"generation {generation}: {before.outcome.value}")
    print(f"generation {activated.generation}: {after.outcome.value}")
    if before.outcome.value != "allow" or after.outcome.value != "review":
        raise RuntimeError("checked-in rollout example no longer has its documented behavior")


if __name__ == "__main__":
    main()
