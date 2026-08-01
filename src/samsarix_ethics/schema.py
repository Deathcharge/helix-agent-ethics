# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Access to versioned JSON Schemas bundled with the distribution."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any


def _load_schema(filename: str) -> dict[str, Any]:
    resource = files("samsarix_ethics").joinpath("schemas", filename)
    value = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"bundled schema {filename!r} is not a JSON object")
    return value


def get_policy_schema() -> dict[str, Any]:
    """Return a fresh copy of the policy format version 1 JSON Schema."""

    return _load_schema("policy-v1.schema.json")


def get_policy_test_schema() -> dict[str, Any]:
    """Return a fresh copy of the policy-test suite version 1 JSON Schema."""

    return _load_schema("policy-test-v1.schema.json")
