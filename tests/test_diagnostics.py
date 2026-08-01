"""Deterministic policy authoring diagnostics."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from samsarix_ethics import (
    POLICY_LINT_VERSION,
    Policy,
    PolicyLintCode,
    PolicyLintSeverity,
    fingerprint_policy,
    lint_policy,
)


def _policy(*rules: dict[str, Any], default_effect: str = "deny") -> Policy:
    return Policy.from_dict(
        {
            "schema_version": 1,
            "id": "lint-policy",
            "version": "1",
            "default_effect": default_effect,
            "rules": list(rules),
        }
    )


def test_lint_policy_reports_stable_ordered_findings_without_values() -> None:
    policy = _policy(
        {"id": "allow-all", "effect": "allow", "conditions": []},
        {
            "id": "impossible",
            "effect": "deny",
            "conditions": [
                {"field": "action.name", "operator": "eq", "value": "never-output-secret"},
                {"field": "action.name", "operator": "neq", "value": "never-output-secret"},
            ],
        },
        {
            "id": "duplicate",
            "effect": "review",
            "message": "Review duplicated facts.",
            "conditions": [
                {"field": "action.risk", "operator": "eq", "value": 1},
                {"field": "action.risk", "operator": "eq", "value": 1.0},
            ],
        },
        default_effect="allow",
    )

    report = lint_policy(policy)

    assert report.lint_version == POLICY_LINT_VERSION == 1
    assert report.policy_fingerprint == fingerprint_policy(policy)
    assert [finding.code for finding in report.findings] == [
        PolicyLintCode.DEFAULT_ALLOW,
        PolicyLintCode.UNCONDITIONAL_ALLOW,
        PolicyLintCode.MISSING_MESSAGE,
        PolicyLintCode.UNREACHABLE_RULE,
        PolicyLintCode.MISSING_MESSAGE,
        PolicyLintCode.DUPLICATE_CONDITION,
    ]
    assert report.security_warnings == 2
    assert report.warnings == 1
    assert report.suggestions == 3
    assert report.blocking_findings == 2
    assert report.passed is False
    assert report.findings[3].condition_indices == (0, 1)
    assert report.findings[5].condition_indices == (0, 1)
    assert "never-output-secret" not in json.dumps(report.to_dict())


def test_fail_on_severity_is_explicit_and_ordered() -> None:
    policy = _policy(
        {
            "id": "missing-message",
            "effect": "allow",
            "conditions": [{"field": "action.name", "operator": "eq", "value": "read"}],
        }
    )

    default_report = lint_policy(policy)
    warning_report = lint_policy(policy, fail_on=PolicyLintSeverity.WARNING)
    suggestion_report = lint_policy(policy, fail_on=PolicyLintSeverity.SUGGESTION)
    report_only = lint_policy(policy, fail_on=None)

    assert default_report.passed is True
    assert warning_report.passed is True
    assert suggestion_report.passed is False
    assert suggestion_report.blocking_findings == 1
    assert report_only.passed is True
    assert report_only.to_dict()["fail_on"] == "none"


def test_only_provably_impossible_condition_sets_are_reported() -> None:
    patterns = [
        [{"field": "x", "operator": "in", "value": []}],
        [
            {"field": "x", "operator": "not_exists"},
            {"field": "x", "operator": "exists"},
        ],
        [
            {"field": "x", "operator": "eq", "value": True},
            {"field": "x", "operator": "eq", "value": 1},
        ],
        [
            {"field": "x", "operator": "eq", "value": "a"},
            {"field": "x", "operator": "neq", "value": "a"},
        ],
        [
            {"field": "x", "operator": "eq", "value": "a"},
            {"field": "x", "operator": "in", "value": ["b"]},
        ],
        [
            {"field": "x", "operator": "in", "value": ["a", "b"]},
            {"field": "x", "operator": "not_in", "value": ["a", "b"]},
        ],
        [
            {"field": "x", "operator": "in", "value": ["a"]},
            {"field": "x", "operator": "in", "value": ["b"]},
        ],
    ]
    rules = [
        {
            "id": f"impossible-{index}",
            "effect": "deny",
            "message": "Impossible by construction.",
            "conditions": conditions,
        }
        for index, conditions in enumerate(patterns)
    ]

    report = lint_policy(_policy(*rules), fail_on=PolicyLintSeverity.WARNING)

    unreachable = [
        finding for finding in report.findings if finding.code is PolicyLintCode.UNREACHABLE_RULE
    ]
    assert len(unreachable) == len(patterns)
    assert [finding.rule_id for finding in unreachable] == [
        f"impossible-{index}" for index in range(len(patterns))
    ]
    assert report.passed is False


def test_dynamic_and_satisfiable_constraints_are_not_guessed_unreachable() -> None:
    policy = _policy(
        {
            "id": "dynamic-reference",
            "effect": "allow",
            "message": "Values may agree at runtime.",
            "conditions": [
                {"field": "x", "operator": "eq", "value": "a"},
                {"field": "x", "operator": "eq", "value": {"$ref": "expected"}},
            ],
        },
        {
            "id": "remaining-member",
            "effect": "allow",
            "message": "One member remains possible.",
            "conditions": [
                {"field": "x", "operator": "in", "value": ["a", "b"]},
                {"field": "x", "operator": "not_in", "value": ["a"]},
            ],
        },
    )

    report = lint_policy(policy, fail_on=PolicyLintSeverity.SUGGESTION)

    assert report.findings == ()
    assert report.passed is True


def test_lint_report_is_frozen_and_serialization_is_detached() -> None:
    report = lint_policy(_policy(default_effect="allow"))
    payload = report.to_dict()

    payload["findings"][0]["condition_indices"].append(31)
    assert report.findings[0].condition_indices == ()
    with pytest.raises(FrozenInstanceError):
        report.policy_id = "changed"  # type: ignore[misc]


def test_lint_policy_rejects_wrong_public_types() -> None:
    policy = _policy()

    with pytest.raises(TypeError, match="policy must be a Policy"):
        lint_policy(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="fail_on must be a PolicyLintSeverity or None"):
        lint_policy(policy, fail_on="warning")  # type: ignore[arg-type]
