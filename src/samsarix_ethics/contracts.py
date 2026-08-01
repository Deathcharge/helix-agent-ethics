# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Versioned application context contracts and policy compatibility checks."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from .errors import ContextContractValidationError, InputValidationError
from .models import Policy, PolicyCondition
from .validation import validate_context, validate_json_shape

CONTEXT_CONTRACT_VERSION = 1
MAX_CONTEXT_CONTRACT_FIELDS = 1_000
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_FIELD_PATH = re.compile(r"^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*$")
_MISSING = object()


class ContextFieldType(StrEnum):
    """JSON-native types supported by a context contract."""

    ARRAY = "array"
    BOOLEAN = "boolean"
    INTEGER = "integer"
    NULL = "null"
    NUMBER = "number"
    OBJECT = "object"
    STRING = "string"


def _check_keys(
    data: Mapping[str, Any], *, required: set[str], optional: set[str], location: str
) -> None:
    missing = sorted(required - data.keys())
    unknown = sorted(data.keys() - required - optional)
    if missing:
        raise ContextContractValidationError(f"{location} is missing: {', '.join(missing)}")
    if unknown:
        raise ContextContractValidationError(
            f"{location} has unknown fields: {', '.join(unknown)}"
        )


def _identifier(value: Any, location: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ContextContractValidationError(
            f"{location} must be 1-128 characters using letters, digits, '.', '_', ':', or '-'"
        )
    return value


def _field_type(value: Any, location: str) -> ContextFieldType:
    try:
        return ContextFieldType(value)
    except (TypeError, ValueError) as exc:
        supported = ", ".join(item.value for item in ContextFieldType)
        raise ContextContractValidationError(
            f"{location} must be one of: {supported}"
        ) from exc


@dataclass(frozen=True, slots=True)
class ContextField:
    """One declared fact in an evaluation context."""

    type: ContextFieldType
    required: bool = True
    items: ContextFieldType | None = None

    @classmethod
    def from_dict(cls, value: Any, *, location: str) -> ContextField:
        if not isinstance(value, dict):
            raise ContextContractValidationError(f"{location} must be a JSON object")
        _check_keys(value, required={"type"}, optional={"required", "items"}, location=location)
        field_type = _field_type(value["type"], f"{location}.type")
        required = value.get("required", True)
        if not isinstance(required, bool):
            raise ContextContractValidationError(f"{location}.required must be a boolean")
        items_value = value.get("items")
        if field_type is ContextFieldType.ARRAY:
            items = None if items_value is None else _field_type(items_value, f"{location}.items")
        else:
            if "items" in value:
                raise ContextContractValidationError(
                    f"{location}.items is allowed only when type is 'array'"
                )
            items = None
        return cls(type=field_type, required=required, items=items)

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {"type": self.type.value, "required": self.required}
        if self.items is not None:
            value["items"] = self.items.value
        return value


@dataclass(frozen=True, slots=True)
class ContextContract:
    """A bounded, immutable declaration of facts policies may reference."""

    context_contract_version: int
    id: str
    version: str
    description: str
    fields: Mapping[str, ContextField]

    @classmethod
    def from_dict(cls, value: Any) -> ContextContract:
        try:
            validate_json_shape(value, label="context contract")
        except InputValidationError as exc:
            raise ContextContractValidationError(str(exc)) from exc
        if not isinstance(value, dict):
            raise ContextContractValidationError("context contract must be a JSON object")
        _check_keys(
            value,
            required={"context_contract_version", "id", "version", "fields"},
            optional={"description"},
            location="context contract",
        )
        if (
            isinstance(value["context_contract_version"], bool)
            or value["context_contract_version"] != CONTEXT_CONTRACT_VERSION
        ):
            raise ContextContractValidationError("context_contract_version must be 1")
        contract_id = _identifier(value["id"], "context contract.id")
        version = _identifier(value["version"], "context contract.version")
        description = value.get("description", "")
        if not isinstance(description, str) or len(description) > 1_000:
            raise ContextContractValidationError(
                "context contract.description must be a string of at most 1000 characters"
            )
        fields_value = value["fields"]
        if not isinstance(fields_value, dict):
            raise ContextContractValidationError("context contract.fields must be a JSON object")
        if len(fields_value) > MAX_CONTEXT_CONTRACT_FIELDS:
            raise ContextContractValidationError(
                "context contract.fields exceeds the limit of "
                f"{MAX_CONTEXT_CONTRACT_FIELDS} fields"
            )
        fields: dict[str, ContextField] = {}
        for path, field_value in fields_value.items():
            if not isinstance(path, str) or len(path) > 256 or not _FIELD_PATH.fullmatch(path):
                raise ContextContractValidationError(
                    "context contract.fields contains an invalid dotted field path"
                )
            fields[path] = ContextField.from_dict(
                field_value, location=f"context contract.fields[{path!r}]"
            )
        for path in fields:
            parts = path.split(".")
            for index in range(1, len(parts)):
                parent_path = ".".join(parts[:index])
                parent = fields.get(parent_path)
                if parent is None:
                    raise ContextContractValidationError(
                        f"context contract field {path!r} requires parent field {parent_path!r}"
                    )
                if parent.type is not ContextFieldType.OBJECT:
                    raise ContextContractValidationError(
                        f"context contract field {path!r} has non-object parent {parent_path!r}"
                    )
                if fields[path].required and not parent.required:
                    raise ContextContractValidationError(
                        f"required context contract field {path!r} has optional parent "
                        f"{parent_path!r}"
                    )
        return cls(
            context_contract_version=CONTEXT_CONTRACT_VERSION,
            id=contract_id,
            version=version,
            description=description,
            fields=MappingProxyType(fields),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "context_contract_version": self.context_contract_version,
            "id": self.id,
            "version": self.version,
            "description": self.description,
            "fields": {path: field.to_dict() for path, field in self.fields.items()},
        }


def _field_value(context: Mapping[str, Any], path: str) -> Any:
    value: Any = context
    for part in path.split("."):
        if not isinstance(value, Mapping) or part not in value:
            return _MISSING
        value = value[part]
    return value


def _matches_type(value: Any, field_type: ContextFieldType) -> bool:
    if field_type is ContextFieldType.NULL:
        return value is None
    if field_type is ContextFieldType.BOOLEAN:
        return isinstance(value, bool)
    if field_type is ContextFieldType.INTEGER:
        return isinstance(value, int) and not isinstance(value, bool)
    if field_type is ContextFieldType.NUMBER:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if field_type is ContextFieldType.STRING:
        return isinstance(value, str)
    if field_type is ContextFieldType.ARRAY:
        return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))
    return isinstance(value, Mapping)


