# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Value-minimized policy evaluation explanations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .models import Effect, Outcome

POLICY_EXPLANATION_VERSION = 1


class ConditionExplanationStatus(StrEnum):
    """Observable result of one condition in short-circuit evaluation."""

    MATCHED = "matched"
    NOT_MATCHED = "not_matched"
    NOT_EVALUATED = "not_evaluated"


@dataclass(frozen=True, slots=True)
class ConditionExplanation:
    """Value-free evaluation status for one policy condition."""

    index: int
    field: str
    operator: str
    status: ConditionExplanationStatus

    def to_dict(self) -> dict[str, Any]:
        """Return the strict value-free JSON condition representation."""

        return {
            "index": self.index,
            "field": self.field,
            "operator": self.operator,
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True)
class RuleExplanation:
    """Value-free evaluation status for one policy rule."""

    rule_id: str
    effect: Effect
    priority: int
    matched: bool
    decisive: bool
    conditions: tuple[ConditionExplanation, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return the strict value-free JSON rule representation."""

        return {
            "rule_id": self.rule_id,
            "effect": self.effect.value,
            "priority": self.priority,
            "matched": self.matched,
            "decisive": self.decisive,
            "conditions": [condition.to_dict() for condition in self.conditions],
        }


@dataclass(frozen=True, slots=True)
class PolicyExplanation:
    """Deterministic input- and value-free explanation of one policy evaluation."""

    policy_id: str
    policy_version: str
    policy_fingerprint: str
    context_contract_fingerprint: str | None
    outcome: Outcome
    default_applied: bool
    matched_rule_ids: tuple[str, ...]
    decisive_rule_ids: tuple[str, ...]
    rules: tuple[RuleExplanation, ...]
    explanation_version: int = POLICY_EXPLANATION_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Return the versioned input- and value-free JSON explanation."""

        return {
            "explanation_version": self.explanation_version,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "policy_fingerprint": self.policy_fingerprint,
            "context_contract_fingerprint": self.context_contract_fingerprint,
            "outcome": self.outcome.value,
            "default_applied": self.default_applied,
            "matched_rule_ids": list(self.matched_rule_ids),
            "decisive_rule_ids": list(self.decisive_rule_ids),
            "evaluated_rules": len(self.rules),
            "rules": [rule.to_dict() for rule in self.rules],
        }
