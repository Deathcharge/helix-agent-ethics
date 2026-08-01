# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Privacy-minimized rule coverage from bounded policy regression suites."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import ContextContract
from .engine import PolicyEngine
from .errors import SamsarixEthicsError
from .models import Outcome, Policy
from .testing import PolicyTestSuite
from .validation import thaw_json_value

POLICY_COVERAGE_VERSION = 1


@dataclass(frozen=True, slots=True)
class PolicyCoverageError:
    """Input-free evaluation error for one named coverage case."""

    name: str
    error: str

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "error": self.error}


@dataclass(frozen=True, slots=True)
class PolicyCoverageReport:
    """Deterministic rule and outcome coverage for one policy and suite."""

    suite_name: str
    policy_id: str
    policy_version: str
    policy_fingerprint: str
    total_cases: int
    covered_rule_ids: tuple[str, ...]
    uncovered_rule_ids: tuple[str, ...]
    allow_cases: int
    deny_cases: int
    review_cases: int
    error_cases: tuple[PolicyCoverageError, ...]
    required_coverage_percent: int = 0
    coverage_version: int = POLICY_COVERAGE_VERSION

    @property
    def total_rules(self) -> int:
        return len(self.covered_rule_ids) + len(self.uncovered_rule_ids)

    @property
    def covered_rules(self) -> int:
        return len(self.covered_rule_ids)

    @property
    def uncovered_rules(self) -> int:
        return len(self.uncovered_rule_ids)

    @property
    def coverage_percent(self) -> float:
        if self.total_rules == 0:
            return 100.0
        return round(self.covered_rules * 100 / self.total_rules, 2)

    @property
    def evaluated_cases(self) -> int:
        return self.allow_cases + self.deny_cases + self.review_cases

    @property
    def errors(self) -> int:
        return len(self.error_cases)

    @property
    def threshold_met(self) -> bool:
        if self.errors:
            return False
        if self.total_rules == 0:
            return True
        return self.covered_rules * 100 >= self.required_coverage_percent * self.total_rules

    @property
    def complete(self) -> bool:
        return self.errors == 0 and self.uncovered_rules == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "coverage_version": self.coverage_version,
            "suite_name": self.suite_name,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "policy_fingerprint": self.policy_fingerprint,
            "total_rules": self.total_rules,
            "covered_rules": self.covered_rules,
            "uncovered_rules": self.uncovered_rules,
            "coverage_percent": self.coverage_percent,
            "required_coverage_percent": self.required_coverage_percent,
            "threshold_met": self.threshold_met,
            "complete": self.complete,
            "covered_rule_ids": list(self.covered_rule_ids),
            "uncovered_rule_ids": list(self.uncovered_rule_ids),
            "total_cases": self.total_cases,
            "evaluated_cases": self.evaluated_cases,
            "allow_cases": self.allow_cases,
            "deny_cases": self.deny_cases,
            "review_cases": self.review_cases,
            "errors": self.errors,
            "error_cases": [error.to_dict() for error in self.error_cases],
        }


def measure_policy_coverage(
    policy: Policy,
    suite: PolicyTestSuite,
    *,
    threshold: int = 0,
    context_contract: ContextContract | None = None,
) -> PolicyCoverageReport:
    """Measure which policy rules match a suite without retaining case inputs."""

    if not isinstance(policy, Policy):
        raise TypeError("policy must be a Policy")
    if not isinstance(suite, PolicyTestSuite):
        raise TypeError("suite must be a PolicyTestSuite")
    if isinstance(threshold, bool) or not isinstance(threshold, int) or not 0 <= threshold <= 100:
        raise ValueError("threshold must be an integer from 0 to 100")

    engine = PolicyEngine(policy, context_contract=context_contract)
    matched_rule_ids: set[str] = set()
    outcome_counts = {outcome: 0 for outcome in Outcome}
    error_cases: list[PolicyCoverageError] = []
    for case in suite.cases:
        try:
            decision = engine.evaluate(thaw_json_value(case.input))
        except SamsarixEthicsError as exc:
            error_cases.append(PolicyCoverageError(name=case.name, error=str(exc)))
            continue
        matched_rule_ids.update(decision.matched_rules)
        outcome_counts[decision.outcome] += 1

    covered_rule_ids = tuple(rule.id for rule in policy.rules if rule.id in matched_rule_ids)
    uncovered_rule_ids = tuple(rule.id for rule in policy.rules if rule.id not in matched_rule_ids)
    return PolicyCoverageReport(
        suite_name=suite.name,
        policy_id=policy.id,
        policy_version=policy.version,
        policy_fingerprint=engine.policy_fingerprint,
        total_cases=len(suite.cases),
        covered_rule_ids=covered_rule_ids,
        uncovered_rule_ids=uncovered_rule_ids,
        allow_cases=outcome_counts[Outcome.ALLOW],
        deny_cases=outcome_counts[Outcome.DENY],
        review_cases=outcome_counts[Outcome.REVIEW],
        error_cases=tuple(error_cases),
        required_coverage_percent=threshold,
    )
