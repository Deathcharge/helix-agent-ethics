"""Baseline-versus-candidate policy impact comparison."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from samsarix_ethics import (
    POLICY_COMPARISON_VERSION,
    Outcome,
    Policy,
    PolicyComparisonChange,
    PolicyComparisonStatus,
    PolicyTestSuite,
    compare_policies,
    fingerprint_policy,
)


def _suite(*cases: dict[str, Any]) -> PolicyTestSuite:
    return PolicyTestSuite.from_dict(
        {"schema_version": 1, "name": "impact cases", "cases": list(cases)}
    )


def _candidate_with_authorization_and_metadata_changes(
    policy_document: dict[str, Any],
) -> Policy:
    candidate = deepcopy(policy_document)
    candidate["version"] = "2.0.0"
    candidate["rules"].extend(
        [
            {
                "id": "deny-read",
                "effect": "deny",
                "priority": 0,
                "message": "Candidate blocks reads.",
                "conditions": [{"field": "action.operation", "operator": "eq", "value": "read"}],
            },
            {
                "id": "warn-write",
                "effect": "warn",
                "priority": 20,
                "message": "Candidate warns on writes.",
                "conditions": [{"field": "action.operation", "operator": "eq", "value": "write"}],
            },
        ]
    )
    return Policy.from_dict(candidate)


def test_compare_policies_classifies_authorization_metadata_and_unchanged_cases(
    policy_document: dict[str, Any],
) -> None:
    baseline = Policy.from_dict(policy_document)
    candidate = _candidate_with_authorization_and_metadata_changes(policy_document)
    suite = _suite(
        {
            "name": "read changes authorization",
            "input": {"action": {"operation": "read"}},
            "expected_outcome": "allow",
        },
        {
            "name": "write changes metadata only",
            "input": {"action": {"operation": "write"}},
            "expected_outcome": "review",
        },
        {
            "name": "delete is unchanged",
            "input": {"action": {"operation": "delete"}},
            "expected_outcome": "deny",
        },
    )

    report = compare_policies(baseline, candidate, suite)

    assert report.comparison_version == POLICY_COMPARISON_VERSION == 1
    assert report.baseline_policy_fingerprint == fingerprint_policy(baseline)
    assert report.candidate_policy_fingerprint == fingerprint_policy(candidate)
    assert report.unchanged == 1
    assert report.changed == 2
    assert report.authorization_changes == 1
    assert report.metadata_only_changes == 1
    assert report.errors == 0
    assert report.identical is False

    authorization, metadata, unchanged = report.results
    assert authorization.status is PolicyComparisonStatus.CHANGED
    assert authorization.changes == (
        PolicyComparisonChange.OUTCOME,
        PolicyComparisonChange.MATCHED_RULES,
        PolicyComparisonChange.REASON_MESSAGES,
    )
    assert authorization.authorization_changed is True
    assert authorization.baseline.outcome is Outcome.ALLOW
    assert authorization.candidate.outcome is Outcome.DENY
    assert metadata.status is PolicyComparisonStatus.CHANGED
    assert metadata.changes == (
        PolicyComparisonChange.MATCHED_RULES,
        PolicyComparisonChange.WARNING_COUNT,
        PolicyComparisonChange.WARNING_MESSAGES,
    )
    assert metadata.authorization_changed is False
    assert unchanged.status is PolicyComparisonStatus.UNCHANGED
    assert unchanged.changes == ()


def test_compare_policies_is_deterministic_detached_and_input_free(
    policy_document: dict[str, Any],
) -> None:
    policy = Policy.from_dict(policy_document)
    suite = _suite(
        {
            "name": "secret case",
            "input": {
                "action": {"operation": "read"},
                "secret": "never-report-comparison-input",
            },
            "expected_outcome": "deny",
        }
    )

    first = compare_policies(policy, policy, suite)
    second = compare_policies(policy, policy, suite)
    payload = first.to_dict()

    assert first == second
    assert first.identical is True
    assert first.unchanged == 1
    assert "never-report-comparison-input" not in json.dumps(payload)
    payload["results"][0]["baseline"]["matched_rules"].append("mutated")
    assert "mutated" not in first.results[0].baseline.matched_rules
    with pytest.raises(FrozenInstanceError):
        first.suite_name = "changed"  # type: ignore[misc]


def test_compare_policies_reports_each_side_error_without_input() -> None:
    baseline = Policy.from_dict(
        {
            "schema_version": 1,
            "id": "error-baseline",
            "version": "1",
            "default_effect": "deny",
            "rules": [
                {
                    "id": "array-only",
                    "effect": "allow",
                    "conditions": [{"field": "roles", "operator": "contains", "value": "admin"}],
                }
            ],
        }
    )
    candidate = Policy.from_dict(
        {
            "schema_version": 1,
            "id": "safe-candidate",
            "version": "2",
            "default_effect": "deny",
            "rules": [],
        }
    )
    suite = _suite(
        {
            "name": "baseline errors",
            "input": {"roles": "private-input-value"},
            "expected_outcome": "deny",
        }
    )

    report = compare_policies(baseline, candidate, suite)
    result = report.results[0]

    assert report.errors == 1
    assert report.identical is False
    assert result.status is PolicyComparisonStatus.ERROR
    assert "requires the input field to be an array" in (result.baseline.error or "")
    assert result.candidate.error is None
    assert result.candidate.outcome is Outcome.DENY
    assert "private-input-value" not in json.dumps(report.to_dict())


def test_message_only_policy_change_is_metadata_impact_without_exposing_text(
    policy_document: dict[str, Any],
) -> None:
    candidate_document = deepcopy(policy_document)
    candidate_document["rules"][0]["message"] = "Different reason text."
    baseline = Policy.from_dict(policy_document)
    candidate = Policy.from_dict(candidate_document)
    suite = _suite(
        {
            "name": "delete",
            "input": {"action": {"operation": "delete"}},
            "expected_outcome": "deny",
        }
    )

    report = compare_policies(baseline, candidate, suite)

    assert report.identical is False
    assert report.metadata_only_changes == 1
    assert report.results[0].changes == (PolicyComparisonChange.REASON_MESSAGES,)
    assert report.baseline_policy_fingerprint != report.candidate_policy_fingerprint
    assert "Different reason text." not in json.dumps(report.to_dict())


@pytest.mark.parametrize(
    ("baseline", "candidate", "suite", "message"),
    [
        (object(), None, None, "baseline must be a Policy"),
        (None, object(), None, "candidate must be a Policy"),
        (None, None, object(), "suite must be a PolicyTestSuite"),
    ],
)
def test_compare_policies_rejects_wrong_public_types(
    baseline: Any,
    candidate: Any,
    suite: Any,
    message: str,
    policy_document: dict[str, Any],
) -> None:
    policy = Policy.from_dict(policy_document)
    if baseline is None:
        baseline = policy
    if candidate is None:
        candidate = policy
    if suite is None:
        suite = _suite({"name": "case", "input": {}, "expected_outcome": "review"})

    with pytest.raises(TypeError, match=message):
        compare_policies(baseline, candidate, suite)
