"""Baseline-authoritative shadow policy evaluation."""

from __future__ import annotations

import json
from typing import Any

import pytest

from samsarix_ethics import (
    EvaluationError,
    InputValidationError,
    Policy,
    PolicyShadowChange,
    PolicyShadowEvaluator,
    PolicyShadowSnapshot,
    PolicyShadowStatus,
    PolicyTestSuite,
    compare_policies,
)


def _policy(
    policy_id: str,
    *,
    version: str = "1",
    default_effect: str = "allow",
    rules: list[dict[str, Any]] | None = None,
) -> Policy:
    return Policy.from_dict(
        {
            "schema_version": 1,
            "id": policy_id,
            "version": version,
            "default_effect": default_effect,
            "rules": rules or [],
        }
    )


def _read_rule(rule_id: str, effect: str, message: str) -> dict[str, Any]:
    return {
        "id": rule_id,
        "effect": effect,
        "message": message,
        "conditions": [{"field": "action.operation", "operator": "eq", "value": "read"}],
    }


def test_shadow_candidate_changes_never_replace_authoritative_decision() -> None:
    baseline = _policy(
        "approved-policy",
        rules=[_read_rule("allow-read", "allow", "Baseline permits reads.")],
    )
    candidate = _policy(
        "candidate-policy",
        version="2-candidate",
        rules=[_read_rule("review-read", "review", "Candidate requires review.")],
    )

    result = PolicyShadowEvaluator(baseline, candidate).evaluate(
        {"action": {"operation": "read"}, "secret": "top-secret-input"}
    )

    assert result.authoritative_decision.outcome.value == "allow"
    assert result.authoritative_decision.allowed is True
    assert result.candidate_decision is not None
    assert result.candidate_decision.outcome.value == "review"
    assert result.status is PolicyShadowStatus.CHANGED
    assert result.authorization_changed is True
    assert result.changes == (
        PolicyShadowChange.OUTCOME,
        PolicyShadowChange.MATCHED_RULES,
        PolicyShadowChange.REASON_MESSAGES,
    )
    serialized = result.to_dict()
    assert serialized["authoritative"]["outcome"] == "allow"
    assert serialized["candidate"]["outcome"] == "review"
    assert serialized["candidate"]["error"] is None
    assert serialized["authoritative"]["evaluation_duration_ns"] >= 0
    assert serialized["candidate"]["evaluation_duration_ns"] >= 0
    payload = json.dumps(serialized)
    assert "top-secret-input" not in payload
    assert "Baseline permits reads." not in payload
    assert "Candidate requires review." not in payload


def test_shadow_unchanged_result_has_independent_decisions_and_detached_serialization() -> None:
    baseline = _policy("baseline")
    candidate = _policy("candidate")
    context = {"nested": {"value": ["original"]}}

    result = PolicyShadowEvaluator(baseline, candidate).evaluate(context)
    context["nested"]["value"][0] = "changed"
    first = result.to_dict()
    first["authoritative"]["matched_rules"].append("mutation")

    assert result.status is PolicyShadowStatus.UNCHANGED
    assert result.changes == ()
    assert result.authorization_changed is False
    assert result.candidate_decision is not None
    assert result.authoritative_decision.decision_id != result.candidate_decision.decision_id
    assert result.to_dict()["authoritative"]["matched_rules"] == []
    assert "nested" not in json.dumps(result.to_dict())
    assert "original" not in json.dumps(result.to_dict())


def test_candidate_domain_error_is_observational_after_successful_baseline() -> None:
    baseline = _policy("baseline")
    candidate = _policy(
        "candidate",
        version="2",
        default_effect="deny",
        rules=[
            {
                "id": "allow-listed-value",
                "effect": "allow",
                "message": "A listed value is allowed.",
                "conditions": [{"field": "value", "operator": "contains", "value": "allowed"}],
            }
        ],
    )
    evaluator = PolicyShadowEvaluator(baseline, candidate)

    result = evaluator.evaluate({"value": "private-scalar"})

    assert result.authoritative_decision.outcome.value == "allow"
    assert result.candidate_decision is None
    assert result.status is PolicyShadowStatus.ERROR
    assert result.changes == ()
    assert result.authorization_changed is False
    assert result.candidate.policy_id == "candidate"
    assert result.candidate.policy_version == "2"
    assert evaluator.baseline_policy_fingerprint == result.authoritative_decision.policy_fingerprint
    assert result.candidate.policy_fingerprint == evaluator.candidate_policy_fingerprint
    assert result.candidate.error == (
        "rule 'allow-listed-value' failed: operator 'contains' requires the input field "
        "to be an array"
    )
    assert result.candidate.decision_id is None
    assert result.candidate.evaluation_duration_ns >= 0
    assert "private-scalar" not in json.dumps(result.to_dict())


