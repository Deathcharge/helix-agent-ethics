# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Shared validation for bounded, in-memory JSON values."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from .errors import InputValidationError

MAX_JSON_DEPTH = 32
MAX_CONTAINER_ITEMS = 10_000
MAX_STRING_LENGTH = 65_536


def validate_json_shape(root: Any, *, label: str) -> None:
    """Reject non-JSON values and JSON structures outside package limits."""

    stack: list[tuple[Any, int]] = [(root, 1)]
    seen_items = 0
    while stack:
        value, depth = stack.pop()
        if depth > MAX_JSON_DEPTH:
            raise InputValidationError(
                f"{label} exceeds the maximum JSON depth of {MAX_JSON_DEPTH}"
            )
        if isinstance(value, Mapping):
            if not all(isinstance(key, str) for key in value):
                raise InputValidationError(f"{label} contains a non-string object key")
            seen_items += len(value)
            stack.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list):
            seen_items += len(value)
            stack.extend((item, depth + 1) for item in value)
        elif isinstance(value, str):
            if len(value) > MAX_STRING_LENGTH:
                raise InputValidationError(
                    f"{label} contains a string longer than {MAX_STRING_LENGTH} characters"
                )
        elif isinstance(value, float):
            if not math.isfinite(value):
                raise InputValidationError(f"{label} contains a non-finite number")
        elif value is not None and not isinstance(value, (bool, int)):
            raise InputValidationError(
                f"{label} contains non-JSON value of type {type(value).__name__}"
            )
        if seen_items > MAX_CONTAINER_ITEMS:
            raise InputValidationError(
                f"{label} exceeds the maximum of {MAX_CONTAINER_ITEMS} container items"
            )


def validate_context(value: Any, *, label: str = "evaluation input") -> Mapping[str, Any]:
    """Validate an in-memory evaluation object against the bounded JSON contract."""

    if not isinstance(value, Mapping):
        raise InputValidationError(f"{label} must be a JSON object")
    validate_json_shape(value, label=label)
    return value
