"""Shared test helpers."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def policy_document() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "id": "test-policy",
        "version": "1.0.0",
        "description": "Test policy",
        "default_effect": "review",
        "rules": [
            {
                "id": "deny-delete",
                "effect": "deny",
                "priority": 1,
                "message": "Delete is denied.",
                "conditions": [{"field": "action.operation", "operator": "eq", "value": "delete"}],
            },
            {
                "id": "allow-read",
                "effect": "allow",
                "priority": 10,
                "message": "Read is allowed.",
                "conditions": [{"field": "action.operation", "operator": "eq", "value": "read"}],
            },
        ],
    }


@pytest.fixture
def write_json(tmp_path: Path) -> Callable[[str, Any], Path]:
    def writer(name: str, value: Any) -> Path:
        path = tmp_path / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    return writer
