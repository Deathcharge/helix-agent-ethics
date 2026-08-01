# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Deterministic evaluation engine with deny-overrides semantics."""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, cast

from .errors import EvaluationError, InputValidationError
from .models import Decision, Effect, Outcome, Policy, PolicyCondition
from .validation import validate_context

_MISSING = object()
MAX_BATCH_ITEMS = 1_000


def _field_value(context: Mapping[str, Any], path: str) -> Any:
    value: Any = context
    for part in path.split("."):
        if not isinstance(value, Mapping) or part not in value:
            return _MISSING
        value = value[part]
    return value


def _resolved_expected(context: Mapping[str, Any], condition: PolicyCondition) -> Any:
    expected = condition.value
    if isinstance(expected, Mapping) and set(expected) == {"$ref"}:
        referenced = _field_value(context, expected["$ref"])
        if referenced is _MISSING:
            raise EvaluationError(
                f"condition on {condition.field!r} references missing field {expected['$ref']!r}"
            )
        return referenced
    return expected


def _sequence_for_membership(value: Any, *, operator: str, role: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise EvaluationError(f"operator {operator!r} requires {role} to be an array")
    return cast(Sequence[Any], value)


def _json_equal(left: Any, right: Any) -> bool:
    """Compare JSON values without Python's ``True == 1`` type confusion."""

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


def _evaluate_condition(context: Mapping[str, Any], condition: PolicyCondition) -> bool:
    actual = _field_value(context, condition.field)
    operator = condition.operator
    if operator == "exists":
        return actual is not _MISSING
    if operator == "not_exists":
        return actual is _MISSING
    if actual is _MISSING:
        return False

    expected = _resolved_expected(context, condition)
    if operator == "eq":
        return _json_equal(actual, expected)
    if operator == "neq":
        return not _json_equal(actual, expected)
    if operator in {"in", "not_in"}:
        collection = _sequence_for_membership(expected, operator=operator, role="the policy value")
        matched = any(_json_equal(actual, item) for item in collection)
        return not matched if operator == "not_in" else matched
    if operator in {"contains", "not_contains"}:
        collection = _sequence_for_membership(actual, operator=operator, role="the input field")
        matched = any(_json_equal(expected, item) for item in collection)
        return not matched if operator == "not_contains" else matched
    if operator in {"starts_with", "ends_with"}:
        if not isinstance(actual, str) or not isinstance(expected, str):
            raise EvaluationError(f"operator {operator!r} requires two strings")
        return (
            actual.startswith(expected) if operator == "starts_with" else actual.endswith(expected)
        )
    if operator in {"gt", "gte", "lt", "lte"}:
        if isinstance(actual, bool) or isinstance(expected, bool):
            raise EvaluationError(f"operator {operator!r} does not accept booleans")
        numeric_pair = isinstance(actual, (int, float)) and isinstance(expected, (int, float))
        string_pair = isinstance(actual, str) and isinstance(expected, str)
        if not (numeric_pair or string_pair):
            raise EvaluationError(f"operator {operator!r} requires two numbers or two strings")
        if operator == "gt":
            return bool(actual > expected)
        if operator == "gte":
            return bool(actual >= expected)
        if operator == "lt":
            return bool(actual < expected)
        return bool(actual <= expected)
    raise EvaluationError(f"unsupported operator: {operator}")


class PolicyEngine:
    """Evaluate validated policies against caller-supplied JSON objects.

    Every rule is evaluated. A matching deny overrides review and allow; a matching
    review overrides allow. When no decisive rule matches, ``default_effect`` is used.
    Evaluation errors are raised so callers cannot accidentally treat malformed input
    as permission to execute an action.
    """

    def __init__(self, policy: Policy):
        self.policy = policy

    def evaluate(self, context: Mapping[str, Any]) -> Decision:
        context = validate_context(context)

        matched: list[tuple[int, str, Effect, str]] = []
        for rule in self.policy.rules:
            try:
                applies = all(
                    _evaluate_condition(context, condition) for condition in rule.conditions
                )
            except EvaluationError as exc:
                raise EvaluationError(f"rule {rule.id!r} failed: {exc}") from exc
            if applies:
                matched.append((rule.priority, rule.id, rule.effect, rule.message))

        matched.sort(key=lambda item: (item[0], item[1]))
        matched_ids = tuple(item[1] for item in matched)
        effects = {item[2] for item in matched}
        if Effect.DENY in effects:
            outcome = Outcome.DENY
        elif Effect.REVIEW in effects:
            outcome = Outcome.REVIEW
        elif Effect.ALLOW in effects:
            outcome = Outcome.ALLOW
        else:
            outcome = self.policy.default_effect

        deciding_effect = Effect(outcome.value)
        reasons = tuple(
            message or f"Rule {rule_id!r} matched with effect {effect.value!r}."
            for _, rule_id, effect, message in matched
            if effect == deciding_effect
        )
        if not reasons:
            reasons = (f"No decisive rule matched; policy default is {outcome.value!r}.",)
        warnings = tuple(
            message or f"Warning rule {rule_id!r} matched."
            for _, rule_id, effect, message in matched
            if effect == Effect.WARN
        )

        return Decision(
            decision_id=str(uuid.uuid4()),
            evaluated_at=datetime.now(UTC).isoformat(),
            policy_id=self.policy.id,
            policy_version=self.policy.version,
            outcome=outcome,
            allowed=outcome == Outcome.ALLOW,
            matched_rules=matched_ids,
            warnings=warnings,
            reasons=reasons,
            evaluated_rules=len(self.policy.rules),
        )

    def evaluate_many(self, contexts: Iterable[Mapping[str, Any]]) -> tuple[Decision, ...]:
        """Evaluate a bounded batch in input order."""

        try:
            iterator = iter(contexts)
        except TypeError as exc:
            raise InputValidationError("evaluation batch must be iterable") from exc

        decisions: list[Decision] = []
        for index, context in enumerate(iterator):
            if index >= MAX_BATCH_ITEMS:
                raise InputValidationError(
                    f"evaluation batch exceeds the limit of {MAX_BATCH_ITEMS} items"
                )
            try:
                decisions.append(self.evaluate(context))
            except InputValidationError as exc:
                raise InputValidationError(f"evaluation batch item {index}: {exc}") from exc
        return tuple(decisions)