def validate_context_against_contract(
    context: Mapping[str, Any], contract: ContextContract
) -> Mapping[str, Any]:
    """Validate declared facts and return the validated JSON context."""

    if not isinstance(contract, ContextContract):
        raise TypeError("contract must be a ContextContract")
    validated = validate_context(context)
    for path, field in contract.fields.items():
        actual = _field_value(validated, path)
        if actual is _MISSING:
            if field.required:
                raise InputValidationError(
                    f"evaluation input is missing required contract field {path!r}"
                )
            continue
        if not _matches_type(actual, field.type):
            raise InputValidationError(
                f"evaluation input field {path!r} must have type {field.type.value!r}"
            )
        if field.items is not None:
            for index, item in enumerate(actual):
                if not _matches_type(item, field.items):
                    raise InputValidationError(
                        f"evaluation input field {path!r}[{index}] must have type "
                        f"{field.items.value!r}"
                    )
    return validated


def _value_type(value: Any) -> ContextFieldType:
    if value is None:
        return ContextFieldType.NULL
    if isinstance(value, bool):
        return ContextFieldType.BOOLEAN
    if isinstance(value, int):
        return ContextFieldType.INTEGER
    if isinstance(value, float):
        return ContextFieldType.NUMBER
    if isinstance(value, str):
        return ContextFieldType.STRING
    if isinstance(value, Mapping):
        return ContextFieldType.OBJECT
    return ContextFieldType.ARRAY


def _types_compatible(left: ContextFieldType, right: ContextFieldType) -> bool:
    return left is right or {left, right} <= {
        ContextFieldType.INTEGER,
        ContextFieldType.NUMBER,
    }


def _condition_error(location: str, message: str) -> ContextContractValidationError:
    return ContextContractValidationError(
        f"{location} is incompatible with context contract: {message}"
    )


def _declared_field(
    contract: ContextContract, path: str, *, location: str
) -> ContextField:
    field = contract.fields.get(path)
    if field is None:
        raise _condition_error(location, f"field {path!r} is not declared")
    return field


