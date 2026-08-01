"""Policy-model validation tests."""

from __future__ import annotations

import math
from typing import Any

import pytest

from samsarix_ethics import Outcome, Policy, PolicyCondition, PolicyRule, PolicyValidationError


def test_valid_policy_is_immutable(policy_document: dict[str, Any]) -> None:
    policy = Policy.from_dict(policy_document)

    assert policy.id == "test-policy"
    assert policy.default_effect is Outcome.REVIEW
    assert [rule.id for rule in policy.rules] == ["deny-delete", "allow-read"]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda policy: policy.update(schema_version=2), "schema_version"),
        (lambda policy: policy.update(extra=True), "unknown fields"),
        (lambda policy: policy.update(default_effect="maybe"), "default_effect"),
        (lambda policy: policy.update(rules="nope"), "rules must be a JSON array"),
    ],
)
def test_invalid_top_level_policy_is_rejected(
    policy_document: dict[str, Any], mutation: Any, message: str
) -> None:
    mutation(policy_document)

    with pytest.raises(PolicyValidationError, match=message):
        Policy.from_dict(policy_document)


def test_unknown_operator_is_rejected(policy_document: dict[str, Any]) -> None:
    policy_document["rules"][0]["conditions"][0]["operator"] = "regex"

    with pytest.raises(PolicyValidationError, match="operator must be one of"):
        Policy.from_dict(policy_document)


def test_duplicate_rule_ids_are_rejected(policy_document: dict[str, Any]) -> None:
    policy_document["rules"][1]["id"] = "deny-delete"

    with pytest.raises(PolicyValidationError, match="duplicate ids"):
        Policy.from_dict(policy_document)


def test_reference_value_must_be_a_single_valid_path(policy_document: dict[str, Any]) -> None:
    policy_document["rules"][0]["conditions"][0]["value"] = {
        "$ref": "actor.tenant",
        "fallback": "root",
    }

    with pytest.raises(PolicyValidationError, match="contain only"):
        Policy.from_dict(policy_document)


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ([], "must be a JSON object"),
        ({"schema_version": 1}, "is missing"),
        (
            {
                "schema_version": 1,
                "id": "bad id",
                "version": "1",
                "default_effect": "deny",
                "rules": [],
            },
            "must be 1-128 characters",
        ),
    ],
)
def test_policy_shape_errors(document: Any, message: str) -> None:
    with pytest.raises(PolicyValidationError, match=message):
        Policy.from_dict(document)


@pytest.mark.parametrize(
    ("condition", "message"),
    [
        ({"field": "bad path!", "operator": "eq", "value": 1}, "valid dotted"),
        ({"field": "value", "operator": "eq"}, "value is required"),
        ({"field": "value", "operator": "in", "value": "read"}, "JSON array"),
        (
            {"field": "value", "operator": "eq", "value": {"$ref": "bad path!"}},
            "value.\\$ref",
        ),
    ],
)
def test_condition_shape_errors(condition: dict[str, Any], message: str) -> None:
    with pytest.raises(PolicyValidationError, match=message):
        PolicyCondition.from_dict(condition, location="condition")


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"effect": "permit"}, "effect must be one of"),
        ({"conditions": "wrong"}, "conditions must be a JSON array"),
        ({"conditions": [{}] * 33}, "limit of 32"),
        ({"message": 4}, "message must be a string"),
        ({"priority": True}, "priority must be an integer"),
    ],
)
def test_rule_shape_errors(changes: dict[str, Any], message: str) -> None:
    rule: dict[str, Any] = {"id": "rule", "effect": "allow", "conditions": []}
    rule.update(changes)
    with pytest.raises(PolicyValidationError, match=message):
        PolicyRule.from_dict(rule, index=0)


def test_policy_round_trip(policy_document: dict[str, Any]) -> None:
    policy = Policy.from_dict(policy_document)

    assert Policy.from_dict(policy.to_dict()) == policy


def test_exists_condition_serializes_without_value() -> None:
    condition = PolicyCondition.from_dict(
        {"field": "actor.id", "operator": "exists"}, location="condition"
    )

    assert condition.to_dict() == {"field": "actor.id", "operator": "exists"}


def test_exists_condition_rejects_unused_value() -> None:
    with pytest.raises(PolicyValidationError, match="value is not allowed"):
        PolicyCondition.from_dict(
            {"field": "actor.id", "operator": "exists", "value": True},
            location="condition",
        )


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (("not", "json"), "non-JSON value"),
        (math.inf, "non-finite number"),
    ],
)
def test_in_memory_policy_uses_json_contract(
    value: Any, message: str, policy_document: dict[str, Any]
) -> None:
    policy_document["rules"][0]["conditions"][0]["value"] = value

    with pytest.raises(PolicyValidationError, match=message):
        Policy.from_dict(policy_document)


def test_reference_path_length_is_bounded() -> None:
    with pytest.raises(PolicyValidationError, match="not a valid field path"):
        PolicyCondition.from_dict(
            {"field": "actor.id", "operator": "eq", "value": {"$ref": "x" * 257}},
            location="condition",
        )


def test_direct_condition_constructor_rejects_non_json_value() -> None:
    with pytest.raises(PolicyValidationError, match="non-JSON value"):
        PolicyCondition.from_dict(
            {"field": "actor.id", "operator": "eq", "value": ("not", "json")},
            location="condition",
        )


def test_direct_rule_constructor_rejects_non_string_key() -> None:
    with pytest.raises(PolicyValidationError, match="non-string object key"):
        PolicyRule.from_dict(
            {"id": "rule", "effect": "deny", "conditions": [], 1: "bad"},
            index=0,
        )


def test_membership_condition_accepts_array_reference() -> None:
    condition = PolicyCondition.from_dict(
        {"field": "action", "operator": "in", "value": {"$ref": "allowed.actions"}},
        location="condition",
    )

    assert condition.value == {"$ref": "allowed.actions"}
