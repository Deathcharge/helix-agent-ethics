# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Deterministic, value-minimized policy authoring diagnostics."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .models import Effect, Outcome, Policy, PolicyCondition, PolicyRule
from .provenance import fingerprint_policy

POLICY_LINT_VERSION = 1


class PolicyLintSeverity(StrEnum):
    """Stable finding severity ordered from most to least consequential."""

    SECURITY_WARNING = "security-warning"
    WARNING = "warning"
    SUGGESTION = "suggestion"


class PolicyLintCode(StrEnum):
    """Stable machine-readable code for one authoring diagnostic."""

    DEFAULT_ALLOW = "SAE001"
    UNCONDITIONAL_ALLOW = "SAE002"
    UNREACHABLE_RULE = "SAE101"
    DUPLICATE_CONDITION = "SAE201"
    MISSING_MESSAGE = "SAE202"


_SEVERITY_RANK = {
    PolicyLintSeverity.SECURITY_WARNING: 3,
    PolicyLintSeverity.WARNING: 2,
    PolicyLintSeverity.SUGGESTION: 1,
}


@dataclass(frozen=True, slots=True)
class PolicyLintFinding:
    """One value-minimized finding at policy or rule/condition scope."""

    code: PolicyLintCode
    severity: PolicyLintSeverity
    message: str
    rule_id: str | None = None
    condition_indices: tuple[int, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "severity": self.severity.value,
            "message": self.message,
            "rule_id": self.rule_id,
            "condition_indices": list(self.condition_indices),
        }


@dataclass(frozen=True, slots=True)
class PolicyLintReport:
    """Deterministic aggregate diagnostics for one validated policy."""

    policy_id: str
    policy_version: str
    policy_fingerprint: str
    findings: tuple[PolicyLintFinding, ...]
    fail_on: PolicyLintSeverity | None = PolicyLintSeverity.SECURITY_WARNING
    lint_version: int = POLICY_LINT_VERSION

    @property
    def security_warnings(self) -> int:
        return sum(
            finding.severity is PolicyLintSeverity.SECURITY_WARNING for finding in self.findings
        )

    @property
    def warnings(self) -> int:
        return sum(finding.severity is PolicyLintSeverity.WARNING for finding in self.findings)

    @property
    def suggestions(self) -> int:
        return sum(finding.severity is PolicyLintSeverity.SUGGESTION for finding in self.findings)

    @property
    def blocking_findings(self) -> int:
        if self.fail_on is None:
            return 0
        threshold = _SEVERITY_RANK[self.fail_on]
        return sum(_SEVERITY_RANK[finding.severity] >= threshold for finding in self.findings)

    @property
    def passed(self) -> bool:
        return self.blocking_findings == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "lint_version": self.lint_version,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "policy_fingerprint": self.policy_fingerprint,
            "fail_on": self.fail_on.value if self.fail_on is not None else "none",
            "total_findings": len(self.findings),
            "security_warnings": self.security_warnings,
            "warnings": self.warnings,
            "suggestions": self.suggestions,
            "blocking_findings": self.blocking_findings,
            "passed": self.passed,
            "findings": [finding.to_dict() for finding in self.findings],
        }


def _json_equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return bool(left == right)
    left_array = isinstance(left, Sequence) and not isinstance(left, (str, bytes, bytearray))
    right_array = isinstance(right, Sequence) and not isinstance(right, (str, bytes, bytearray))
    if left_array or right_array:
        if not (left_array and right_array):
            return False
        return len(left) == len(right) and all(
            _json_equal(left_item, right_item)
            for left_item, right_item in zip(left, right, strict=True)
        )
    if isinstance(left, Mapping) or isinstance(right, Mapping):
        if not (isinstance(left, Mapping) and isinstance(right, Mapping)):
            return False
        return left.keys() == right.keys() and all(
            _json_equal(left[key], right[key]) for key in left
        )
    if type(left) is not type(right):
        return False
    return bool(left == right)


def _condition_equal(left: PolicyCondition, right: PolicyCondition) -> bool:
    return (
        left.field == right.field
        and left.operator == right.operator
        and _json_equal(left.value, right.value)
    )


def _duplicate_condition_groups(rule: PolicyRule) -> tuple[tuple[int, ...], ...]:
    groups: list[tuple[int, ...]] = []
    consumed: set[int] = set()
    for index, condition in enumerate(rule.conditions):
        if index in consumed:
            continue
        duplicates = tuple(
            candidate_index
            for candidate_index in range(index, len(rule.conditions))
            if _condition_equal(condition, rule.conditions[candidate_index])
        )
        if len(duplicates) > 1:
            groups.append(duplicates)
            consumed.update(duplicates)
    return tuple(groups)


