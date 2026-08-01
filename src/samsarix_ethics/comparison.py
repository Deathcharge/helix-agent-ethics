# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Privacy-minimized comparison of baseline and candidate policy behavior."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, cast

from ._decision_observation import decision_change_names
from .engine import PolicyEngine
from .errors import SamsarixEthicsError
from .models import Decision, Outcome, Policy
from .testing import PolicyTestCase, PolicyTestSuite
from .validation import thaw_json_value

POLICY_COMPARISON_VERSION = 1


class PolicyComparisonStatus(StrEnum):
    """Result category for one comparison case."""

    UNCHANGED = "unchanged"
    CHANGED = "changed"
    ERROR = "error"


class PolicyComparisonChange(StrEnum):
    """Observable decision field that changed between policies."""

    OUTCOME = "outcome"
    MATCHED_RULES = "matched_rules"
    WARNING_COUNT = "warning_count"
    REASON_MESSAGES = "reason_messages"
    WARNING_MESSAGES = "warning_messages"


@dataclass(frozen=True, slots=True)
class PolicyComparisonSnapshot:
    """Input-free observable result from one policy evaluation."""

    outcome: Outcome | None
    matched_rules: tuple[str, ...]
    warning_count: int | None
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome.value if self.outcome is not None else None,
            "matched_rules": list(self.matched_rules),
            "warning_count": self.warning_count,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class PolicyComparisonResult:
    """Comparison result for one named suite case without its input."""

    name: str
    status: PolicyComparisonStatus
    changes: tuple[PolicyComparisonChange, ...]
    baseline: PolicyComparisonSnapshot
    candidate: PolicyComparisonSnapshot

    @property
    def authorization_changed(self) -> bool:
        return PolicyComparisonChange.OUTCOME in self.changes

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "changes": [change.value for change in self.changes],
            "authorization_changed": self.authorization_changed,
            "baseline": self.baseline.to_dict(),
            "candidate": self.candidate.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class PolicyComparisonReport:
    """Deterministic aggregate impact report for two policies and one suite."""

    suite_name: str
    baseline_policy_id: str
    baseline_policy_version: str
    baseline_policy_fingerprint: str
    candidate_policy_id: str
    candidate_policy_version: str
    candidate_policy_fingerprint: str
    results: tuple[PolicyComparisonResult, ...]
    comparison_version: int = POLICY_COMPARISON_VERSION

    @property
    def unchanged(self) -> int:
        return sum(result.status is PolicyComparisonStatus.UNCHANGED for result in self.results)

    @property
    def changed(self) -> int:
        return sum(result.status is PolicyComparisonStatus.CHANGED for result in self.results)

    @property
    def errors(self) -> int:
        return sum(result.status is PolicyComparisonStatus.ERROR for result in self.results)

    @property
    def authorization_changes(self) -> int:
        return sum(
            result.status is PolicyComparisonStatus.CHANGED and result.authorization_changed
            for result in self.results
        )

    @property
    def metadata_only_changes(self) -> int:
        return self.changed - self.authorization_changes

    @property
    def identical(self) -> bool:
        return self.changed == 0 and self.errors == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "comparison_version": self.comparison_version,
            "suite_name": self.suite_name,
            "baseline_policy_id": self.baseline_policy_id,
            "baseline_policy_version": self.baseline_policy_version,
            "baseline_policy_fingerprint": self.baseline_policy_fingerprint,
            "candidate_policy_id": self.candidate_policy_id,
            "candidate_policy_version": self.candidate_policy_version,
            "candidate_policy_fingerprint": self.candidate_policy_fingerprint,
            "total": len(self.results),
            "unchanged": self.unchanged,
            "changed": self.changed,
            "authorization_changes": self.authorization_changes,
            "metadata_only_changes": self.metadata_only_changes,
            "errors": self.errors,
            "identical": self.identical,
            "results": [result.to_dict() for result in self.results],
        }


@dataclass(frozen=True, slots=True)
class _CaseEvaluation:
    snapshot: PolicyComparisonSnapshot
    decision: Decision | None


def _evaluate_case(engine: PolicyEngine, case: PolicyTestCase) -> _CaseEvaluation:
    try:
        decision = engine.evaluate(thaw_json_value(case.input))
    except SamsarixEthicsError as exc:
        return _CaseEvaluation(
            snapshot=PolicyComparisonSnapshot(
                outcome=None,
                matched_rules=(),
                warning_count=None,
                error=str(exc),
            ),
            decision=None,
        )
    return _CaseEvaluation(
        snapshot=PolicyComparisonSnapshot(
            outcome=decision.outcome,
            matched_rules=decision.matched_rules,
            warning_count=len(decision.warnings),
            error=None,
        ),
        decision=decision,
    )


def compare_policies(
    baseline: Policy,
    candidate: Policy,
    suite: PolicyTestSuite,
) -> PolicyComparisonReport:
    """Compare two policies over the same bounded suite without reporting case inputs."""

    if not isinstance(baseline, Policy):
        raise TypeError("baseline must be a Policy")
    if not isinstance(candidate, Policy):
        raise TypeError("candidate must be a Policy")
    if not isinstance(suite, PolicyTestSuite):
        raise TypeError("suite must be a PolicyTestSuite")

    baseline_engine = PolicyEngine(baseline)
    candidate_engine = PolicyEngine(candidate)
    results: list[PolicyComparisonResult] = []
    for case in suite.cases:
        baseline_evaluation = _evaluate_case(baseline_engine, case)
        candidate_evaluation = _evaluate_case(candidate_engine, case)
        baseline_snapshot = baseline_evaluation.snapshot
        candidate_snapshot = candidate_evaluation.snapshot
        changes: list[PolicyComparisonChange] = []
        if baseline_snapshot.error is not None or candidate_snapshot.error is not None:
            status = PolicyComparisonStatus.ERROR
        else:
            baseline_decision = cast(Decision, baseline_evaluation.decision)
            candidate_decision = cast(Decision, candidate_evaluation.decision)
            changes.extend(
                PolicyComparisonChange(change)
                for change in decision_change_names(baseline_decision, candidate_decision)
            )
            status = PolicyComparisonStatus.CHANGED if changes else PolicyComparisonStatus.UNCHANGED
        results.append(
            PolicyComparisonResult(
                name=case.name,
                status=status,
                changes=tuple(changes),
                baseline=baseline_snapshot,
                candidate=candidate_snapshot,
            )
        )

    return PolicyComparisonReport(
        suite_name=suite.name,
        baseline_policy_id=baseline.id,
        baseline_policy_version=baseline.version,
        baseline_policy_fingerprint=baseline_engine.policy_fingerprint,
        candidate_policy_id=candidate.id,
        candidate_policy_version=candidate.version,
        candidate_policy_fingerprint=candidate_engine.policy_fingerprint,
        results=tuple(results),
    )
