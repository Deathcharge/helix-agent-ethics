# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Validated policy-test suites and deterministic regression reports."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from .engine import MAX_BATCH_ITEMS, PolicyEngine
from .errors import InputValidationError, PolicyTestValidationError, SamsarixEthicsError
from .io import _parse_json, _read_file
from .models import Outcome, Policy
from .validation import (
    freeze_json_value,
    thaw_json_value,
    validate_context,
    validate_json_shape,
)

MAX_POLICY_TEST_BYTES = 4_194_304
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


class PolicyTestStatus(StrEnum):
    """Outcome of one policy regression case."""

    PASS = "pass"  # noqa: S105 - result label, not a credential
    FAIL = "fail"
    ERROR = "error"


def _mapping(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PolicyTestValidationError(f"{location} must be a JSON object")
    if not all(isinstance(key, str) for key in value):
        raise PolicyTestValidationError(f"{location} contains a non-string object key")
    return value


def _keys(data: dict[str, Any], *, required: set[str], optional: set[str], location: str) -> None:
    missing = sorted(required - data.keys())
    unknown = sorted(data.keys() - required - optional)
    if missing:
        raise PolicyTestValidationError(f"{location} is missing: {', '.join(missing)}")
    if unknown:
        raise PolicyTestValidationError(f"{location} has unknown fields: {', '.join(unknown)}")


@dataclass(frozen=True, slots=True)
class PolicyTestCase:
    """One expected policy decision without retaining it in the report."""

    name: str
    input: Mapping[str, Any]
    expected_outcome: Outcome
    expected_matched_rules: tuple[str, ...] | None = None
    expected_warning_count: int | None = None

    @classmethod
    def from_dict(cls, value: Any, *, index: int) -> PolicyTestCase:
        location = f"policy test cases[{index}]"
        try:
            validate_json_shape(value, label=location)
        except InputValidationError as exc:
            raise PolicyTestValidationError(str(exc)) from exc
        data = _mapping(value, location)
        _keys(
            data,
            required={"name", "input", "expected_outcome"},
            optional={"expected_matched_rules", "expected_warning_count"},
            location=location,
        )
        name = data["name"]
        if not isinstance(name, str) or not 1 <= len(name) <= 200:
            raise PolicyTestValidationError(
                f"{location}.name must be a string from 1 to 200 characters"
            )
        input_value = data["input"]
        try:
            validate_context(input_value, label=f"{location}.input")
        except InputValidationError as exc:
            raise PolicyTestValidationError(str(exc)) from exc
        try:
            expected_outcome = Outcome(data["expected_outcome"])
        except (TypeError, ValueError) as exc:
            raise PolicyTestValidationError(
                f"{location}.expected_outcome must be allow, deny, or review"
            ) from exc

        matched_value = data.get("expected_matched_rules")
        expected_matched_rules: tuple[str, ...] | None = None
        if "expected_matched_rules" in data:
            if not isinstance(matched_value, list) or not all(
                isinstance(item, str) and _IDENTIFIER.fullmatch(item) for item in matched_value
            ):
                raise PolicyTestValidationError(
                    f"{location}.expected_matched_rules must be an array of rule ids"
                )
            if len(matched_value) > MAX_BATCH_ITEMS:
                raise PolicyTestValidationError(
                    f"{location}.expected_matched_rules exceeds the limit of {MAX_BATCH_ITEMS}"
                )
            if len(set(matched_value)) != len(matched_value):
                raise PolicyTestValidationError(
                    f"{location}.expected_matched_rules contains duplicates"
                )
            expected_matched_rules = tuple(matched_value)

        warning_count = data.get("expected_warning_count")
        if "expected_warning_count" in data and (
            isinstance(warning_count, bool)
            or not isinstance(warning_count, int)
            or not 0 <= warning_count <= MAX_BATCH_ITEMS
        ):
            raise PolicyTestValidationError(
                f"{location}.expected_warning_count must be an integer from 0 to {MAX_BATCH_ITEMS}"
            )
        return cls(
            name=name,
            input=freeze_json_value(input_value),
            expected_outcome=expected_outcome,
            expected_matched_rules=expected_matched_rules,
            expected_warning_count=warning_count,
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.name,
            "input": thaw_json_value(self.input),
            "expected_outcome": self.expected_outcome.value,
        }
        if self.expected_matched_rules is not None:
            data["expected_matched_rules"] = list(self.expected_matched_rules)
        if self.expected_warning_count is not None:
            data["expected_warning_count"] = self.expected_warning_count
        return data


@dataclass(frozen=True, slots=True)
class PolicyTestSuite:
    """A bounded, versioned collection of policy regression cases."""

    schema_version: int
    name: str
    cases: tuple[PolicyTestCase, ...]

    @classmethod
    def from_dict(cls, value: Any) -> PolicyTestSuite:
        data = _mapping(value, "policy test suite")
        _keys(
            data,
            required={"schema_version", "cases"},
            optional={"name"},
            location="policy test suite",
        )
        if isinstance(data["schema_version"], bool) or data["schema_version"] != 1:
            raise PolicyTestValidationError("policy test suite.schema_version must be 1")
        name = data.get("name", "policy tests")
        if not isinstance(name, str) or not 1 <= len(name) <= 200:
            raise PolicyTestValidationError(
                "policy test suite.name must be a string from 1 to 200 characters"
            )
        cases_value = data["cases"]
        if not isinstance(cases_value, list):
            raise PolicyTestValidationError("policy test suite.cases must be a JSON array")
        if not 1 <= len(cases_value) <= MAX_BATCH_ITEMS:
            raise PolicyTestValidationError(
                f"policy test suite.cases must contain from 1 to {MAX_BATCH_ITEMS} cases"
            )
        cases = tuple(
            PolicyTestCase.from_dict(item, index=index) for index, item in enumerate(cases_value)
        )
        names = [case.name for case in cases]
        duplicates = sorted({case_name for case_name in names if names.count(case_name) > 1})
        if duplicates:
            raise PolicyTestValidationError(
                f"policy test suite.cases has duplicate names: {', '.join(duplicates)}"
            )
        return cls(schema_version=1, name=name, cases=cases)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "cases": [case.to_dict() for case in self.cases],
        }


