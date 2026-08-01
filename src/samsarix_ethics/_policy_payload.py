# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Shared bounded serialization for deployable policy documents."""

from __future__ import annotations

import json
from typing import Any

from .errors import InputValidationError, PolicyValidationError, SamsarixEthicsError
from .validation import validate_json_shape

MAX_POLICY_BYTES = 1_048_576


def serialize_policy_document(
    value: dict[str, Any],
    *,
    label: str,
    max_bytes: int = MAX_POLICY_BYTES,
    error_type: type[SamsarixEthicsError] = PolicyValidationError,
) -> bytes:
    """Serialize a structurally valid JSON document within a byte limit."""

    try:
        validate_json_shape(value, label=label)
    except InputValidationError as exc:
        raise error_type(str(exc)) from exc
    encoder = json.JSONEncoder(allow_nan=False, ensure_ascii=True, indent=2, sort_keys=False)
    payload = bytearray()
    try:
        for part in encoder.iterencode(value):
            chunk = part.encode("ascii")
            if len(payload) + len(chunk) + 1 > max_bytes:
                raise error_type(f"{label} exceeds the byte limit of {max_bytes} when serialized")
            payload.extend(chunk)
    except (TypeError, ValueError, UnicodeError) as exc:
        raise error_type(f"{label} cannot be serialized: {type(exc).__name__}") from exc
    payload.extend(b"\n")
    return bytes(payload)
