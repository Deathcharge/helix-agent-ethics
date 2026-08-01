"""Policy schema and regression-suite behavior."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, ValidationError

from samsarix_ethics import (
    Outcome,
    Policy,
    PolicyTestCase,
    PolicyTestStatus,
    PolicyTestSuite,
    PolicyTestValidationError,
    get_policy_schema,
    get_policy_test_schema,
    load_policy_test_suite,
    run_policy_tests,
)
from samsarix_ethics.io import SAMPLE_POLICY


def _suite(*cases: dict[str, Any]) -> PolicyTestSuite:
    return PolicyTestSuite.from_dict(
        {"schema_version": 1, "name": "test suite", "cases": list(cases)}
    )


def test_bundled_draft_2020_12_schemas_validate_examples() -> None:
    policy_schema = get_policy_schema()
    test_schema = get_policy_test_schema()
    example_suite = json.loads(
        (Path(__file__).parents[1] / "examples/tests/safe-agent-actions.tests.json").read_text(
            encoding="utf-8"
        )
    )

    Draft202012Validator.check_schema(policy_schema)
    Draft202012Validator.check_schema(test_schema)
    Draft202012Validator(policy_schema).validate(SAMPLE_POLICY)
    Draft202012Validator(test_schema).validate(example_suite)
    assert policy_schema["$id"].endswith("/policy/v1.json")
    assert test_schema["$id"].endswith("/policy-test/v1.json")


def test_policy_schema_matches_strict_condition_contract() -> None:
    schema = get_policy_schema()
    exists_with_value = copy.deepcopy(SAMPLE_POLICY)
    exists_with_value["rules"][0]["conditions"][1]["value"] = True
    scalar_membership = copy.deepcopy(SAMPLE_POLICY)
    scalar_membership["rules"][0]["conditions"][0]["value"] = "delete"

    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(exists_with_value)
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(scalar_membership)


def test_schema_access_returns_fresh_values() -> None:
    changed = get_policy_schema()
    changed["title"] = "changed"

    assert get_policy_schema()["title"] != "changed"


def test_policy_test_report_preserves_pass_fail_and_privacy(
    policy_document: dict[str, Any],
) -> None:
    suite = _suite(
        {
            "name": "read passes",
            "input": {"action": {"operation": "read"}, "secret": "never-report-this"},
            "expected_outcome": "allow",
            "expected_matched_rules": ["allow-read"],
            "expected_warning_count": 0,
        },
        {
            "name": "wrong expectation fails",
            "input": {"action": {"operation": "delete"}},
            "expected_outcome": "allow",
        },
    )

    report = run_policy_tests(Policy.from_dict(policy_document), suite)
    payload = report.to_dict()

    assert report.passed == 1
    assert report.failed == 1
    assert report.errors == 0
    assert report.successful is False
    assert report.results[0].status is PolicyTestStatus.PASS
    assert report.results[1].status is PolicyTestStatus.FAIL
    assert "expected outcome 'allow', got 'deny'" in report.results[1].failures
    assert "never-report-this" not in json.dumps(payload)
    assert payload["results"][0]["actual_matched_rules"] == ["allow-read"]


def test_policy_test_evaluation_errors_are_reported() -> None:
    policy = Policy.from_dict(
        {
            "schema_version": 1,
            "id": "error-policy",
            "version": "1",
            "default_effect": "deny",
            "rules": [
                {
                    "id": "requires-array",
                    "effect": "allow",
                    "conditions": [{"field": "roles", "operator": "contains", "value": "admin"}],
                }
            ],
        }
    )
    suite = _suite(
        {
            "name": "bad input type",
            "input": {"roles": "admin"},
            "expected_outcome": "allow",
        }
    )

    report = run_policy_tests(policy, suite)

    assert report.errors == 1
    assert report.results[0].status is PolicyTestStatus.ERROR
    assert "requires the input field to be an array" in (report.results[0].error or "")
    assert report.results[0].actual_outcome is None


@pytest.mark.parametrize(
    ("suite", "message"),
    [
        ({"schema_version": 1, "cases": []}, "must contain from 1"),
        (
            {
                "schema_version": 1,
                "cases": [
                    {"name": "same", "input": {}, "expected_outcome": "allow"},
                    {"name": "same", "input": {}, "expected_outcome": "deny"},
                ],
            },
            "duplicate names",
        ),
        (
            {
                "schema_version": 1,
                "cases": [{"name": "case", "input": {}, "expected_outcome": "invalid"}],
            },
            "must be allow, deny, or review",
        ),
        (
            {
                "schema_version": 1,
                "cases": [
                    {
                        "name": "case",
                        "input": {"value": ("not", "json")},
                        "expected_outcome": "deny",
                    }
                ],
            },
            "non-JSON value",
        ),
        ({"schema_version": 1, "cases": [], 1: "bad key"}, "non-string object key"),
        (
            {
                "schema_version": 1,
                "cases": [
                    {
                        "name": "null assertion",
                        "input": {},
                        "expected_outcome": "deny",
                        "expected_matched_rules": None,
                    }
                ],
            },
            "must be an array of rule ids",
        ),
        (
            {
                "schema_version": 1,
                "cases": [
                    {
                        "name": "null warning count",
                        "input": {},
                        "expected_outcome": "deny",
                        "expected_warning_count": None,
                    }
                ],
            },
            "must be an integer",
        ),
    ],
)
def test_invalid_policy_test_suites_are_rejected(suite: dict[str, Any], message: str) -> None:
    with pytest.raises(PolicyTestValidationError, match=message):
        PolicyTestSuite.from_dict(suite)


def test_policy_test_suite_load_and_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "suite.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "cases": [{"name": "default name", "input": {}, "expected_outcome": "review"}],
            }
        ),
        encoding="utf-8",
    )

    suite = load_policy_test_suite(path)

    assert suite.name == "policy tests"
    assert suite.cases[0].expected_outcome is Outcome.REVIEW
    assert PolicyTestSuite.from_dict(suite.to_dict()) == suite


def test_policy_test_inputs_are_recursively_immutable() -> None:
    source = {
        "schema_version": 1,
        "cases": [
            {
                "name": "immutable input",
                "input": {"action": {"operation": "read"}},
                "expected_outcome": "allow",
            }
        ],
    }
    suite = PolicyTestSuite.from_dict(source)
    source["cases"][0]["input"]["action"]["operation"] = "delete"
    serialized = suite.to_dict()
    serialized["cases"][0]["input"]["action"]["operation"] = "publish"

    assert suite.cases[0].input == {"action": {"operation": "read"}}
    assert suite.to_dict()["cases"][0]["input"] == {"action": {"operation": "read"}}


def test_direct_policy_test_case_rejects_non_string_key() -> None:
    with pytest.raises(PolicyTestValidationError, match="non-string object key"):
        PolicyTestCase.from_dict(
            {"name": "case", "input": {}, "expected_outcome": "deny", 1: "bad"},
            index=0,
        )