def test_baseline_error_propagates_fail_closed() -> None:
    broken_baseline = _policy(
        "baseline",
        rules=[
            {
                "id": "unsafe-type",
                "effect": "allow",
                "conditions": [{"field": "value", "operator": "contains", "value": "x"}],
            }
        ],
    )
    evaluator = PolicyShadowEvaluator(broken_baseline, _policy("candidate"))

    with pytest.raises(EvaluationError, match="rule 'unsafe-type' failed"):
        evaluator.evaluate({"value": "not-an-array"})


def test_unexpected_candidate_failure_is_not_silently_downgraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluator = PolicyShadowEvaluator(_policy("baseline"), _policy("candidate"))

    def fail_unexpectedly(context: object) -> object:
        raise RuntimeError("programmer failure")

    monkeypatch.setattr(evaluator._candidate_engine, "evaluate", fail_unexpectedly)
    with pytest.raises(RuntimeError, match="programmer failure"):
        evaluator.evaluate({})


def test_shadow_records_separate_monotonic_evaluation_durations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ticks = iter((100, 175, 200, 260))
    monkeypatch.setattr("samsarix_ethics.shadow.perf_counter_ns", lambda: next(ticks))

    result = PolicyShadowEvaluator(_policy("baseline"), _policy("candidate")).evaluate({})

    assert result.authoritative.evaluation_duration_ns == 75
    assert result.candidate.evaluation_duration_ns == 60


def test_shadow_and_offline_comparison_use_identical_change_semantics() -> None:
    baseline = _policy(
        "baseline",
        rules=[
            _read_rule("allow-read", "allow", "Old reason."),
            _read_rule("warn-read", "warn", "Old warning."),
        ],
    )
    candidate = _policy(
        "candidate",
        rules=[
            _read_rule("allow-read-renamed", "allow", "New reason."),
            _read_rule("warn-read", "warn", "New warning."),
            _read_rule("warn-read-again", "warn", "Second warning."),
        ],
    )
    context = {"action": {"operation": "read"}}
    suite = PolicyTestSuite.from_dict(
        {
            "schema_version": 1,
            "cases": [{"name": "read", "input": context, "expected_outcome": "allow"}],
        }
    )

    shadow = PolicyShadowEvaluator(baseline, candidate).evaluate(context)
    comparison = compare_policies(baseline, candidate, suite).results[0]

    assert tuple(change.value for change in shadow.changes) == tuple(
        change.value for change in comparison.changes
    )
    assert tuple(change.value for change in shadow.changes) == (
        "matched_rules",
        "warning_count",
        "reason_messages",
        "warning_messages",
    )


def test_shadow_public_type_contracts() -> None:
    policy = _policy("valid")
    with pytest.raises(TypeError, match="baseline must be a Policy"):
        PolicyShadowEvaluator(object(), policy)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="candidate must be a Policy"):
        PolicyShadowEvaluator(policy, object())  # type: ignore[arg-type]
    with pytest.raises(InputValidationError, match="must be a JSON object"):
        PolicyShadowEvaluator(policy, policy).evaluate([])  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="decision must be a Decision"):
        PolicyShadowSnapshot.from_decision(  # type: ignore[arg-type]
            object(), evaluation_duration_ns=0
        )
    decision = PolicyShadowEvaluator(policy, policy).evaluate({}).authoritative_decision
    with pytest.raises(ValueError, match="must be a non-negative integer"):
        PolicyShadowSnapshot.from_decision(decision, evaluation_duration_ns=True)
