"""Exact-content deployment lock tests."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, ValidationError  # type: ignore[import-untyped]

from samsarix_ethics import (
    DEPLOYMENT_LOCK_VERSION,
    MAX_DEPLOYMENT_LOCK_BYTES,
    ContextContract,
    DeploymentLock,
    DeploymentLockArtifact,
    DeploymentLockValidationError,
    Outcome,
    Policy,
    PolicyEngine,
    ToolGate,
    create_deployment_lock,
    get_deployment_lock_schema,
    load_context_contract,
    load_deployment_lock,
    load_policy,
    verify_deployment_lock,
)


def _policy() -> Policy:
    return Policy.from_dict(
        {
            "schema_version": 1,
            "id": "locked-policy",
            "version": "1.0.0",
            "default_effect": "deny",
            "rules": [
                {
                    "id": "allow-read",
                    "effect": "allow",
                    "conditions": [
                        {"field": "action.operation", "operator": "eq", "value": "read"}
                    ],
                }
            ],
        }
    )


def _contract() -> ContextContract:
    return ContextContract.from_dict(
        {
            "context_contract_version": 1,
            "id": "locked-context",
            "version": "1.0.0",
            "fields": {
                "action": {"type": "object"},
                "action.operation": {"type": "string"},
            },
        }
    )


def test_deployment_lock_round_trips_with_exact_artifacts() -> None:
    policy = _policy()
    contract = _contract()
    lock = create_deployment_lock(policy, contract)

    assert lock.deployment_lock_version == DEPLOYMENT_LOCK_VERSION == 1
    assert lock.policy.id == policy.id
    assert lock.policy.fingerprint.startswith("v1:sha256:")
    assert lock.context_contract is not None
    assert lock.context_contract.id == contract.id
    assert DeploymentLock.from_dict(lock.to_dict()) == lock
    verify_deployment_lock(lock, policy, contract)


def test_policy_only_lock_requires_context_absence() -> None:
    policy = _policy()
    lock = create_deployment_lock(policy)

    assert lock.context_contract is None
    verify_deployment_lock(lock, policy)
    with pytest.raises(DeploymentLockValidationError, match="presence does not match"):
        verify_deployment_lock(lock, policy, _contract())
    with pytest.raises(DeploymentLockValidationError, match="presence does not match"):
        verify_deployment_lock(create_deployment_lock(policy, _contract()), policy)


def test_lock_rejects_changed_policy_or_contract_content() -> None:
    policy = _policy()
    contract = _contract()
    lock = create_deployment_lock(policy, contract)
    changed_policy_value = policy.to_dict()
    changed_policy_value["description"] = "same labels, different content"
    changed_contract_value = contract.to_dict()
    changed_contract_value["description"] = "same labels, different content"

    with pytest.raises(DeploymentLockValidationError, match="does not match the policy"):
        verify_deployment_lock(lock, Policy.from_dict(changed_policy_value), contract)
    with pytest.raises(DeploymentLockValidationError, match="does not match the context contract"):
        verify_deployment_lock(
            lock,
            policy,
            ContextContract.from_dict(changed_contract_value),
        )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda value: value.update(extra=True), "unknown fields"),
        (lambda value: value.update(deployment_lock_version=True), "must be 1"),
        (lambda value: value.pop("policy"), "is missing: policy"),
        (lambda value: value.update(policy=[]), "policy must be a JSON object"),
        (lambda value: value["policy"].pop("id"), "is missing: id"),
        (lambda value: value["policy"].update(id="bad id"), "must be a 1-128"),
        (
            lambda value: value["policy"].update(fingerprint="sha256:not-versioned"),
            "must use the v1 SHA-256",
        ),
        (lambda value: value.update(context_contract=[]), "must be a JSON object"),
    ],
)
def test_deployment_lock_parser_rejects_malformed_values(mutate: Any, message: str) -> None:
    value = create_deployment_lock(_policy(), _contract()).to_dict()
    mutate(value)

    with pytest.raises(DeploymentLockValidationError, match=message):
        DeploymentLock.from_dict(value)


def test_deployment_lock_parser_rejects_non_json_and_non_object() -> None:
    value = create_deployment_lock(_policy()).to_dict()
    value["policy"]["id"] = object()
    with pytest.raises(DeploymentLockValidationError, match="non-JSON value"):
        DeploymentLock.from_dict(value)
    with pytest.raises(DeploymentLockValidationError, match="must be a JSON object"):
        DeploymentLock.from_dict([])


def test_lock_schema_matches_runtime_shape() -> None:
    validator = Draft202012Validator(get_deployment_lock_schema())
    valid = create_deployment_lock(_policy(), _contract()).to_dict()
    validator.validate(valid)
    invalid = deepcopy(valid)
    invalid["policy"]["fingerprint"] = "not-a-fingerprint"

    with pytest.raises(ValidationError):
        validator.validate(invalid)


def test_engine_and_gate_verify_lock_before_evaluation() -> None:
    policy = _policy()
    contract = _contract()
    lock = create_deployment_lock(policy, contract)
    engine = PolicyEngine(policy, context_contract=contract, deployment_lock=lock)
    gate = ToolGate(policy, context_contract=contract, deployment_lock=lock)

    assert engine.deployment_lock is lock
    assert engine.context_contract_fingerprint == lock.context_contract.fingerprint  # type: ignore[union-attr]
    assert gate.deployment_lock is lock
    assert gate.bind("read").deployment_lock is lock
    assert gate.context_contract_fingerprint == engine.context_contract_fingerprint
    assert gate.bind("read").context_contract_fingerprint == engine.context_contract_fingerprint
    assert engine.evaluate({"action": {"operation": "read"}}).outcome is Outcome.ALLOW
    with pytest.raises(TypeError, match="deployment_lock"):
        PolicyEngine(policy, deployment_lock=object())  # type: ignore[arg-type]


def test_loader_bounds_and_wraps_file_errors(tmp_path: Path, write_json: Any) -> None:
    path = write_json("deployment.lock.json", create_deployment_lock(_policy()).to_dict())
    assert load_deployment_lock(path).policy.id == "locked-policy"

    oversized = tmp_path / "oversized.lock.json"
    oversized.write_bytes(b"{" + b" " * MAX_DEPLOYMENT_LOCK_BYTES + b"}")
    with pytest.raises(DeploymentLockValidationError, match="exceeds the byte limit"):
        load_deployment_lock(oversized)
    with pytest.raises(DeploymentLockValidationError, match="cannot read deployment lock"):
        load_deployment_lock(tmp_path / "missing.lock.json")


def test_deployment_helpers_reject_wrong_argument_types() -> None:
    with pytest.raises(TypeError, match="policy must be"):
        create_deployment_lock(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="context_contract"):
        create_deployment_lock(_policy(), object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="lock must be"):
        verify_deployment_lock(object(), _policy())  # type: ignore[arg-type]


def test_direct_deployment_lock_models_remain_strict() -> None:
    with pytest.raises(DeploymentLockValidationError, match="artifact id"):
        DeploymentLockArtifact("bad id", "1", "v1:sha256:" + "0" * 64)
    with pytest.raises(DeploymentLockValidationError, match="artifact fingerprint"):
        DeploymentLockArtifact("valid", "1", "not-a-fingerprint")
    artifact = DeploymentLockArtifact("valid", "1", "v1:sha256:" + "0" * 64)
    with pytest.raises(DeploymentLockValidationError, match="deployment_lock_version"):
        DeploymentLock(2, artifact, None)
    with pytest.raises(DeploymentLockValidationError, match="policy must be"):
        DeploymentLock(1, object(), None)  # type: ignore[arg-type]
    with pytest.raises(DeploymentLockValidationError, match="context_contract must be"):
        DeploymentLock(1, artifact, object())  # type: ignore[arg-type]


def test_schema_accessor_returns_fresh_values() -> None:
    changed = get_deployment_lock_schema()
    changed["title"] = "changed"

    assert get_deployment_lock_schema()["title"] != "changed"


def test_checked_in_tool_policy_deployment_lock_is_current() -> None:
    root = Path(__file__).parents[1]
    policy = load_policy(root / "examples/policies/tool-call-baseline.json")
    contract = load_context_contract(root / "examples/contracts/tool-call-context.json")
    lock = load_deployment_lock(root / "examples/deployment/tool-call-baseline.lock.json")

    verify_deployment_lock(lock, policy, contract)
