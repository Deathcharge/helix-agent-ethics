"""Policy rule-coverage reporting."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from samsarix_ethics import (
    POLICY_COVERAGE_VERSION,
    Policy,
    PolicyTestSuite,
    fingerprint_policy,
    measure_policy_coverage,
)


def _suite(*cases: dict[str, Any]) -> PolicyTestSuite:
    return PolicyTestSuite.from_dict(
        {"schema_version": 1, "name": "coverage cases", "cases": list(cases)}
    )


def test_measure_policy_coverage_reports_rules_outcomes_and_threshold(
    policy_document: dict[str, Any],
) -> None:
    policy = Policy.from_dict(policy_document)
    suite = _suite(
        {
            "name": "read matches allow",
            "input": {"action": {"operation": "read"}},
            "expected_outcome": "allow",
        },
        {
            "name": "write uses default",
            "input": {"action": {"operation": "write"}},
            "expected_outcome": "review",
        },
    )

    report = measure_policy_coverage(policy, suite, threshold=50)

    assert report.coverage_version == POLICY_COVERAGE_VERSION == 1
    assert report.policy_fingerprint == fingerprint_policy(policy)
    assert report.total_rules == 2
    assert report.covered_rules == 1
    assert report.uncovered_rules == 1
    assert report.coverage_percent == 50.0
    assert report.covered_rule_ids == ("allow-read",)
    assert report.uncovered_rule_ids == ("deny-delete",)
    assert report.total_cases == 2
    assert report.evaluated_cases == 2
    assert report.allow_cases == 1
    assert report.deny_cases == 0
    assert report.review_cases == 1
    assert report.errors == 0
    assert report.threshold_met is True
    assert report.complete is False


def test_threshold_uses_exact_counts_not_rounded_display(
    policy_document: dict[str, Any],
) -> None:
    policy = Policy.from_dict(policy_document)
    suite = _suite(
        {
            "name": "read",
            "input": {"action": {"operation": "read"}},
            "expected_outcome": "allow",
        }
    )

    report = measure_policy_coverage(policy, suite, threshold=51)

    assert report.coverage_percent == 50.0
    assert report.threshold_met is False


def test_coverage_errors_fail_threshold_without_exposing_inputs() -> None:
    policy = Policy.from_dict(
        {
            "schema_version": 1,
            "id": "array-policy",
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
    suite = _suite(
        {
            "name": "wrong role shape",
            "input": {"roles": "never-report-this-input"},
            "expected_outcome": "deny",
        }
    )

    report = measure_policy_coverage(policy, suite)

    assert report.evaluated_cases == 0
    assert report.errors == 1
    assert report.threshold_met is False
    assert report.complete is False
    assert report.error_cases[0].name == "wrong role shape"
    assert "requires the input field to be an array" in report.error_cases[0].error
    assert "never-report-this-input" not in json.dumps(report.to_dict())


def test_empty_policy_has_vacuously_complete_rule_coverage() -> None:
    policy = Policy.from_dict(
        {
            "schema_version": 1,
            "id": "default-only",
            "version": "1",
            "default_effect": "deny",
            "rules": [],
        }
    )
    suite = _suite({"name": "default", "input": {}, "expected_outcome": "deny"})

    report = measure_policy_coverage(policy, suite, threshold=100)

    assert report.total_rules == 0
    assert report.coverage_percent == 100.0
    assert report.deny_cases == 1
    assert report.threshold_met is True
    assert report.complete is True


def test_coverage_report_is_frozen_and_serialization_is_detached(
    policy_document: dict[str, Any],
) -> None:
    policy = Policy.from_dict(policy_document)
    suite = _suite(
        {
            "name": "read",
            "input": {"action": {"operation": "read"}},
            "expected_outcome": "allow",
        }
    )
    report = measure_policy_coverage(policy, suite)
    payload = report.to_dict()

    payload["covered_rule_ids"].append("mutated")
    assert "mutated" not in report.covered_rule_ids
    with pytest.raises(FrozenInstanceError):
        report.policy_id = "changed"  # type: ignore[misc]


@pytest.mark.parametrize("threshold", [-1, 101, True, 1.5, "100"])
def test_measure_policy_coverage_rejects_invalid_thresholds(
    threshold: Any, policy_document: dict[str, Any]
) -> None:
    policy = Policy.from_dict(policy_document)
    suite = _suite({"name": "case", "input": {}, "expected_outcome": "review"})

    with pytest.raises(ValueError, match="integer from 0 to 100"):
        measure_policy_coverage(policy, suite, threshold=threshold)


def test_measure_policy_coverage_rejects_wrong_public_types(
    policy_document: dict[str, Any],
) -> None:
    policy = Policy.from_dict(policy_document)
    suite = _suite({"name": "case", "input": {}, "expected_outcome": "review"})

    with pytest.raises(TypeError, match="policy must be a Policy"):
        measure_policy_coverage(object(), suite)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="suite must be a PolicyTestSuite"):
        measure_policy_coverage(policy, object())  # type: ignore[arg-type]
