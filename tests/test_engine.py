"""Real policy-evaluation tests."""

from __future__ import annotations

import math
from itertools import repeat
from typing import Any

import pytest

from samsarix_ethics import (
    MAX_BATCH_ITEMS,
    EvaluationError,
    InputValidationError,
    Outcome,
    Policy,
    PolicyEngine,
)


def test_explicit_allow(policy_document: dict[str, Any]) -> None:
    decision = PolicyEngine(Policy.from_dict(policy_document)).evaluate(
        {"action": {"operation": "read"}}
    )

    assert decision.allowed is True
    assert decision.outcome is Outcome.ALLOW
    assert decision.matched_rules == ("allow-read",)
    assert decision.reasons == ("Read is allowed.",)
    assert decision.to_dict()["matched_rules"] == ["allow-read"]
    assert decision.to_dict()["warnings"] == []
    assert decision.to_dict()["reasons"] == ["Read is allowed."]


def test_boolean_approval_does_not_accept_integer_one() -> None:
    policy = Policy.from_dict(
        {
            "schema_version": 1,
            "id": "strict-types",
            "version": "1",
            "default_effect": "deny",
            "rules": [
                {
                    "id": "allow-approved",
                    "effect": "allow",
                    "conditions": [
                        {"field": "approved", "operator": "eq", "value": True},
                        {"field": "roles", "operator": "contains", "value": True},
                    ],
                }
            ],
        }
    )

    decision = PolicyEngine(policy).evaluate({"approved": 1, "roles": [1]})

    assert decision.outcome is Outcome.DENY


def test_nested_json_arrays_and_objects_compare_after_policy_freezing() -> None:
    policy = Policy.from_dict(
        {
            "schema_version": 1,
            "id": "structured-equality",
            "version": "1",
            "default_effect": "deny",
            "rules": [
                {
                    "id": "allow-structured",
                    "effect": "allow",
                    "conditions": [
                        {
                            "field": "value",
                            "operator": "eq",
                            "value": [1, {"enabled": True}],
                        }
                    ],
                }
            ],
        }
    )

    decision = PolicyEngine(policy).evaluate({"value": [1.0, {"enabled": True}]})

    assert decision.outcome is Outcome.ALLOW


def test_deny_overrides_allow(policy_document: dict[str, Any]) -> None:
    policy_document["rules"][1]["conditions"] = []

    decision = PolicyEngine(Policy.from_dict(policy_document)).evaluate(
        {"action": {"operation": "delete"}}
    )

    assert decision.outcome is Outcome.DENY
    assert decision.allowed is False
    assert decision.matched_rules == ("deny-delete", "allow-read")
    assert decision.reasons == ("Delete is denied.",)


def test_no_match_uses_review_default(policy_document: dict[str, Any]) -> None:
    decision = PolicyEngine(Policy.from_dict(policy_document)).evaluate(
        {"action": {"operation": "write"}}
    )

    assert decision.outcome is Outcome.REVIEW
    assert decision.allowed is False
    assert decision.reasons == ("No decisive rule matched; policy default is 'review'.",)


def test_cross_field_reference() -> None:
    policy = Policy.from_dict(
        {
            "schema_version": 1,
            "id": "tenant-boundary",
            "version": "1",
            "default_effect": "deny",
            "rules": [
                {
                    "id": "allow-same-tenant",
                    "effect": "allow",
                    "conditions": [
                        {
                            "field": "actor.tenant_id",
                            "operator": "eq",
                            "value": {"$ref": "resource.tenant_id"},
                        }
                    ],
                }
            ],
        }
    )

    same = PolicyEngine(policy).evaluate(
        {"actor": {"tenant_id": "one"}, "resource": {"tenant_id": "one"}}
    )
    different = PolicyEngine(policy).evaluate(
        {"actor": {"tenant_id": "one"}, "resource": {"tenant_id": "two"}}
    )

    assert same.outcome is Outcome.ALLOW
    assert different.outcome is Outcome.DENY


def test_missing_reference_is_an_evaluation_error() -> None:
    policy = Policy.from_dict(
        {
            "schema_version": 1,
            "id": "reference-policy",
            "version": "1",
            "default_effect": "deny",
            "rules": [
                {
                    "id": "reference",
                    "effect": "allow",
                    "conditions": [
                        {"field": "actor.id", "operator": "eq", "value": {"$ref": "owner.id"}}
                    ],
                }
            ],
        }
    )

    with pytest.raises(EvaluationError, match="references missing field"):
        PolicyEngine(policy).evaluate({"actor": {"id": "a"}})


@pytest.mark.parametrize(
    ("operator", "actual", "expected", "result"),
    [
        ("exists", "value", None, True),
        ("not_exists", "missing", None, True),
        ("neq", 2, 3, True),
        ("in", "read", ["read", "list"], True),
        ("not_in", "write", ["read", "list"], True),
        ("contains", ["admin", "user"], "admin", True),
        ("not_contains", ["user"], "admin", True),
        ("subset_of", ["read", "sensitive"], ["read", "sensitive", "write"], True),
        ("subset_of", ["read", "shell"], ["read", "write"], False),
        ("starts_with", "system.admin", "system.", True),
        ("ends_with", "report.json", ".json", True),
        ("gt", 5, 4, True),
        ("gt", 5, 4.5, True),
        ("gte", 5, 5, True),
        ("gte", 5.0, 5, True),
        ("lt", 4, 5, True),
        ("lt", 4.5, 5, True),
        ("lte", 5, 5, True),
        ("lte", 5, 5.0, True),
    ],
)
def test_supported_operators(operator: str, actual: Any, expected: Any, result: bool) -> None:
    condition: dict[str, Any] = {"field": "value", "operator": operator}
    if operator not in {"exists", "not_exists"}:
        condition["value"] = expected
    policy = Policy.from_dict(
        {
            "schema_version": 1,
            "id": "operators",
            "version": "1",
            "default_effect": "deny",
            "rules": [{"id": "match", "effect": "allow", "conditions": [condition]}],
        }
    )
    context = {} if actual == "missing" else {"value": actual}

    assert (PolicyEngine(policy).evaluate(context).outcome is Outcome.ALLOW) is result


