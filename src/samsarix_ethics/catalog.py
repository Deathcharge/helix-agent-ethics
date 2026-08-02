# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Versioned application-owned tool capability catalogs."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .errors import InputValidationError, ToolCatalogValidationError
from .validation import validate_json_shape

TOOL_CATALOG_VERSION = 1
MAX_TOOL_CATALOG_TOOLS = 256
MAX_TOOL_CATALOG_CAPABILITIES = 64
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


def _check_keys(
    data: Mapping[str, Any], *, required: set[str], optional: set[str], location: str
) -> None:
    missing = sorted(required - data.keys())
    unknown = sorted(data.keys() - required - optional)
    if missing:
        raise ToolCatalogValidationError(f"{location} is missing: {', '.join(missing)}")
    if unknown:
        raise ToolCatalogValidationError(f"{location} has unknown fields: {', '.join(unknown)}")


def _identifier(value: Any, location: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ToolCatalogValidationError(
            f"{location} must be 1-128 characters using letters, digits, '.', '_', ':', or '-'"
        )
    return value


@dataclass(frozen=True, slots=True)
class ToolCatalogEntry:
    """One trusted local tool name and its canonical capability labels."""

    name: str
    capabilities: tuple[str, ...]

    def __post_init__(self) -> None:
        _identifier(self.name, "tool catalog entry.name")
        if not isinstance(self.capabilities, tuple):
            raise ToolCatalogValidationError(
                "tool catalog entry.capabilities must be an immutable tuple"
            )
        if not self.capabilities:
            raise ToolCatalogValidationError(
                "tool catalog entry.capabilities must contain at least one capability"
            )
        if len(self.capabilities) > MAX_TOOL_CATALOG_CAPABILITIES:
            raise ToolCatalogValidationError(
                "tool catalog entry.capabilities exceeds the limit of "
                f"{MAX_TOOL_CATALOG_CAPABILITIES} capabilities"
            )
        for index, capability in enumerate(self.capabilities):
            _identifier(capability, f"tool catalog entry.capabilities[{index}]")
        if len(set(self.capabilities)) != len(self.capabilities):
            raise ToolCatalogValidationError(
                "tool catalog entry.capabilities must not contain duplicates"
            )
        if self.capabilities != tuple(sorted(self.capabilities)):
            raise ToolCatalogValidationError(
                "tool catalog entry.capabilities must use canonical sorted order"
            )

    @classmethod
    def from_dict(cls, value: Any, *, index: int) -> ToolCatalogEntry:
        location = f"tool catalog.tools[{index}]"
        if not isinstance(value, dict):
            raise ToolCatalogValidationError(f"{location} must be a JSON object")
        _check_keys(value, required={"name", "capabilities"}, optional=set(), location=location)
        name = _identifier(value["name"], f"{location}.name")
        capabilities_value = value["capabilities"]
        if not isinstance(capabilities_value, list):
            raise ToolCatalogValidationError(f"{location}.capabilities must be a JSON array")
        if not capabilities_value:
            raise ToolCatalogValidationError(
                f"{location}.capabilities must contain at least one capability"
            )
        if len(capabilities_value) > MAX_TOOL_CATALOG_CAPABILITIES:
            raise ToolCatalogValidationError(
                f"{location}.capabilities exceeds the limit of "
                f"{MAX_TOOL_CATALOG_CAPABILITIES} capabilities"
            )
        capabilities = tuple(
            _identifier(capability, f"{location}.capabilities[{capability_index}]")
            for capability_index, capability in enumerate(capabilities_value)
        )
        if len(set(capabilities)) != len(capabilities):
            raise ToolCatalogValidationError(f"{location}.capabilities must not contain duplicates")
        return cls(name=name, capabilities=tuple(sorted(capabilities)))

    def to_dict(self) -> dict[str, Any]:
        """Return canonical detached registration metadata."""

        return {"name": self.name, "capabilities": list(self.capabilities)}


@dataclass(frozen=True, slots=True)
class ToolCatalog:
    """A bounded immutable catalog of application-owned tool capabilities."""

    tool_catalog_version: int
    id: str
    version: str
    description: str
    tools: tuple[ToolCatalogEntry, ...]

    def __post_init__(self) -> None:
        if (
            isinstance(self.tool_catalog_version, bool)
            or not isinstance(self.tool_catalog_version, int)
            or self.tool_catalog_version != TOOL_CATALOG_VERSION
        ):
            raise ToolCatalogValidationError("tool_catalog_version must be 1")
        _identifier(self.id, "tool catalog.id")
        _identifier(self.version, "tool catalog.version")
        if not isinstance(self.description, str) or len(self.description) > 1_000:
            raise ToolCatalogValidationError(
                "tool catalog.description must be a string of at most 1000 characters"
            )
        if not isinstance(self.tools, tuple):
            raise ToolCatalogValidationError("tool catalog.tools must be an immutable tuple")
        if not self.tools:
            raise ToolCatalogValidationError("tool catalog.tools must contain at least one tool")
        if len(self.tools) > MAX_TOOL_CATALOG_TOOLS:
            raise ToolCatalogValidationError(
                f"tool catalog.tools exceeds the limit of {MAX_TOOL_CATALOG_TOOLS} tools"
            )
        if any(not isinstance(tool, ToolCatalogEntry) for tool in self.tools):
            raise ToolCatalogValidationError(
                "tool catalog.tools must contain only ToolCatalogEntry objects"
            )
        names = [tool.name for tool in self.tools]
        if len(set(names)) != len(names):
            raise ToolCatalogValidationError("tool catalog.tools must not contain duplicate names")
        if self.tools != tuple(sorted(self.tools, key=lambda tool: tool.name)):
            raise ToolCatalogValidationError("tool catalog.tools must use canonical sorted order")

    @classmethod
    def from_dict(cls, value: Any) -> ToolCatalog:
        try:
            validate_json_shape(value, label="tool catalog")
        except InputValidationError as exc:
            raise ToolCatalogValidationError(str(exc)) from exc
        if not isinstance(value, dict):
            raise ToolCatalogValidationError("tool catalog must be a JSON object")
        _check_keys(
            value,
            required={"tool_catalog_version", "id", "version", "tools"},
            optional={"description"},
            location="tool catalog",
        )
        if (
            isinstance(value["tool_catalog_version"], bool)
            or not isinstance(value["tool_catalog_version"], int)
            or value["tool_catalog_version"] != TOOL_CATALOG_VERSION
        ):
            raise ToolCatalogValidationError("tool_catalog_version must be 1")
        catalog_id = _identifier(value["id"], "tool catalog.id")
        version = _identifier(value["version"], "tool catalog.version")
        description = value.get("description", "")
        if not isinstance(description, str) or len(description) > 1_000:
            raise ToolCatalogValidationError(
                "tool catalog.description must be a string of at most 1000 characters"
            )
        tools_value = value["tools"]
        if not isinstance(tools_value, list):
            raise ToolCatalogValidationError("tool catalog.tools must be a JSON array")
        if not tools_value:
            raise ToolCatalogValidationError("tool catalog.tools must contain at least one tool")
        if len(tools_value) > MAX_TOOL_CATALOG_TOOLS:
            raise ToolCatalogValidationError(
                f"tool catalog.tools exceeds the limit of {MAX_TOOL_CATALOG_TOOLS} tools"
            )
        tools = tuple(
            ToolCatalogEntry.from_dict(item, index=index) for index, item in enumerate(tools_value)
        )
        names = [tool.name for tool in tools]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ToolCatalogValidationError(
                f"tool catalog.tools has duplicate names: {', '.join(duplicates)}"
            )
        return cls(
            tool_catalog_version=TOOL_CATALOG_VERSION,
            id=catalog_id,
            version=version,
            description=description,
            tools=tuple(sorted(tools, key=lambda tool: tool.name)),
        )

    @property
    def tool_names(self) -> tuple[str, ...]:
        """Return canonical registered tool names."""

        return tuple(tool.name for tool in self.tools)

    def get(self, name: str) -> ToolCatalogEntry:
        """Return trusted metadata for one known tool name."""

        for tool in self.tools:
            if tool.name == name:
                return tool
        raise KeyError(name)

    def to_dict(self) -> dict[str, Any]:
        """Return the canonical detached catalog document."""

        return {
            "tool_catalog_version": self.tool_catalog_version,
            "id": self.id,
            "version": self.version,
            "description": self.description,
            "tools": [tool.to_dict() for tool in self.tools],
        }


def _name_summary(names: set[str]) -> str:
    ordered = sorted(names)
    visible = ", ".join(ordered[:5])
    suffix = "" if len(ordered) <= 5 else f", ... ({len(ordered)} total)"
    return visible + suffix


def validate_tool_catalog_registration(
    catalog: ToolCatalog,
    registered_tools: Iterable[str],
) -> tuple[str, ...]:
    """Require a catalog to exactly match a trusted registry name snapshot."""

    if not isinstance(catalog, ToolCatalog):
        raise TypeError("catalog must be a ToolCatalog")
    if isinstance(registered_tools, (str, bytes, bytearray)):
        raise ToolCatalogValidationError("registered tools must be an iterable of tool names")
    try:
        iterator = iter(registered_tools)
    except TypeError as exc:
        raise ToolCatalogValidationError("registered tools must be iterable") from exc

    normalized: list[str] = []
    for index, name in enumerate(iterator):
        if index >= MAX_TOOL_CATALOG_TOOLS:
            raise ToolCatalogValidationError(
                f"registered tools exceed the limit of {MAX_TOOL_CATALOG_TOOLS} tools"
            )
        normalized.append(_identifier(name, f"registered tools[{index}]"))
    if len(set(normalized)) != len(normalized):
        raise ToolCatalogValidationError("registered tools must not contain duplicate names")

    catalog_names = set(catalog.tool_names)
    registered_names = set(normalized)
    missing = catalog_names - registered_names
    uncataloged = registered_names - catalog_names
    details: list[str] = []
    if missing:
        details.append(f"cataloged tools missing from registry: {_name_summary(missing)}")
    if uncataloged:
        details.append(f"registered tools missing from catalog: {_name_summary(uncataloged)}")
    if details:
        raise ToolCatalogValidationError("; ".join(details))
    return tuple(sorted(normalized))
