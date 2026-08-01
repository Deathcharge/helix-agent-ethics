# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Shared observable-decision comparison for rollout tooling."""

from __future__ import annotations

from typing import Literal, TypeAlias

from .models import Decision

DecisionChangeName: TypeAlias = Literal[
    "outcome",
    "matched_rules",
    "warning_count",
    "reason_messages",
    "warning_messages",
]


def decision_change_names(
    baseline: Decision,
    candidate: Decision,
) -> tuple[DecisionChangeName, ...]:
    """Return privacy-safe labels for observable decision differences."""

    changes: list[DecisionChangeName] = []
    if baseline.outcome is not candidate.outcome:
        changes.append("outcome")
    if baseline.matched_rules != candidate.matched_rules:
        changes.append("matched_rules")
    if len(baseline.warnings) != len(candidate.warnings):
        changes.append("warning_count")
    if baseline.reasons != candidate.reasons:
        changes.append("reason_messages")
    if baseline.warnings != candidate.warnings:
        changes.append("warning_messages")
    return tuple(changes)
