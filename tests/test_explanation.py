"""Value-minimized policy explanation tests."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest
from jsonschema import Draft202012Validator, ValidationError  # type: ignore[import-untyped]

from samsarix_ethics import (
    ConditionExplanationStatus,
    ContextContract,
    EvaluationError,
    Outcome,
    Policy,
    PolicyEngine,
    ToolGate,
    get_policy_explanation_schema,
)


def _policy() -> Policy:
    return Policy.from_dict(
        {
            "schema_version": 1,
            "id": "explain-policy",
            "version": "1",
            "default_effect": "review",
            "rules": [
                {
                    "id": "allow-read",
                    "effect": "allow",
                    "priority": 10,
                    "message": "sensitive allow explanation",
                    "conditions": [
                        {"field": "action.kind", "operator": "eq", "value": "read"},
                        {"field": "action.risk", "operator": "lte", "value": 2},
                    ],
                },
                {
                    "id": "deny-blocked",
                    "effect": "deny",
                    "priority": 1,
                    "conditions": [{"field": "action.blocked", "operator": "eq", "value": True}],
                },
                {
                    "id": "warn-external",
                    "effect": "warn",
                    "priority": 20,
                    "conditions": [{"field": "action.external", "operator": "eq", "value": True}],
                },
            ],
        }
    )


def test_explanation_matches_decision_and_marks_short_circuit() -> None:
    engine = PolicyEngine(_policy())
    context = {"action": {"kind": "write", "risk": [], "blocked": False, "external": False}}

    decision = engine.evaluate(context)
    explanation = engine.explain(context)

    assert decision.outcome is explanation.outcome is Outcome.REVIEW
    assert decision.matched_rules == explanation.matched_rule_ids == ()
    assert explanation.default_applied is True
    assert explanation.decisive_rule_ids == ()
    assert explanation.rules[0].matched is False
    assert [item.status for item in explanation.rules[0].conditions] == [
        ConditionExplanationStatus.NOT_MATCHED,
        ConditionExplanationStatus.NOT_EVALUATED,
    ]


def test_explanation_identifies_all_matches_and_only_decisive_effect() -> None:
    engine = PolicyEngine(_policy())
    context = {
        "action": {
            "kind": "read",
            "risk": 1,
            "blocked": True,
            "external": True,
        }
    }

    explanation = engine.explain(context)

    assert explanation.outcome is Outcome.DENY
    assert explanation.default_applied is False
    assert explanation.matched_rule_ids == (
        "deny-blocked",
        "allow-read",
        "warn-external",
    )
    assert explanation.decisive_rule_ids == ("deny-blocked",)
    by_id = {rule.rule_id: rule for rule in explanation.rules}
    assert by_id["deny-blocked"].decisive is True
    assert by_id["allow-read"].matched is True
    assert by_id["allow-read"].decisive is False
    assert all(
        condition.status is ConditionExplanationStatus.MATCHED
        for rule in explanation.rules
        for condition in rule.conditions
    )


def test_explanation_is_value_minimized_and_schema_valid() -> None:
    explanation = PolicyEngine(_policy()).explain(
        {
            "action": {
                "kind": "private-input-value",
                "risk": 1,
                "blocked": False,
                "external": False,
            }
        }
    )
    document = explanation.to_dict()
    encoded = json.dumps(document, sort_keys=True)

    Draft202012Validator(get_policy_explanation_schema()).validate(document)
    assert document["explanation_version"] == 1
    assert document["evaluated_rules"] == 3
    assert "private-input-value" not in encoded
    assert "sensitive allow explanation" not in encoded
    assert '"value"' not in encoded
    assert '"message"' not in encoded


def test_explanation_binds_optional_context_contract() -> None:
    contract = ContextContract.from_dict(
        {
            "context_contract_version": 1,
            "id": "explain-context",
            "version": "1",
            "fields": {
                "action": {"type": "object"},
                "action.kind": {"type": "string"},
                "action.risk": {"type": "number"},
                "action.blocked": {"type": "boolean"},
                "action.external": {"type": "boolean"},
            },
        }
    )
    explanation = PolicyEngine(_policy(), context_contract=contract).explain(
        {
            "action": {
                "kind": "read",
                "risk": 1,
                "blocked": False,
                "external": False,
            }
        }
    )

    assert explanation.context_contract_fingerprint is not None
    assert explanation.context_contract_fingerprint.startswith("v1:sha256:")


def test_explanation_and_decision_raise_same_evaluation_error() -> None:
    policy = Policy.from_dict(
        {
            "schema_version": 1,
            "id": "error-explanation",
            "version": "1",
            "default_effect": "deny",
            "rules": [
                {
                    "id": "typed-condition",
                    "effect": "allow",
                    "conditions": [
                        {"field": "action.kind", "operator": "starts_with", "value": "r"}
                    ],
                }
            ],
        }
    )
    engine = PolicyEngine(policy)

    with pytest.raises(EvaluationError) as decision_error:
        engine.evaluate({"action": {"kind": []}})
    with pytest.raises(EvaluationError) as explanation_error:
        engine.explain({"action": {"kind": []}})

    assert str(explanation_error.value) == str(decision_error.value)


def test_explanation_to_dict_returns_fresh_containers() -> None:
    explanation = PolicyEngine(_policy()).explain(
        {
            "action": {
                "kind": "read",
                "risk": 1,
                "blocked": False,
                "external": False,
            }
        }
    )
    first = explanation.to_dict()
    second = explanation.to_dict()
    first["rules"][0]["conditions"][0]["status"] = "changed"

    assert second["rules"][0]["conditions"][0]["status"] == "matched"


def test_explanation_schema_accessor_returns_fresh_values() -> None:
    changed = get_policy_explanation_schema()
    changed["title"] = "changed"

    assert get_policy_explanation_schema()["title"] != "changed"


def test_tool_gate_and_bound_gate_explain_normalized_calls() -> None:
    audit_records: list[object] = []
    gate = ToolGate(_policy(), audit_sink=audit_records.append)
    bound = gate.bind("read-record", capabilities=("records.read",))

    direct = gate.explain("read-record", {"record_id": "private"})
    registered = bound.explain({"record_id": "private"})

    assert direct.outcome is Outcome.REVIEW
    assert registered.to_dict() == direct.to_dict()
    assert audit_records == []


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update({"default_applied": True}),
        lambda value: value["rules"][2].update({"decisive": True}),
        lambda value: value["rules"][0]["conditions"][0].update({"status": "not_evaluated"}),
    ],
)
def test_explanation_schema_rejects_contradictory_status(
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    explanation = (
        PolicyEngine(_policy())
        .explain(
            {
                "action": {
                    "kind": "read",
                    "risk": 1,
                    "blocked": False,
                    "external": False,
                }
            }
        )
        .to_dict()
    )
    mutate(explanation)

    with pytest.raises(ValidationError):
        Draft202012Validator(get_policy_explanation_schema()).validate(explanation)
