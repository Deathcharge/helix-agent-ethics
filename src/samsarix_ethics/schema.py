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


def get_audit_record_schema() -> dict[str, Any]:
    """Return a fresh copy of the audit-record version 1 JSON Schema."""

    return _load_schema("audit-record-v1.schema.json")


def get_policy_test_schema() -> dict[str, Any]:
    """Return a fresh copy of the policy-test suite version 1 JSON Schema."""

    return _load_schema("policy-test-v1.schema.json")


def get_policy_comparison_schema() -> dict[str, Any]:
    """Return a fresh copy of the policy-comparison version 1 JSON Schema."""

    return _load_schema("policy-comparison-v1.schema.json")


def get_policy_coverage_schema() -> dict[str, Any]:
    """Return a fresh copy of the policy-coverage version 1 JSON Schema."""

    return _load_schema("policy-coverage-v1.schema.json")


def get_policy_lint_schema() -> dict[str, Any]:
    """Return a fresh copy of the policy-lint version 1 JSON Schema."""

    return _load_schema("policy-lint-v1.schema.json")


def get_policy_composition_schema() -> dict[str, Any]:
    """Return a fresh copy of the policy-composition version 1 JSON Schema."""

    return _load_schema("policy-composition-v1.schema.json")


def get_tool_context_schema() -> dict[str, Any]:
    """Return a fresh copy of the tool-call context version 1 JSON Schema."""

    return _load_schema("tool-context-v1.schema.json")


def get_tool_approval_schema() -> dict[str, Any]:
    """Return a fresh copy of the tool-approval version 1 JSON Schema."""

    return _load_schema("tool-approval-v1.schema.json")
