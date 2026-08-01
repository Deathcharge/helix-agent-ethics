# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Validated, immutable policy and decision models."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any, ClassVar

from .errors import InputValidationError, PolicyValidationError
from .validation import validate_json_shape

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_FIELD_PATH = re.compile(r"^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*$")


class Effect(StrEnum):
    """Effect produced when a rule matches."""

    ALLOW = "allow"
    DENY = "deny"
    REVIEW = "review"
    WARN = "warn"
    AUDIT = "audit"


class Outcome(StrEnum):
    """Final action-gate outcome."""

    ALLOW = "allow"
    DENY = "deny"
    REVIEW = "review"


def _expect_mapping(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PolicyValidationError(f"{location} must be a JSON object")
    if not all(isinstance(key, str) for key in value):
        raise PolicyValidationError(f"{location} contains a non-string key")
    return value


def _validate_policy_json_shape(value: Any, location: str) -> None:
    try:
        validate_json_shape(value, label=location)
    except InputValidationError as exc:
        raise PolicyValidationError(str(exc)) from exc


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_thaw_json(item) for item in value]
    return value


def _check_keys(
    data: dict[str, Any], *, required: set[str], optional: set[str], location: str
) -> None:
    missing = sorted(required - data.keys())
    unknown = sorted(data.keys() - required - optional)
    if missing:
        raise PolicyValidationError(f"{location} is missing: {', '.join(missing)}")
    if unknown:
        raise PolicyValidationError(f"{location} has unknown fields: {', '.join(unknown)}")


def _identifier(value: Any, location: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise PolicyValidationError(
            f"{location} must be 1-128 characters using letters, digits, '.', '_', ':', or '-'"
        )
    return value


@dataclass(frozen=True, slots=True)
class PolicyCondition:
    """One comparison against a dotted path in the evaluation input."""

    SUPPORTED_OPERATORS: ClassVar[frozenset[str]] = frozenset(
        {
            "contains",
            "ends_with",
            "eq",
            "exists",
            "gt",
            "gte",
            "in",
            "lt",
            "lte",
            "neq",
            "not_contains",
            "not_exists",
            "not_in",
            "starts_with",
        }
    )

    field: str
    operator: str
    value: Any = None

    @classmethod
    def from_dict(cls, value: Any, *, location: str) -> PolicyCondition:
        _validate_policy_json_shape(value, location)
        data = _expect_mapping(value, location)
        _check_keys(
            data,
            required={"field", "operator"},
            optional={"value"},
            location=location,
        )
        field = data["field"]
        operator = data["operator"]
        if not isinstance(field, str) or len(field) > 256 or not _FIELD_PATH.fullmatch(field):
            raise PolicyValidationError(f"{location}.field is not a valid dotted field path")
        if not isinstance(operator, str) or operator not in cls.SUPPORTED_OPERATORS:
            supported = ", ".join(sorted(cls.SUPPORTED_OPERATORS))
            raise PolicyValidationError(f"{location}.operator must be one of: {supported}")
        if operator in {"exists", "not_exists"} and "value" in data:
            raise PolicyValidationError(
                f"{location}.value is not allowed for operator {operator!r}"
            )
        if operator not in {"exists", "not_exists"} and "value" not in data:
            raise PolicyValidationError(f"{location}.value is required for operator {operator!r}")
        expected = data.get("value")
        if isinstance(expected, Mapping):
            if set(expected) != {"$ref"} or not isinstance(expected["$ref"], str):
                raise PolicyValidationError(
                    f"{location}.value objects must contain only a string '$ref' field"
                )
            if len(expected["$ref"]) > 256 or not _FIELD_PATH.fullmatch(expected["$ref"]):
                raise PolicyValidationError(f"{location}.value.$ref is not a valid field path")
        if operator in {"in", "not_in"} and not isinstance(expected, (list, dict)):
            raise PolicyValidationError(
                f"{location}.value must be a JSON array or '$ref' for operator {operator!r}"
            )
        return cls(field=field, operator=operator, value=_freeze_json(expected))

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"field": self.field, "operator": self.operator}
        if self.operator not in {"exists", "not_exists"}:
            data["value"] = _thaw_json(self.value)
        return data


