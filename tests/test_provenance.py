"""Exact policy provenance tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Any

import pytest

from samsarix_ethics import (
    ContextContract,
    ContextContractValidationError,
    Policy,
    PolicyEngine,
    PolicyValidationError,
    fingerprint_context_contract,
    fingerprint_policy,
)


def test_policy_fingerprint_has_stable_known_vector() -> None:
    policy = Policy.from_dict(
        {
            "schema_version": 1,
            "id": "fingerprint-vector",
            "version": "2026.08",
            "description": "Unicode snow: 雪",
            "default_effect": "deny",
            "rules": [
                {
                    "id": "structured",
                    "effect": "allow",
                    "priority": 7,
                    "message": "Exact vector.",
                    "conditions": [
                        {
                            "field": "value",
                            "operator": "eq",
                            "value": [1, 1.25, {"β": "雪"}],
                        }
                    ],
                }
            ],
        }
    )

    assert fingerprint_policy(policy) == (
        "v1:sha256:764ffd9940d737d655e7bd8aea747b2c74281ca165040bcf1018cc07aa4c9271"
    )


def test_policy_fingerprint_canonicalizes_object_key_order(
    policy_document: dict[str, Any],
) -> None:
    reordered = {
        "rules": [
            {
                "priority": rule["priority"],
                "message": rule["message"],
                "conditions": [
                    {
                        "value": condition["value"],
                        "operator": condition["operator"],
                        "field": condition["field"],
                    }
                    for condition in rule["conditions"]
                ],
                "effect": rule["effect"],
                "id": rule["id"],
            }
            for rule in policy_document["rules"]
        ],
        "default_effect": policy_document["default_effect"],
        "description": policy_document["description"],
        "version": policy_document["version"],
        "id": policy_document["id"],
        "schema_version": policy_document["schema_version"],
    }

    assert fingerprint_policy(Policy.from_dict(reordered)) == fingerprint_policy(
        Policy.from_dict(policy_document)
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update(id="another-policy"),
        lambda value: value.update(version="2"),
        lambda value: value.update(description="Changed documentation."),
        lambda value: value.update(default_effect="deny"),
        lambda value: value["rules"][0].update(effect="review"),
        lambda value: value["rules"][0].update(message="Changed reason."),
        lambda value: value["rules"][0].update(priority=99),
        lambda value: value["rules"][0]["conditions"][0].update(value="write"),
        lambda value: value.update(rules=list(reversed(value["rules"]))),
    ],
)
def test_policy_fingerprint_changes_with_exact_policy_content(
    policy_document: dict[str, Any], mutation: Any
) -> None:
    changed = deepcopy(policy_document)
    mutation(changed)

    assert fingerprint_policy(Policy.from_dict(changed)) != fingerprint_policy(
        Policy.from_dict(policy_document)
    )


def test_engine_reuses_policy_fingerprint_in_every_decision(
    policy_document: dict[str, Any],
) -> None:
    policy = Policy.from_dict(policy_document)
    engine = PolicyEngine(policy)

    first, second = engine.evaluate_many(
        [{"action": {"operation": "read"}}, {"action": {"operation": "delete"}}]
    )

    assert engine.policy_fingerprint == fingerprint_policy(policy)
    assert first.policy_fingerprint == engine.policy_fingerprint
    assert second.policy_fingerprint == engine.policy_fingerprint
    assert first.to_dict()["policy_fingerprint"] == engine.policy_fingerprint


def test_policy_fingerprint_rejects_wrong_type_and_invalid_direct_model(
    policy_document: dict[str, Any],
) -> None:
    with pytest.raises(TypeError, match="policy must be a Policy"):
        fingerprint_policy(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="policy must be a Policy"):
        PolicyEngine(object())  # type: ignore[arg-type]

    malformed = replace(Policy.from_dict(policy_document), description=object())  # type: ignore[arg-type]
    with pytest.raises(PolicyValidationError, match="cannot be fingerprinted"):
        fingerprint_policy(malformed)


def test_context_contract_fingerprint_has_stable_known_vector() -> None:
    contract = ContextContract.from_dict(
        {
            "context_contract_version": 1,
            "id": "fingerprint-vector",
            "version": "2026.08",
            "description": "Unicode snow: 雪",
            "fields": {
                "action": {"type": "object"},
                "action.score": {"type": "number", "required": False},
                "action.tags": {"type": "array", "items": "string"},
            },
        }
    )

    assert fingerprint_context_contract(contract) == (
        "v1:sha256:c9151569038cdf98ad03d9adbefeb2887db5585e8a88a4ce9091a2e2f0874d42"
    )


def test_context_contract_fingerprint_is_canonical_and_content_sensitive() -> None:
    value = {
        "context_contract_version": 1,
        "id": "canonical",
        "version": "1",
        "fields": {
            "action": {"type": "object"},
            "action.operation": {"type": "string"},
        },
    }
    reordered = {
        "fields": {
            "action.operation": {"required": True, "type": "string"},
            "action": {"required": True, "type": "object"},
        },
        "version": "1",
        "id": "canonical",
        "context_contract_version": 1,
    }
    changed = deepcopy(value)
    changed["description"] = "changed"

    assert fingerprint_context_contract(
        ContextContract.from_dict(value)
    ) == fingerprint_context_contract(ContextContract.from_dict(reordered))
    assert fingerprint_context_contract(
        ContextContract.from_dict(value)
    ) != fingerprint_context_contract(ContextContract.from_dict(changed))


def test_context_contract_fingerprint_rejects_invalid_models() -> None:
    with pytest.raises(TypeError, match="contract must be"):
        fingerprint_context_contract(object())  # type: ignore[arg-type]
    malformed = replace(
        ContextContract.from_dict(
            {
                "context_contract_version": 1,
                "id": "malformed",
                "version": "1",
                "fields": {},
            }
        ),
        description=object(),  # type: ignore[arg-type]
    )
    with pytest.raises(ContextContractValidationError, match="cannot be fingerprinted"):
        fingerprint_context_contract(malformed)