def test_invalid_comparison_type_fails_closed() -> None:
    policy = Policy.from_dict(
        {
            "schema_version": 1,
            "id": "types",
            "version": "1",
            "default_effect": "allow",
            "rules": [
                {
                    "id": "bad-comparison",
                    "effect": "deny",
                    "conditions": [{"field": "risk", "operator": "gt", "value": 2}],
                }
            ],
        }
    )

    with pytest.raises(EvaluationError, match="two numbers or two strings"):
        PolicyEngine(policy).evaluate({"risk": "high"})


def test_non_object_context_is_rejected(policy_document: dict[str, Any]) -> None:
    with pytest.raises(InputValidationError, match="JSON object"):
        PolicyEngine(Policy.from_dict(policy_document)).evaluate([])  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("context", "message"),
    [
        ({"nested": {1: "value"}}, "non-string object key"),
        ({"value": ("not", "json")}, "non-JSON value of type tuple"),
        ({"value": math.inf}, "non-finite number"),
    ],
)
def test_in_memory_context_uses_json_contract(
    context: dict[str, Any], message: str, policy_document: dict[str, Any]
) -> None:
    with pytest.raises(InputValidationError, match=message):
        PolicyEngine(Policy.from_dict(policy_document)).evaluate(context)


def test_bounded_batch_evaluation_preserves_order(policy_document: dict[str, Any]) -> None:
    engine = PolicyEngine(Policy.from_dict(policy_document))

    decisions = engine.evaluate_many(
        [
            {"action": {"operation": "read"}},
            {"action": {"operation": "delete"}},
            {"action": {"operation": "write"}},
        ]
    )

    assert tuple(decision.outcome for decision in decisions) == (
        Outcome.ALLOW,
        Outcome.DENY,
        Outcome.REVIEW,
    )


def test_batch_evaluation_reports_item_and_size_errors(policy_document: dict[str, Any]) -> None:
    engine = PolicyEngine(Policy.from_dict(policy_document))

    with pytest.raises(InputValidationError, match="batch must be iterable"):
        engine.evaluate_many(None)  # type: ignore[arg-type]
    with pytest.raises(InputValidationError, match=r"batch item 1.*non-finite"):
        engine.evaluate_many([{}, {"value": math.nan}])
    with pytest.raises(InputValidationError, match=f"limit of {MAX_BATCH_ITEMS}"):
        engine.evaluate_many(repeat({}, MAX_BATCH_ITEMS + 1))


def test_batch_evaluation_indexes_evaluation_errors() -> None:
    policy = Policy.from_dict(
        {
            "schema_version": 1,
            "id": "batch-errors",
            "version": "1",
            "default_effect": "deny",
            "rules": [
                {
                    "id": "numeric-comparison",
                    "effect": "allow",
                    "conditions": [{"field": "value", "operator": "gt", "value": 1}],
                }
            ],
        }
    )

    with pytest.raises(EvaluationError, match=r"batch item 1.*does not accept booleans"):
        PolicyEngine(policy).evaluate_many([{"value": 2}, {"value": True}])


def test_review_and_warning_rules_are_explained() -> None:
    policy = Policy.from_dict(
        {
            "schema_version": 1,
            "id": "review-policy",
            "version": "1",
            "default_effect": "deny",
            "rules": [
                {"id": "review", "effect": "review", "conditions": [], "message": "Review."},
                {"id": "warn", "effect": "warn", "conditions": [], "message": "Warning."},
                {"id": "audit", "effect": "audit", "conditions": []},
            ],
        }
    )

    decision = PolicyEngine(policy).evaluate({})

    assert decision.outcome is Outcome.REVIEW
    assert decision.reasons == ("Review.",)
    assert decision.warnings == ("Warning.",)
    assert decision.matched_rules == ("audit", "review", "warn")


@pytest.mark.parametrize(
    ("operator", "actual", "expected", "message"),
    [
        ("contains", "read", "r", "input field to be an array"),
        ("subset_of", "read", ["read"], "input field to be an array"),
        ("starts_with", 10, "1", "requires two strings"),
        ("gt", True, True, "does not accept booleans"),
    ],
)
def test_operator_type_errors(operator: str, actual: Any, expected: Any, message: str) -> None:
    policy = Policy.from_dict(
        {
            "schema_version": 1,
            "id": "type-errors",
            "version": "1",
            "default_effect": "deny",
            "rules": [
                {
                    "id": "rule",
                    "effect": "allow",
                    "conditions": [{"field": "value", "operator": operator, "value": expected}],
                }
            ],
        }
    )

    with pytest.raises(EvaluationError, match=message):
        PolicyEngine(policy).evaluate({"value": actual})
