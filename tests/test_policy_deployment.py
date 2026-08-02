"""Single-file exact policy deployment tests."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, ValidationError  # type: ignore[import-untyped]

import samsarix_ethics.io as io_module
from samsarix_ethics import (
    MAX_POLICY_DEPLOYMENT_BYTES,
    POLICY_DEPLOYMENT_VERSION,
    ContextContract,
    Outcome,
    Policy,
    PolicyActivationError,
    PolicyDeployment,
    PolicyDeploymentValidationError,
    PolicyRuntime,
    ToolGate,
    create_policy_deployment,
    get_policy_deployment_schema,
    load_context_contract,
    load_policy,
    load_policy_deployment,
    write_policy_deployment,
)


def _policy(version: str = "1", effect: str = "allow") -> Policy:
    return Policy.from_dict(
        {
            "schema_version": 1,
            "id": "deployment-policy",
            "version": version,
            "default_effect": "review",
            "description": "Deployment policy content.",
            "rules": [
                {
                    "id": f"{effect}-read",
                    "effect": effect,
                    "message": f"{effect.title()} read.",
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
            "id": "deployment-context",
            "version": version,
            "fields": {
                "action": {"type": "object"},
                "action.operation": {"type": "string"},
            },
        }
    )


def test_deployment_round_trips_and_detaches_complete_exact_artifacts() -> None:
    policy = _policy()
    contract = _contract()
    deployment = create_policy_deployment(policy, contract)
    serialized = deployment.to_dict()

    assert deployment.policy_deployment_version == POLICY_DEPLOYMENT_VERSION == 1
    assert deployment.policy is policy
    assert deployment.context_contract is contract
    assert deployment.deployment_lock.policy.id == policy.id
    assert deployment.deployment_lock.context_contract is not None
    assert deployment.deployment_lock.context_contract.id == contract.id
    assert PolicyDeployment.from_dict(serialized) == deployment

    serialized["policy"]["description"] = "changed detached copy"
    serialized["context_contract"]["version"] = "changed"
    serialized["deployment_lock"]["policy"]["id"] = "changed"
    assert deployment.policy.description == "Deployment policy content."
    assert deployment.context_contract.version == "1"
    assert deployment.deployment_lock.policy.id == "deployment-policy"


def test_policy_only_deployment_requires_and_verifies_a_lock() -> None:
    deployment = create_policy_deployment(_policy())

    assert deployment.context_contract is None
    assert deployment.deployment_lock.context_contract is None
    assert deployment.to_dict()["context_contract"] is None
    assert PolicyDeployment.from_dict(deployment.to_dict()) == deployment


def test_deployment_rejects_policy_contract_incompatibility_before_transport() -> None:
    incomplete_contract = ContextContract.from_dict(
        {
            "context_contract_version": 1,
            "id": "incomplete-context",
            "version": "1",
            "fields": {"action": {"type": "object"}},
        }
    )

    with pytest.raises(PolicyDeploymentValidationError, match="contract compatibility failed"):
        create_policy_deployment(_policy(), incomplete_contract)


def test_parser_rejects_mismatched_policy_or_contract_content() -> None:
    value = create_policy_deployment(_policy(), _contract()).to_dict()
    changed_policy = deepcopy(value)
    changed_policy["policy"]["description"] = "changed without lock update"
    changed_contract = deepcopy(value)
    changed_contract["context_contract"]["version"] = "2"

    with pytest.raises(PolicyDeploymentValidationError, match="does not match the policy"):
        PolicyDeployment.from_dict(changed_policy)
    with pytest.raises(PolicyDeploymentValidationError, match="context contract"):
        PolicyDeployment.from_dict(changed_contract)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda value: value.update(extra=True), "unknown fields"),
        (lambda value: value.pop("policy"), "is missing: policy"),
        (lambda value: value.update(policy_deployment_version=True), "must be 1"),
        (lambda value: value.update(policy=[]), "invalid policy"),
        (lambda value: value.update(context_contract=[]), "invalid context contract"),
        (lambda value: value.update(deployment_lock=[]), "invalid deployment lock"),
    ],
)
def test_parser_rejects_malformed_deployment_shapes(mutate: Any, message: str) -> None:
    value = create_policy_deployment(_policy(), _contract()).to_dict()
    mutate(value)

    with pytest.raises(PolicyDeploymentValidationError, match=message):
        PolicyDeployment.from_dict(value)


def test_parser_rejects_non_json_and_non_object_values() -> None:
    value = create_policy_deployment(_policy()).to_dict()
    value["deployment_lock"]["policy"]["id"] = object()

    with pytest.raises(PolicyDeploymentValidationError, match="non-JSON value"):
        PolicyDeployment.from_dict(value)
    with pytest.raises(PolicyDeploymentValidationError, match="must be a JSON object"):
        PolicyDeployment.from_dict([])


def test_schema_is_self_contained_and_matches_runtime_semantics() -> None:
    schema = get_policy_deployment_schema()
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    valid = create_policy_deployment(_policy(), _contract()).to_dict()
    validator.validate(valid)
    invalid = deepcopy(valid)
    invalid["policy"]["rules"][0]["effect"] = "execute"

    with pytest.raises(ValidationError):
        validator.validate(invalid)


def test_schema_accessor_returns_fresh_nested_schemas() -> None:
    changed = get_policy_deployment_schema()
    changed["$defs"]["policy"]["title"] = "changed"

    assert get_policy_deployment_schema()["$defs"]["policy"]["title"] != "changed"


def test_bounded_loader_and_atomic_writer_round_trip(tmp_path: Path) -> None:
    deployment = create_policy_deployment(_policy(), _contract())
    path = tmp_path / "policy.deployment.json"

    assert write_policy_deployment(path, deployment) == path.resolve()
    assert load_policy_deployment(path) == deployment
    with pytest.raises(PolicyDeploymentValidationError, match="refusing to overwrite"):
        write_policy_deployment(path, deployment)
    assert write_policy_deployment(path, deployment, force=True) == path.resolve()

    missing_parent = tmp_path / "missing" / "policy.deployment.json"
    with pytest.raises(PolicyDeploymentValidationError, match="parent directory"):
        write_policy_deployment(missing_parent, deployment)


def test_loader_rejects_duplicates_oversize_and_missing_files(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.deployment.json"
    duplicate.write_text(
        '{"policy_deployment_version":1,"policy_deployment_version":1}',
        encoding="utf-8",
    )
    oversized = tmp_path / "oversized.deployment.json"
    oversized.write_bytes(b"{" + b" " * MAX_POLICY_DEPLOYMENT_BYTES + b"}")

    with pytest.raises(PolicyDeploymentValidationError, match="duplicate object key"):
        load_policy_deployment(duplicate)
    with pytest.raises(PolicyDeploymentValidationError, match="exceeds the byte limit"):
        load_policy_deployment(oversized)
    with pytest.raises(PolicyDeploymentValidationError, match="cannot read policy deployment"):
        load_policy_deployment(tmp_path / "missing.deployment.json")


def test_deployment_write_does_not_replace_a_concurrent_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "concurrent.deployment.json"

    def collide(source: str, destination: str | Path) -> None:
        del source
        Path(destination).write_text("concurrent owner", encoding="utf-8")
        raise FileExistsError

    monkeypatch.setattr(io_module.os, "link", collide)
    with pytest.raises(PolicyDeploymentValidationError, match="refusing to overwrite"):
        write_policy_deployment(path, create_policy_deployment(_policy()))

    assert path.read_text(encoding="utf-8") == "concurrent owner"
    assert list(tmp_path.glob(".concurrent.deployment.json.*")) == []


def test_runtime_constructs_and_activates_complete_deployments() -> None:
    baseline = create_policy_deployment(_policy("1", "allow"), _contract("1"))
    candidate = create_policy_deployment(_policy("2", "deny"), _contract("2"))
    runtime = PolicyRuntime.from_deployment(baseline)
    gate = ToolGate(runtime).bind("read")

    assert runtime.status.generation == 1
    assert runtime.status.deployment_lock_verified is True
    assert runtime.context_contract.version == "1"  # type: ignore[union-attr]
    assert gate.evaluate({}).outcome is Outcome.ALLOW

    status = runtime.activate_deployment(candidate, expected_generation=1)
    assert status.generation == 2
    assert status.policy_version == "2"
    assert status.context_contract_version == "2"
    assert status.deployment_lock_verified is True
    assert gate.evaluate({}).outcome is Outcome.DENY

    with pytest.raises(PolicyActivationError, match="expected 1, active 2"):
        runtime.activate_deployment(baseline, expected_generation=1)
    assert runtime.status is status


def test_public_constructors_reject_wrong_argument_types() -> None:
    policy = _policy()
    lock = create_policy_deployment(policy).deployment_lock

    with pytest.raises(TypeError, match="policy must be"):
        create_policy_deployment(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="context_contract"):
        create_policy_deployment(policy, object())  # type: ignore[arg-type]
    with pytest.raises(PolicyDeploymentValidationError, match="policy_deployment_version"):
        PolicyDeployment(2, policy, None, lock)
    with pytest.raises(PolicyDeploymentValidationError, match="policy must be"):
        PolicyDeployment(1, object(), None, lock)  # type: ignore[arg-type]
    with pytest.raises(PolicyDeploymentValidationError, match="context_contract must be"):
        PolicyDeployment(1, policy, object(), lock)  # type: ignore[arg-type]
    with pytest.raises(PolicyDeploymentValidationError, match="deployment_lock must be"):
        PolicyDeployment(1, policy, None, object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="deployment must be"):
        write_policy_deployment("unused", object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="deployment must be"):
        PolicyRuntime.from_deployment(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="deployment must be"):
        PolicyRuntime(policy).activate_deployment(object())  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("stem", "contract_stem"),
    [
        ("tool-call-baseline", "tool-call-context"),
        ("coding-agent-baseline", "coding-agent-tool-context"),
    ],
)
def test_checked_in_tool_call_deployment_is_exact_and_current(
    stem: str, contract_stem: str
) -> None:
    root = Path(__file__).parents[1]
    expected = create_policy_deployment(
        load_policy(root / f"examples/policies/{stem}.json"),
        load_context_contract(root / f"examples/contracts/{contract_stem}.json"),
    )

    assert load_policy_deployment(root / f"examples/deployment/{stem}.deployment.json") == expected
