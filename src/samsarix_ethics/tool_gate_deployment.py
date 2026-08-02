# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Coherent policy-and-catalog deployment units for tool gates."""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from typing import Any

from .catalog import ToolCatalog
from .errors import (
    InputValidationError,
    PolicyDeploymentValidationError,
    ToolCatalogValidationError,
    ToolGateDeploymentValidationError,
)
from .policy_deployment import PolicyDeployment
from .provenance import fingerprint_tool_catalog
from .validation import validate_json_shape

TOOL_GATE_DEPLOYMENT_VERSION = 1


@dataclass(frozen=True, slots=True, repr=False)
class ToolGateDeployment:
    """One internally verified policy deployment and trusted tool catalog."""

    tool_gate_deployment_version: int
    policy_deployment: PolicyDeployment
    tool_catalog: ToolCatalog
    tool_catalog_fingerprint: str

    def __repr__(self) -> str:
        """Return artifact identity without policy rules or catalog capabilities."""

        return (
            "ToolGateDeployment("
            f"policy_id={self.policy_deployment.policy.id!r}, "
            f"policy_version={self.policy_deployment.policy.version!r}, "
            f"catalog_id={self.tool_catalog.id!r}, "
            f"catalog_version={self.tool_catalog.version!r}, "
            f"tool_count={len(self.tool_catalog.tools)})"
        )

    def __post_init__(self) -> None:
        if (
            isinstance(self.tool_gate_deployment_version, bool)
            or not isinstance(self.tool_gate_deployment_version, int)
            or self.tool_gate_deployment_version != TOOL_GATE_DEPLOYMENT_VERSION
        ):
            raise ToolGateDeploymentValidationError("tool_gate_deployment_version must be 1")
        if not isinstance(self.policy_deployment, PolicyDeployment):
            raise ToolGateDeploymentValidationError(
                "tool gate deployment policy_deployment must be a PolicyDeployment"
            )
        if not isinstance(self.tool_catalog, ToolCatalog):
            raise ToolGateDeploymentValidationError(
                "tool gate deployment tool_catalog must be a ToolCatalog"
            )
        expected = fingerprint_tool_catalog(self.tool_catalog)
        if not isinstance(self.tool_catalog_fingerprint, str) or not hmac.compare_digest(
            self.tool_catalog_fingerprint, expected
        ):
            raise ToolGateDeploymentValidationError(
                "tool gate deployment catalog fingerprint does not match the catalog"
            )

    @classmethod
    def from_dict(cls, value: Any) -> ToolGateDeployment:
        """Strictly parse and internally verify a coherent tool-gate deployment."""

        try:
            validate_json_shape(value, label="tool gate deployment")
        except InputValidationError as exc:
            raise ToolGateDeploymentValidationError(str(exc)) from exc
        if not isinstance(value, dict):
            raise ToolGateDeploymentValidationError("tool gate deployment must be a JSON object")
        required = {
            "tool_gate_deployment_version",
            "policy_deployment",
            "tool_catalog",
            "tool_catalog_fingerprint",
        }
        missing = sorted(required - value.keys())
        unknown = sorted(value.keys() - required)
        if missing:
            raise ToolGateDeploymentValidationError(
                f"tool gate deployment is missing: {', '.join(missing)}"
            )
        if unknown:
            raise ToolGateDeploymentValidationError(
                f"tool gate deployment has unknown fields: {', '.join(unknown)}"
            )
        try:
            policy_deployment = PolicyDeployment.from_dict(value["policy_deployment"])
        except PolicyDeploymentValidationError as exc:
            raise ToolGateDeploymentValidationError(
                f"tool gate deployment contains an invalid policy deployment: {exc}"
            ) from exc
        try:
            tool_catalog = ToolCatalog.from_dict(value["tool_catalog"])
        except ToolCatalogValidationError as exc:
            raise ToolGateDeploymentValidationError(
                f"tool gate deployment contains an invalid tool catalog: {exc}"
            ) from exc
        return cls(
            tool_gate_deployment_version=value["tool_gate_deployment_version"],
            policy_deployment=policy_deployment,
            tool_catalog=tool_catalog,
            tool_catalog_fingerprint=value["tool_catalog_fingerprint"],
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a fresh canonical JSON-compatible deployment document."""

        return {
            "tool_gate_deployment_version": self.tool_gate_deployment_version,
            "policy_deployment": self.policy_deployment.to_dict(),
            "tool_catalog": self.tool_catalog.to_dict(),
            "tool_catalog_fingerprint": self.tool_catalog_fingerprint,
        }


def create_tool_gate_deployment(
    policy_deployment: PolicyDeployment,
    tool_catalog: ToolCatalog,
) -> ToolGateDeployment:
    """Create a coherent deployment from already validated artifacts."""

    if not isinstance(policy_deployment, PolicyDeployment):
        raise TypeError("policy_deployment must be a PolicyDeployment")
    if not isinstance(tool_catalog, ToolCatalog):
        raise TypeError("tool_catalog must be a ToolCatalog")
    return ToolGateDeployment(
        tool_gate_deployment_version=TOOL_GATE_DEPLOYMENT_VERSION,
        policy_deployment=policy_deployment,
        tool_catalog=tool_catalog,
        tool_catalog_fingerprint=fingerprint_tool_catalog(tool_catalog),
    )