def _intersect_values(left: list[Any], right: list[Any]) -> list[Any]:
    return [item for item in left if any(_json_equal(item, candidate) for candidate in right)]


def _impossible_condition_indices(rule: PolicyRule) -> tuple[int, ...]:
    by_field: dict[str, list[tuple[int, PolicyCondition]]] = {}
    for index, condition in enumerate(rule.conditions):
        by_field.setdefault(condition.field, []).append((index, condition))

    for field_conditions in by_field.values():
        not_exists = [
            index for index, condition in field_conditions if condition.operator == "not_exists"
        ]
        requires_value = [
            index for index, condition in field_conditions if condition.operator != "not_exists"
        ]
        if not_exists and requires_value:
            return tuple(sorted({*not_exists, *requires_value}))

        allowed: list[Any] | None = None
        excluded: list[Any] = []
        relevant_indices: list[int] = []
        for index, condition in field_conditions:
            expected = condition.value
            if isinstance(expected, Mapping):
                continue
            candidates: list[Any] | None = None
            exclusions: list[Any] = []
            if condition.operator == "eq":
                candidates = [expected]
            elif condition.operator == "in":
                candidates = list(expected)
            elif condition.operator == "neq":
                exclusions = [expected]
            elif condition.operator == "not_in":
                exclusions = list(expected)
            else:
                continue
            relevant_indices.append(index)
            if candidates is not None:
                allowed = candidates if allowed is None else _intersect_values(allowed, candidates)
            excluded.extend(exclusions)

        if allowed is not None:
            possible = [
                item
                for item in allowed
                if not any(_json_equal(item, excluded_item) for excluded_item in excluded)
            ]
            if not possible:
                return tuple(relevant_indices)
    return ()


def lint_policy(
    policy: Policy,
    *,
    fail_on: PolicyLintSeverity | None = PolicyLintSeverity.SECURITY_WARNING,
) -> PolicyLintReport:
    """Return deterministic diagnostics without exposing policy condition values."""

    if not isinstance(policy, Policy):
        raise TypeError("policy must be a Policy")
    if fail_on is not None and not isinstance(fail_on, PolicyLintSeverity):
        raise TypeError("fail_on must be a PolicyLintSeverity or None")

    findings: list[PolicyLintFinding] = []
    if policy.default_effect is Outcome.ALLOW:
        findings.append(
            PolicyLintFinding(
                code=PolicyLintCode.DEFAULT_ALLOW,
                severity=PolicyLintSeverity.SECURITY_WARNING,
                message="Policy defaults to allow when no decisive rule matches.",
            )
        )

    for rule in policy.rules:
        if rule.effect is Effect.ALLOW and not rule.conditions:
            findings.append(
                PolicyLintFinding(
                    code=PolicyLintCode.UNCONDITIONAL_ALLOW,
                    severity=PolicyLintSeverity.SECURITY_WARNING,
                    message="Allow rule has no conditions and matches every valid input.",
                    rule_id=rule.id,
                )
            )

        impossible_indices = _impossible_condition_indices(rule)
        if impossible_indices:
            findings.append(
                PolicyLintFinding(
                    code=PolicyLintCode.UNREACHABLE_RULE,
                    severity=PolicyLintSeverity.WARNING,
                    message="Rule can never match because its conditions are contradictory.",
                    rule_id=rule.id,
                    condition_indices=impossible_indices,
                )
            )

        for duplicate_indices in _duplicate_condition_groups(rule):
            findings.append(
                PolicyLintFinding(
                    code=PolicyLintCode.DUPLICATE_CONDITION,
                    severity=PolicyLintSeverity.SUGGESTION,
                    message="Rule repeats a semantically identical condition.",
                    rule_id=rule.id,
                    condition_indices=duplicate_indices,
                )
            )

        if (
            rule.effect in {Effect.ALLOW, Effect.DENY, Effect.REVIEW, Effect.WARN}
            and not rule.message
        ):
            findings.append(
                PolicyLintFinding(
                    code=PolicyLintCode.MISSING_MESSAGE,
                    severity=PolicyLintSeverity.SUGGESTION,
                    message="Rule relies on a generated explanation because message is empty.",
                    rule_id=rule.id,
                )
            )

    return PolicyLintReport(
        policy_id=policy.id,
        policy_version=policy.version,
        policy_fingerprint=fingerprint_policy(policy),
        findings=tuple(findings),
        fail_on=fail_on,
    )
