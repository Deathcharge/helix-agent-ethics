"""Trusted tool catalog validation, provenance, and gate binding."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from itertools import repeat
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from samsarix_ethics import (
    MAX_TOOL_CATALOG_BYTES,
    MAX_TOOL_CATALOG_CAPABILITIES,
    MAX_TOOL_CATALOG_TOOLS,
    BoundToolCatalog,
    Outcome,
    ToolCallDeniedError,
    ToolCatalog,
    ToolCatalogEntry,
    ToolCatalogValidationError,
    ToolGate,
    fingerprint_tool_catalog,
    get_tool_catalog_schema,
    load_policy,
    load_tool_catalog,
    validate_tool_catalog_registration,
)

_ROOT = Path(__file__).parents[1]
_POLICY_PATH = _ROOT / "examples/policies/tool-call-baseline.json"


def _catalog_document() -> dict[str, Any]:
    return {
        "tool_catalog_version": 1,
        "id": "support-tools",
        "version": "1.0.0",
        "description": "Trusted support tool capabilities.",
        "tools": [
            {
                "name": "read_ticket",
                "capabilities": ["data:sensitive", "resource:read"],
            },
            {
                "name": "delete_ticket",
                "capabilities": ["destructive", "resource:write"],
            },
        ],
    }


def test_catalog_is_canonical_immutable_and_detached() -> None:
    source = _catalog_document()
    source["tools"].reverse()
    source["tools"][1]["capabilities"].reverse()

    catalog = ToolCatalog.from_dict(source)
    source["tools"][0]["name"] = "changed"

    assert catalog.tool_names == ("delete_ticket", "read_ticket")
    assert catalog.get("read_ticket").capabilities == ("data:sensitive", "resource:read")
    assert catalog.to_dict()["tools"][0]["name"] == "delete_ticket"
    assert catalog.to_dict()["tools"][1]["name"] == "read_ticket"
    with pytest.raises(KeyError):
        catalog.get("missing")
    with pytest.raises(FrozenInstanceError):
        catalog.version = "2"  # type: ignore[misc]


def test_direct_catalog_constructors_preserve_validated_immutable_invariants() -> None:
    entry = ToolCatalogEntry("read_ticket", ("resource:read",))
    catalog = ToolCatalog(1, "support-tools", "1", "", (entry,))

    assert catalog.get("read_ticket") is entry
    with pytest.raises(ToolCatalogValidationError, match="immutable tuple"):
        ToolCatalogEntry("read_ticket", ["resource:read"])  # type: ignore[arg-type]
    with pytest.raises(ToolCatalogValidationError, match="canonical sorted order"):
        ToolCatalogEntry("read_ticket", ("resource:read", "data:sensitive"))
    with pytest.raises(ToolCatalogValidationError, match="immutable tuple"):
        ToolCatalog(1, "support-tools", "1", "", [entry])  # type: ignore[arg-type]
    with pytest.raises(ToolCatalogValidationError, match="version must be 1"):
        ToolCatalog(True, "support-tools", "1", "", (entry,))


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda value: value.update(tool_catalog_version=True), "version must be 1"),
        (lambda value: value.update(id="bad id"), "tool catalog.id"),
        (lambda value: value.update(description=1), "description"),
        (lambda value: value.update(tools={}), "tools must be a JSON array"),
        (lambda value: value.update(tools=[]), "at least one tool"),
        (lambda value: value.update(extra=True), "unknown fields"),
        (lambda value: value["tools"][0].update(extra=True), "unknown fields"),
        (lambda value: value["tools"][0].update(name="bad name"), r"tools\[0\]\.name"),
        (lambda value: value["tools"][0].update(capabilities=[]), "at least one capability"),
        (
            lambda value: value["tools"][0].update(capabilities=["resource:read"] * 2),
            "must not contain duplicates",
        ),
    ],
)
def test_catalog_rejects_invalid_documents(mutate: Any, message: str) -> None:
    value = _catalog_document()
    mutate(value)

    with pytest.raises(ToolCatalogValidationError, match=message):
        ToolCatalog.from_dict(value)


def test_catalog_rejects_duplicate_names_and_resource_limits() -> None:
    duplicate = _catalog_document()
    duplicate["tools"][1]["name"] = duplicate["tools"][0]["name"]
    with pytest.raises(ToolCatalogValidationError, match="duplicate names"):
        ToolCatalog.from_dict(duplicate)

    too_many_tools = _catalog_document()
    too_many_tools["tools"] = [
        {"name": f"tool-{index}", "capabilities": ["risk:known"]}
        for index in range(MAX_TOOL_CATALOG_TOOLS + 1)
    ]
    with pytest.raises(ToolCatalogValidationError, match="limit of 256 tools"):
        ToolCatalog.from_dict(too_many_tools)

    too_many_capabilities = _catalog_document()
    too_many_capabilities["tools"][0]["capabilities"] = [
        f"capability:{index}" for index in range(MAX_TOOL_CATALOG_CAPABILITIES + 1)
    ]
    with pytest.raises(ToolCatalogValidationError, match="limit of 64 capabilities"):
        ToolCatalog.from_dict(too_many_capabilities)


def test_catalog_fingerprint_uses_canonical_registration_semantics() -> None:
    first_value = _catalog_document()
    second_value = _catalog_document()
    second_value["tools"].reverse()
    second_value["tools"][0]["capabilities"].reverse()
    first = ToolCatalog.from_dict(first_value)
    second = ToolCatalog.from_dict(second_value)

    assert first == second
    assert fingerprint_tool_catalog(first) == fingerprint_tool_catalog(second)
    assert fingerprint_tool_catalog(first) == (
        "v1:sha256:10404700cb688aea9900aa5b979356a6cd9aa9e3f8eec270d77dced7db872176"
    )
    changed = first.to_dict()
    changed["tools"][0]["capabilities"].append("risk:elevated")
    assert fingerprint_tool_catalog(ToolCatalog.from_dict(changed)) != fingerprint_tool_catalog(
        first
    )
    with pytest.raises(TypeError, match="ToolCatalog"):
        fingerprint_tool_catalog(object())  # type: ignore[arg-type]


def test_registration_snapshot_requires_exact_bounded_names() -> None:
    catalog = ToolCatalog.from_dict(_catalog_document())

    assert validate_tool_catalog_registration(catalog, ["read_ticket", "delete_ticket"]) == (
        "delete_ticket",
        "read_ticket",
    )
    with pytest.raises(ToolCatalogValidationError, match="missing from registry: read_ticket"):
        validate_tool_catalog_registration(catalog, ["delete_ticket"])
    with pytest.raises(ToolCatalogValidationError, match="missing from catalog: send_ticket"):
        validate_tool_catalog_registration(catalog, ["delete_ticket", "read_ticket", "send_ticket"])
    with pytest.raises(ToolCatalogValidationError, match="iterable of tool names"):
        validate_tool_catalog_registration(catalog, "read_ticket")
    with pytest.raises(ToolCatalogValidationError, match="must be iterable"):
        validate_tool_catalog_registration(catalog, None)  # type: ignore[arg-type]
    with pytest.raises(ToolCatalogValidationError, match="duplicate names"):
        validate_tool_catalog_registration(catalog, ["read_ticket", "read_ticket"])
    with pytest.raises(ToolCatalogValidationError, match=r"registered tools\[0\]"):
        validate_tool_catalog_registration(catalog, ["bad name"])
    with pytest.raises(ToolCatalogValidationError, match="limit of 256 tools"):
        validate_tool_catalog_registration(catalog, repeat("read_ticket", 257))
    with pytest.raises(TypeError, match="ToolCatalog"):
        validate_tool_catalog_registration(object(), [])  # type: ignore[arg-type]


def test_gate_binds_exact_catalog_to_immutable_safe_mapping() -> None:
    catalog = ToolCatalog.from_dict(
        {
            "tool_catalog_version": 1,
            "id": "gate-tools",
            "version": "1",
            "tools": [
                {"name": "read_file", "capabilities": ["resource:read"]},
                {"name": "delete_file", "capabilities": ["destructive"]},
            ],
        }
    )
    gate = ToolGate(load_policy(_POLICY_PATH))

    bindings = gate.bind_catalog(
        catalog,
        registered_tools={"delete_file", "read_file"},
    )

    assert isinstance(bindings, BoundToolCatalog)
    assert bindings.gate is gate
    assert bindings.catalog is catalog
    assert bindings.catalog_fingerprint == fingerprint_tool_catalog(catalog)
    assert bindings.tool_names == ("delete_file", "read_file")
    assert tuple(bindings) == bindings.tool_names
    assert bindings["read_file"].capabilities == ("resource:read",)
    assert bindings["read_file"].enforce({"path": "README.md"}).outcome is Outcome.ALLOW
    with pytest.raises(ToolCallDeniedError):
        bindings["delete_file"].enforce({"path": "old.log"})
    with pytest.raises(KeyError):
        bindings["unknown"]
    with pytest.raises(TypeError):
        bindings._bindings["read_file"] = bindings["delete_file"]  # type: ignore[index]
    assert repr(bindings) == (
        "BoundToolCatalog(catalog_id='gate-tools', catalog_version='1', tool_count=2)"
    )
    assert "destructive" not in repr(bindings)
    with pytest.raises(TypeError, match=r"created by ToolGate\.bind_catalog"):
        BoundToolCatalog()


def test_catalog_file_loading_is_bounded_and_duplicate_safe(tmp_path: Path) -> None:
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(_catalog_document()), encoding="utf-8")
    assert load_tool_catalog(path) == ToolCatalog.from_dict(_catalog_document())

    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"tool_catalog_version":1,"tool_catalog_version":1}', encoding="utf-8")
    with pytest.raises(ToolCatalogValidationError, match="duplicate object key"):
        load_tool_catalog(duplicate)

    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b"{" + b" " * MAX_TOOL_CATALOG_BYTES + b"}")
    with pytest.raises(ToolCatalogValidationError, match="byte limit"):
        load_tool_catalog(oversized)


def test_catalog_schema_is_valid_and_accepts_the_example() -> None:
    schema = get_tool_catalog_schema()
    Draft202012Validator.check_schema(schema)
    example = json.loads(
        (_ROOT / "examples/catalogs/coding-agent-tools.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(example)
    assert ToolCatalog.from_dict(example).id == "coding-agent-tools"
