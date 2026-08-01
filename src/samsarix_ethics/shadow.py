# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Baseline-authoritative shadow evaluation for safe policy rollouts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from time import perf_counter_ns
from typing import Any, cast

from ._decision_observation import decision_change_names
from .contracts import ContextContract
from .engine import PolicyEngine
from .errors import SamsarixEthicsError
from .models import Decision, Outcome, Policy
from .validation import thaw_json_value, validate_context

POLICY_SHADOW_VERSION = 1


class PolicyShadowStatus(StrEnum):
    """Candidate observation status for one authoritative evaluation."""

    UNCHANGED = "unchanged"
    CHANGED = "changed"
    ERROR = "error"


class PolicyShadowChange(StrEnum):
    """Observable decision field that differs from the authoritative baseline."""

    OUTCOME = "outcome"
    MATCHED_RULES = "matched_rules"
    WARNING_COUNT = "warning_count"
    REASON_MESSAGES = "reason_messages"
    WARNING_MESSAGES = "warning_messages"


@dataclass(frozen=True, slots=True)
class PolicyShadowSnapshot:
    """Input-free decision telemetry for one side of a shadow evaluation."""

    policy_id: str
    policy_version: str
    policy_fingerprint: str
    decision_id: str | None
    evaluated_at: str | None
    outcome: Outcome | None
    matched_rules: tuple[str, ...]
    warning_count: int | None
    evaluated_rules: int | None
    evaluation_duration_ns: int
    error: str | None

    @classmethod
    def from_decision(
        cls,
        decision: Decision,
        *,
        evaluation_duration_ns: int,
    ) -> PolicyShadowSnapshot:
        """Build a minimized snapshot from a successful decision."""

        if not isinstance(decision, Decision):
            raise TypeError("decision must be a Decision")
        if (
            isinstance(evaluation_duration_ns, bool)
            or not isinstance(evaluation_duration_ns, int)
            or evaluation_duration_ns < 0
        ):
            raise ValueError("evaluation_duration_ns must be a non-negative integer")
        return cls(
            policy_id=decision.policy_id,
            policy_version=decision.policy_version,
            policy_fingerprint=decision.policy_fingerprint,
            decision_id=decision.decision_id,
            evaluated_at=decision.evaluated_at,
            outcome=decision.outcome,
            matched_rules=decision.matched_rules,
            warning_count=len(decision.warnings),
            evaluated_rules=decision.evaluated_rules,
            evaluation_duration_ns=evaluation_duration_ns,
            error=None,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the versioned JSON-compatible snapshot representation."""

        return {
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "policy_fingerprint": self.policy_fingerprint,
            "decision_id": self.decision_id,
            "evaluated_at": self.evaluated_at,
            "outcome": self.outcome.value if self.outcome is not None else None,
            "matched_rules": list(self.matched_rules),
            "warning_count": self.warning_count,
            "evaluated_rules": self.evaluated_rules,
            "evaluation_duration_ns": self.evaluation_duration_ns,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class PolicyShadowEvaluation:
    """One baseline decision paired with observational candidate telemetry."""

    authoritative_decision: Decision
    authoritative: PolicyShadowSnapshot
    candidate_decision: Decision | None
    candidate: PolicyShadowSnapshot
    status: PolicyShadowStatus
    changes: tuple[PolicyShadowChange, ...]
    shadow_version: int = POLICY_SHADOW_VERSION

    @property
    def authorization_changed(self) -> bool:
        """Whether the successful candidate produced a different outcome."""

        return PolicyShadowChange.OUTCOME in self.changes

    def to_dict(self) -> dict[str, Any]:
        """Return input-free rollout telemetry; policy messages remain excluded."""

        return {
            "shadow_version": self.shadow_version,
            "status": self.status.value,
            "changes": [change.value for change in self.changes],
            "authorization_changed": self.authorization_changed,
            "authoritative": self.authoritative.to_dict(),
            "candidate": self.candidate.to_dict(),
        }


class PolicyShadowEvaluator:
    """Evaluate a candidate observationally after an authoritative baseline.

    Baseline validation or evaluation errors propagate and must be treated as
    non-authorization. Candidate :class:`SamsarixEthicsError` failures are retained in
    the returned telemetry and never replace the successful baseline decision.
    """

    def __init__(
        self,
        baseline: Policy,
        candidate: Policy,
        *,
        context_contract: ContextContract | None = None,
    ) -> None:
        if not isinstance(baseline, Policy):
            raise TypeError("baseline must be a Policy")
        if not isinstance(candidate, Policy):
            raise TypeError("candidate must be a Policy")
        self.baseline_policy = baseline
        self.candidate_policy = candidate
        self.context_contract = context_contract
        self._baseline_engine = PolicyEngine(baseline, context_contract=context_contract)
        self._candidate_engine = PolicyEngine(candidate, context_contract=context_contract)

    @property
    def baseline_policy_fingerprint(self) -> str:
        """Return the exact authoritative policy fingerprint."""

        return self._baseline_engine.policy_fingerprint

    @property
    def candidate_policy_fingerprint(self) -> str:
        """Return the exact observational policy fingerprint."""

        return self._candidate_engine.policy_fingerprint

    def evaluate(self, context: Mapping[str, Any]) -> PolicyShadowEvaluation:
        """Evaluate one detached context, keeping the baseline authoritative."""

        validated = validate_context(context)
        detached = cast(Mapping[str, Any], thaw_json_value(validated))
        baseline_started_ns = perf_counter_ns()
        authoritative_decision = self._baseline_engine.evaluate(detached)
        baseline_duration_ns = perf_counter_ns() - baseline_started_ns
        authoritative_snapshot = PolicyShadowSnapshot.from_decision(
            authoritative_decision,
            evaluation_duration_ns=baseline_duration_ns,
        )
        candidate_started_ns = perf_counter_ns()
        try:
            candidate_decision = self._candidate_engine.evaluate(detached)
        except SamsarixEthicsError as exc:
            candidate_duration_ns = perf_counter_ns() - candidate_started_ns
            candidate_snapshot = PolicyShadowSnapshot(
                policy_id=self.candidate_policy.id,
                policy_version=self.candidate_policy.version,
                policy_fingerprint=self.candidate_policy_fingerprint,
                decision_id=None,
                evaluated_at=None,
                outcome=None,
                matched_rules=(),
                warning_count=None,
                evaluated_rules=None,
                evaluation_duration_ns=candidate_duration_ns,
                error=str(exc),
            )
            return PolicyShadowEvaluation(
                authoritative_decision=authoritative_decision,
                authoritative=authoritative_snapshot,
                candidate_decision=None,
                candidate=candidate_snapshot,
                status=PolicyShadowStatus.ERROR,
                changes=(),
            )

        candidate_duration_ns = perf_counter_ns() - candidate_started_ns
        changes = tuple(
            PolicyShadowChange(change)
            for change in decision_change_names(authoritative_decision, candidate_decision)
        )
        return PolicyShadowEvaluation(
            authoritative_decision=authoritative_decision,
            authoritative=authoritative_snapshot,
            candidate_decision=candidate_decision,
            candidate=PolicyShadowSnapshot.from_decision(
                candidate_decision,
                evaluation_duration_ns=candidate_duration_ns,
            ),
            status=PolicyShadowStatus.CHANGED if changes else PolicyShadowStatus.UNCHANGED,
            changes=changes,
        )