@dataclass(frozen=True, slots=True)
class PolicyTestResult:
    """One input-free test result suitable for logs and CI output."""

    name: str
    status: PolicyTestStatus
    expected_outcome: Outcome
    actual_outcome: Outcome | None
    expected_matched_rules: tuple[str, ...] | None
    actual_matched_rules: tuple[str, ...]
    failures: tuple[str, ...]
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "expected_outcome": self.expected_outcome.value,
            "actual_outcome": self.actual_outcome.value if self.actual_outcome else None,
            "expected_matched_rules": (
                list(self.expected_matched_rules)
                if self.expected_matched_rules is not None
                else None
            ),
            "actual_matched_rules": list(self.actual_matched_rules),
            "failures": list(self.failures),
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class PolicyTestReport:
    """Aggregate deterministic policy-test result."""

    suite_name: str
    policy_id: str
    policy_version: str
    policy_fingerprint: str
    results: tuple[PolicyTestResult, ...]

    @property
    def passed(self) -> int:
        return sum(result.status is PolicyTestStatus.PASS for result in self.results)

    @property
    def failed(self) -> int:
        return sum(result.status is PolicyTestStatus.FAIL for result in self.results)

    @property
    def errors(self) -> int:
        return sum(result.status is PolicyTestStatus.ERROR for result in self.results)

    @property
    def successful(self) -> bool:
        return self.passed == len(self.results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite_name": self.suite_name,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "policy_fingerprint": self.policy_fingerprint,
            "total": len(self.results),
            "passed": self.passed,
            "failed": self.failed,
            "errors": self.errors,
            "successful": self.successful,
            "results": [result.to_dict() for result in self.results],
        }


def load_policy_test_suite(path: str | Path) -> PolicyTestSuite:
    """Load and validate a bounded JSON policy-test suite."""

    try:
        value = _parse_json(
            _read_file(path, max_bytes=MAX_POLICY_TEST_BYTES, label="policy test suite"),
            label="policy test suite",
        )
        return PolicyTestSuite.from_dict(value)
    except InputValidationError as exc:
        raise PolicyTestValidationError(str(exc)) from exc


def run_policy_tests(policy: Policy, suite: PolicyTestSuite) -> PolicyTestReport:
    """Run every case, preserving failures and evaluation errors in one report."""

    engine = PolicyEngine(policy)
    results: list[PolicyTestResult] = []
    for case in suite.cases:
        try:
            decision = engine.evaluate(thaw_json_value(case.input))
        except SamsarixEthicsError as exc:
            results.append(
                PolicyTestResult(
                    name=case.name,
                    status=PolicyTestStatus.ERROR,
                    expected_outcome=case.expected_outcome,
                    actual_outcome=None,
                    expected_matched_rules=case.expected_matched_rules,
                    actual_matched_rules=(),
                    failures=(),
                    error=str(exc),
                )
            )
            continue

        failures: list[str] = []
        if decision.outcome is not case.expected_outcome:
            failures.append(
                f"expected outcome {case.expected_outcome.value!r}, got {decision.outcome.value!r}"
            )
        if (
            case.expected_matched_rules is not None
            and decision.matched_rules != case.expected_matched_rules
        ):
            failures.append(
                "expected matched rules "
                f"{list(case.expected_matched_rules)!r}, got {list(decision.matched_rules)!r}"
            )
        if (
            case.expected_warning_count is not None
            and len(decision.warnings) != case.expected_warning_count
        ):
            failures.append(
                f"expected {case.expected_warning_count} warnings, got {len(decision.warnings)}"
            )
        results.append(
            PolicyTestResult(
                name=case.name,
                status=PolicyTestStatus.FAIL if failures else PolicyTestStatus.PASS,
                expected_outcome=case.expected_outcome,
                actual_outcome=decision.outcome,
                expected_matched_rules=case.expected_matched_rules,
                actual_matched_rules=decision.matched_rules,
                failures=tuple(failures),
                error=None,
            )
        )
    return PolicyTestReport(
        suite_name=suite.name,
        policy_id=policy.id,
        policy_version=policy.version,
        policy_fingerprint=engine.policy_fingerprint,
        results=tuple(results),
    )