@dataclass(frozen=True, slots=True)
class PolicyRule:
    """A named policy rule; all of its conditions must match."""

    id: str
    effect: Effect
    conditions: tuple[PolicyCondition, ...]
    message: str
    priority: int = 100

    @classmethod
    def from_dict(cls, value: Any, *, index: int) -> PolicyRule:
        location = f"rules[{index}]"
        _validate_policy_json_shape(value, location)
        data = _expect_mapping(value, location)
        _check_keys(
            data,
            required={"id", "effect", "conditions"},
            optional={"message", "priority"},
            location=location,
        )
        rule_id = _identifier(data["id"], f"{location}.id")
        try:
            effect = Effect(data["effect"])
        except (TypeError, ValueError) as exc:
            raise PolicyValidationError(
                f"{location}.effect must be one of: {', '.join(Effect)}"
            ) from exc
        conditions_value = data["conditions"]
        if not isinstance(conditions_value, list):
            raise PolicyValidationError(f"{location}.conditions must be a JSON array")
        if len(conditions_value) > 32:
            raise PolicyValidationError(f"{location}.conditions exceeds the limit of 32")
        conditions = tuple(
            PolicyCondition.from_dict(item, location=f"{location}.conditions[{condition_index}]")
            for condition_index, item in enumerate(conditions_value)
        )
        message = data.get("message", "")
        if not isinstance(message, str) or len(message) > 500:
            raise PolicyValidationError(
                f"{location}.message must be a string of at most 500 characters"
            )
        priority = data.get("priority", 100)
        if (
            isinstance(priority, bool)
            or not isinstance(priority, int)
            or not -10_000 <= priority <= 10_000
        ):
            raise PolicyValidationError(
                f"{location}.priority must be an integer from -10000 to 10000"
            )
        return cls(
            id=rule_id,
            effect=effect,
            conditions=conditions,
            message=message,
            priority=priority,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "effect": self.effect.value,
            "conditions": [condition.to_dict() for condition in self.conditions],
            "message": self.message,
            "priority": self.priority,
        }


@dataclass(frozen=True, slots=True)
class Policy:
    """A validated policy document."""

    schema_version: int
    id: str
    version: str
    description: str
    default_effect: Outcome
    rules: tuple[PolicyRule, ...]

    @classmethod
    def from_dict(cls, value: Any) -> Policy:
        _validate_policy_json_shape(value, "policy")
        data = _expect_mapping(value, "policy")
        _check_keys(
            data,
            required={"schema_version", "id", "version", "default_effect", "rules"},
            optional={"description"},
            location="policy",
        )
        if data["schema_version"] != 1:
            raise PolicyValidationError("policy.schema_version must be 1")
        policy_id = _identifier(data["id"], "policy.id")
        version = _identifier(data["version"], "policy.version")
        description = data.get("description", "")
        if not isinstance(description, str) or len(description) > 1_000:
            raise PolicyValidationError(
                "policy.description must be a string of at most 1000 characters"
            )
        try:
            default_effect = Outcome(data["default_effect"])
        except (TypeError, ValueError) as exc:
            raise PolicyValidationError(
                "policy.default_effect must be allow, deny, or review"
            ) from exc
        rules_value = data["rules"]
        if not isinstance(rules_value, list):
            raise PolicyValidationError("policy.rules must be a JSON array")
        if len(rules_value) > 1_000:
            raise PolicyValidationError("policy.rules exceeds the limit of 1000")
        rules = tuple(
            PolicyRule.from_dict(item, index=index) for index, item in enumerate(rules_value)
        )
        identifiers = [rule.id for rule in rules]
        duplicates = sorted(
            {identifier for identifier in identifiers if identifiers.count(identifier) > 1}
        )
        if duplicates:
            raise PolicyValidationError(f"policy.rules has duplicate ids: {', '.join(duplicates)}")
        return cls(
            schema_version=1,
            id=policy_id,
            version=version,
            description=description,
            default_effect=default_effect,
            rules=rules,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "version": self.version,
            "description": self.description,
            "default_effect": self.default_effect.value,
            "rules": [rule.to_dict() for rule in self.rules],
        }


@dataclass(frozen=True, slots=True)
class Decision:
    """Explainable policy decision. The evaluated input is intentionally excluded."""

    decision_id: str
    evaluated_at: str
    policy_id: str
    policy_version: str
    outcome: Outcome
    allowed: bool
    matched_rules: tuple[str, ...]
    warnings: tuple[str, ...]
    reasons: tuple[str, ...]
    evaluated_rules: int

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["outcome"] = self.outcome.value
        data["matched_rules"] = list(self.matched_rules)
        data["warnings"] = list(self.warnings)
        data["reasons"] = list(self.reasons)
        return data
