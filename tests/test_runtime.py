"""Atomic live policy runtime tests."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier, Event
from typing import Any

import pytest
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from samsarix_ethics import (
    POLICY_RUNTIME_STATUS_VERSION,
    ContextContract,
    DeploymentLockValidationError,
    Outcome,
    Policy,
    PolicyActivationError,
    PolicyRuntime,
    ToolGate,
    create_deployment_lock,
    get_policy_runtime_status_schema,
)


def _policy(
    version: str,
    effect: str,
    *,
    message: str = "Policy message that status must not disclose.",
) -> Policy:
    return Policy.from_dict(
        {
            "schema_version": 1,
            "id": "live-policy",
            "version": version,
            "default_effect": "review",
            "description": "Private policy description.",
            "rules": [
                {
                    "id": f"{effect}-read",
                    "effect": effect,
                    "message": message,
                    "conditions": [
                        {"field": "action.operation", "operator": "eq", "value": "read"}
                    ],
                }
            ],
        }
    )


def _contract(version: str = "1") -> ContextContract:
    return ContextContract.from_dict(
        {
            "context_contract_version": 1,
            "id": "live-context",
            "version": version,
            "description": "Private contract description.",
            "fields": {
                "action": {"type": "object"},
                "action.operation": {"type": "string"},
            },
        }
    )


def test_initial_status_binds_exact_active_artifacts_without_policy_content() -> None:
    policy = _policy("1", "allow")
    contract = _contract()
    lock = create_deployment_lock(policy, contract)
    runtime = PolicyRuntime(policy, context_contract=contract, deployment_lock=lock)

    status = runtime.status
    serialized = status.to_dict()

    assert status.runtime_status_version == POLICY_RUNTIME_STATUS_VERSION == 1
    assert status.generation == 1
    assert status.policy_id == "live-policy"
    assert status.policy_fingerprint == lock.policy.fingerprint
    assert status.context_contract_id == "live-context"
    assert status.context_contract_fingerprint == lock.context_contract.fingerprint  # type: ignore[union-attr]
    assert status.deployment_lock_verified is True
    assert runtime.policy_fingerprint == status.policy_fingerprint
    assert runtime.context_contract is contract
    assert runtime.context_contract_fingerprint == status.context_contract_fingerprint
    assert runtime.deployment_lock is lock
    assert serialized["policy"]["version"] == "1"
    assert serialized["context_contract"]["version"] == "1"
    assert serialized["deployment_lock_verified"] is True
    payload = json.dumps(serialized)
    assert "Private policy description" not in payload
    assert "Policy message" not in payload
    assert "action.operation" not in payload
    Draft202012Validator(get_policy_runtime_status_schema()).validate(serialized)


def test_successful_activation_changes_behavior_and_supports_rollback() -> None:
    approved = _policy("1", "allow")
    restrictive = _policy("2", "deny")
    runtime = PolicyRuntime(approved)
    initial = runtime.status

    assert runtime.evaluate({"action": {"operation": "read"}}).outcome is Outcome.ALLOW
    activated = runtime.activate(restrictive, expected_generation=initial.generation)

    assert activated.generation == 2
    assert activated.policy_version == "2"
    assert activated.activated_at >= initial.activated_at
    assert runtime.status is activated
    assert runtime.evaluate({"action": {"operation": "read"}}).outcome is Outcome.DENY

    rolled_back = runtime.activate(approved, expected_generation=2)
    assert rolled_back.generation == 3
    assert rolled_back.policy_version == "1"
    assert runtime.evaluate({"action": {"operation": "read"}}).outcome is Outcome.ALLOW


def test_failed_candidate_validation_preserves_last_known_good_generation() -> None:
    approved = _policy("1", "allow")
    runtime = PolicyRuntime(approved)
    before = runtime.status
    candidate = _policy("2", "deny")
    wrong_lock = create_deployment_lock(_policy("3", "deny"))

    with pytest.raises(DeploymentLockValidationError, match="does not match the policy"):
        runtime.activate(candidate, deployment_lock=wrong_lock, expected_generation=1)

    assert runtime.status is before
    assert runtime.policy is approved
    assert runtime.evaluate({"action": {"operation": "read"}}).outcome is Outcome.ALLOW


def test_stale_compare_and_swap_preserves_newer_generation() -> None:
    runtime = PolicyRuntime(_policy("1", "allow"))
    current = runtime.activate(_policy("2", "deny"), expected_generation=1)

    with pytest.raises(PolicyActivationError, match=r"expected 1, active 2"):
        runtime.activate(_policy("3", "allow"), expected_generation=1)

    assert runtime.status is current
    assert runtime.status.policy_version == "2"
    assert runtime.evaluate({"action": {"operation": "read"}}).outcome is Outcome.DENY


@pytest.mark.parametrize("value", [True, False, 0, -1, 1.5, "1"])
def test_expected_generation_must_be_a_positive_integer(value: Any) -> None:
    runtime = PolicyRuntime(_policy("1", "allow"))

    with pytest.raises(ValueError, match="positive integer"):
        runtime.activate(_policy("2", "deny"), expected_generation=value)

    assert runtime.status.generation == 1


def test_only_one_concurrent_compare_and_swap_can_win() -> None:
    runtime = PolicyRuntime(_policy("1", "allow"))
    barrier = Barrier(2)

    def activate(version: str) -> str:
        barrier.wait()
        try:
            return runtime.activate(_policy(version, "deny"), expected_generation=1).policy_version
        except PolicyActivationError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(activate, ("2a", "2b")))

    assert results.count("conflict") == 1
    assert runtime.status.generation == 2
    assert runtime.status.policy_version in {"2a", "2b"}


def test_in_flight_evaluation_finishes_on_its_captured_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = PolicyRuntime(_policy("1", "allow"))
    old_engine = runtime._engine
    original_evaluate = old_engine.evaluate
    started = Event()
    release = Event()

    def delayed(context: Any) -> Any:
        started.set()
        assert release.wait(timeout=5)
        return original_evaluate(context)

    monkeypatch.setattr(old_engine, "evaluate", delayed)
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(runtime.evaluate, {"action": {"operation": "read"}})
        assert started.wait(timeout=5)
        runtime.activate(_policy("2", "deny"), expected_generation=1)
        release.set()
        old_decision = pending.result(timeout=5)

    assert old_decision.outcome is Outcome.ALLOW
    assert old_decision.policy_version == "1"
    assert runtime.evaluate({"action": {"operation": "read"}}).outcome is Outcome.DENY


def test_batch_pins_one_generation_during_activation(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = PolicyRuntime(_policy("1", "allow"))
    old_engine = runtime._engine
    original_evaluate = old_engine.evaluate
    first_started = Event()
    release = Event()
    call_count = 0

    def delayed_first(context: Any) -> Any:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            first_started.set()
            assert release.wait(timeout=5)
        return original_evaluate(context)

    monkeypatch.setattr(old_engine, "evaluate", delayed_first)
    contexts = [{"action": {"operation": "read"}} for _ in range(3)]
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(runtime.evaluate_many, contexts)
        assert first_started.wait(timeout=5)
        runtime.activate(_policy("2", "deny"), expected_generation=1)
        release.set()
        decisions = pending.result(timeout=5)

    assert {decision.policy_version for decision in decisions} == {"1"}
    assert {decision.outcome for decision in decisions} == {Outcome.ALLOW}


def test_runtime_backed_gate_and_binding_follow_atomic_activations() -> None:
    records: list[Any] = []
    runtime = PolicyRuntime(_policy("1", "allow"))
    gate = ToolGate(runtime, audit_sink=records.append)
    read = gate.bind("read", capabilities=["resource:read"])

    assert gate.runtime_status is runtime.status
    assert read.runtime_status is runtime.status
    assert read.evaluate({}).outcome is Outcome.ALLOW
    assert len(records) == 1

    runtime.activate(_policy("2", "deny"), expected_generation=1)

    assert gate.policy.version == "2"
    assert read.policy.version == "2"
    assert gate.runtime_status is runtime.status
    assert read.evaluate({}).outcome is Outcome.DENY
    assert read.explain({}).outcome is Outcome.DENY
    assert len(records) == 2


def test_runtime_owns_contract_and_lock_for_runtime_backed_gate() -> None:
    policy = _policy("1", "allow")
    contract = _contract()
    lock = create_deployment_lock(policy, contract)
    runtime = PolicyRuntime(policy, context_contract=contract, deployment_lock=lock)
    gate = ToolGate(runtime)

    assert gate.context_contract is contract
    assert gate.deployment_lock is lock
    assert gate.runtime_status is not None
    assert gate.runtime_status.deployment_lock_verified is True
    with pytest.raises(ValueError, match="configured on PolicyRuntime"):
        ToolGate(runtime, context_contract=contract)
    with pytest.raises(ValueError, match="configured on PolicyRuntime"):
        ToolGate(runtime, deployment_lock=lock)


def test_policy_only_status_uses_null_contract_and_unverified_lock_marker() -> None:
    runtime = PolicyRuntime(_policy("1", "allow"))

    assert runtime.status.context_contract_id is None
    assert runtime.status.context_contract_version is None
    assert runtime.status.context_contract_fingerprint is None
    assert runtime.status.deployment_lock_verified is False
    assert runtime.status.to_dict()["context_contract"] is None


def test_runtime_public_type_contracts_and_fresh_schema() -> None:
    with pytest.raises(TypeError, match="policy must be a Policy"):
        PolicyRuntime(object())  # type: ignore[arg-type]
    runtime = PolicyRuntime(_policy("1", "allow"))
    static_gate = ToolGate(_policy("static", "allow"))
    assert static_gate.runtime_status is None
    assert static_gate.bind("read").runtime_status is None
    with pytest.raises(TypeError, match="policy must be a Policy"):
        runtime.activate(object())  # type: ignore[arg-type]

    changed = deepcopy(get_policy_runtime_status_schema())
    changed["title"] = "changed"
    assert get_policy_runtime_status_schema()["title"] != "changed"