def _literal_array_item_types(value: Any, *, location: str) -> tuple[ContextFieldType, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise _condition_error(location, "policy value must be an array")
    return tuple(_value_type(item) for item in value)


def _expected_field(
    condition: PolicyCondition, contract: ContextContract, *, location: str
) -> ContextField | None:
    expected = condition.value
    if isinstance(expected, Mapping) and set(expected) == {"$ref"}:
        return _declared_field(contract, expected["$ref"], location=f"{location}.value.$ref")
    return None


def _validate_condition(
    condition: PolicyCondition, contract: ContextContract, *, location: str
) -> None:
    actual = _declared_field(contract, condition.field, location=f"{location}.field")
    operator = condition.operator
    if operator in {"exists", "not_exists"}:
        return
    referenced = _expected_field(condition, contract, location=location)
    expected = condition.value

    if operator in {"starts_with", "ends_with"}:
        if actual.type is not ContextFieldType.STRING:
            raise _condition_error(location, f"operator {operator!r} requires a string field")
        expected_type = referenced.type if referenced else _value_type(expected)
        if expected_type is not ContextFieldType.STRING:
            raise _condition_error(location, f"operator {operator!r} requires a string value")
        return

    if operator in {"gt", "gte", "lt", "lte"}:
        comparable = {
            ContextFieldType.INTEGER,
            ContextFieldType.NUMBER,
            ContextFieldType.STRING,
        }
        expected_type = referenced.type if referenced else _value_type(expected)
        if actual.type not in comparable or not _types_compatible(actual.type, expected_type):
            raise _condition_error(
                location, f"operator {operator!r} requires two numbers or two strings"
            )
        return

    if operator in {"contains", "not_contains", "subset_of"}:
        if actual.type is not ContextFieldType.ARRAY:
            raise _condition_error(location, f"operator {operator!r} requires an array field")
        expected_items: tuple[ContextFieldType, ...]
        if operator == "subset_of":
            if referenced:
                if referenced.type is not ContextFieldType.ARRAY:
                    raise _condition_error(location, "operator 'subset_of' requires an array value")
                expected_items = () if referenced.items is None else (referenced.items,)
            else:
                expected_items = _literal_array_item_types(expected, location=location)
        else:
            expected_items = (
                (referenced.type,) if referenced is not None else (_value_type(expected),)
            )
        if actual.items is not None and any(
            not _types_compatible(actual.items, item_type) for item_type in expected_items
        ):
            raise _condition_error(location, "policy value type does not match array item type")
        return

    if operator in {"in", "not_in"}:
        membership_items: tuple[ContextFieldType, ...]
        if referenced:
            if referenced.type is not ContextFieldType.ARRAY:
                raise _condition_error(location, f"operator {operator!r} requires an array value")
            membership_items = () if referenced.items is None else (referenced.items,)
        else:
            membership_items = _literal_array_item_types(expected, location=location)
        if any(not _types_compatible(actual.type, item_type) for item_type in membership_items):
            raise _condition_error(location, "field type does not match policy array item type")
        return

    expected_type = referenced.type if referenced else _value_type(expected)
    if not _types_compatible(actual.type, expected_type):
        raise _condition_error(location, "field and policy value types do not match")
    if actual.type is ContextFieldType.ARRAY and actual.items is not None:
        equality_items: tuple[ContextFieldType, ...]
        if referenced is not None:
            equality_items = () if referenced.items is None else (referenced.items,)
        else:
            equality_items = _literal_array_item_types(expected, location=location)
        if any(
            not _types_compatible(actual.items, item_type) for item_type in equality_items
        ):
            raise _condition_error(location, "policy value type does not match array item type")


def validate_policy_context_contract(policy: Policy, contract: ContextContract) -> None:
    """Reject policy field references and operator uses incompatible with a contract."""

    if not isinstance(policy, Policy):
        raise TypeError("policy must be a Policy")
    if not isinstance(contract, ContextContract):
        raise TypeError("contract must be a ContextContract")
    for rule_index, rule in enumerate(policy.rules):
        for condition_index, condition in enumerate(rule.conditions):
            _validate_condition(
                condition,
                contract,
                location=f"rules[{rule_index}].conditions[{condition_index}]",
            )
