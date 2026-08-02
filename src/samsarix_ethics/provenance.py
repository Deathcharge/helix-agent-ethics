# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Deterministic provenance identifiers for validated policy artifacts."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from .catalog import ToolCatalog
from .contracts import ContextContract
from .errors import (
    ContextContractValidationError,
    PolicyValidationError,
    ToolCatalogValidationError,
    ToolGateDeploymentValidationError,
)
from .models import Policy

POLICY_FINGERPRINT_VERSION = 1
CONTEXT_CONTRACT_FINGERPRINT_VERSION = 1
TOOL_CATALOG_FINGERPRINT_VERSION = 1
TOOL_GATE_DEPLOYMENT_FINGERPRINT_VERSION = 1

_POLICY_FINGERPRINT = re.compile(r"^v1:sha256:[0-9a-f]{64}$")
_CONTEXT_CONTRACT_FINGERPRINT = re.compile(r"^v1:sha256:[0-9a-f]{64}$")
_TOOL_GATE_DEPLOYMENT_FINGERPRINT = re.compile(r"^v1:sha256:[0-9a-f]{64}$")


def _fingerprint_json(payload: Mapping[str, Any]) -> str:
    encoder = json.JSONEncoder(
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    digest = hashlib.sha256()
    for part in encoder.iterencode(payload):
        digest.update(part.encode("ascii"))
    return digest.hexdigest()


def fingerprint_policy(policy: Policy) -> str:
    """Return a versioned SHA-256 fingerprint of one validated policy.

    Object keys are canonicalized while JSON array order is retained. Consequently,
    policy rule and condition order remain part of the exact policy provenance.
    """

    if not isinstance(policy, Policy):
        raise TypeError("policy must be a Policy")
    payload = {
        "fingerprint_version": POLICY_FINGERPRINT_VERSION,
        "policy": policy.to_dict(),
    }
    try:
        digest = _fingerprint_json(payload)
    except (TypeError, ValueError, UnicodeError) as exc:
        raise PolicyValidationError(
            f"policy cannot be fingerprinted: {type(exc).__name__}"
        ) from exc
    return f"v{POLICY_FINGERPRINT_VERSION}:sha256:{digest}"


def fingerprint_context_contract(contract: ContextContract) -> str:
    """Return a versioned SHA-256 fingerprint of one validated context contract."""

    if not isinstance(contract, ContextContract):
        raise TypeError("contract must be a ContextContract")
    payload = {
        "context_contract_fingerprint_version": CONTEXT_CONTRACT_FINGERPRINT_VERSION,
        "context_contract": contract.to_dict(),
    }
    try:
        digest = _fingerprint_json(payload)
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ContextContractValidationError(
            f"context contract cannot be fingerprinted: {type(exc).__name__}"
        ) from exc
    return f"v{CONTEXT_CONTRACT_FINGERPRINT_VERSION}:sha256:{digest}"


def fingerprint_tool_catalog(catalog: ToolCatalog) -> str:
    """Return a versioned SHA-256 fingerprint of one validated tool catalog."""

    if not isinstance(catalog, ToolCatalog):
        raise TypeError("catalog must be a ToolCatalog")
    payload = {
        "tool_catalog_fingerprint_version": TOOL_CATALOG_FINGERPRINT_VERSION,
        "tool_catalog": catalog.to_dict(),
    }
    try:
        digest = _fingerprint_json(payload)
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ToolCatalogValidationError(
            f"tool catalog cannot be fingerprinted: {type(exc).__name__}"
        ) from exc
    return f"v{TOOL_CATALOG_FINGERPRINT_VERSION}:sha256:{digest}"


def fingerprint_tool_gate_deployment(deployment: object) -> str:
    """Return a versioned SHA-256 fingerprint of one complete tool-gate deployment."""

    # Local import avoids the provenance/deployment module cycle.
    from .tool_gate_deployment import ToolGateDeployment

    if not isinstance(deployment, ToolGateDeployment):
        raise TypeError("deployment must be a ToolGateDeployment")
    payload = {
        "tool_gate_deployment_fingerprint_version": (TOOL_GATE_DEPLOYMENT_FINGERPRINT_VERSION),
        "deployment": deployment.to_dict(),
    }
    try:
        digest = _fingerprint_json(payload)
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ToolGateDeploymentValidationError(
            f"tool gate deployment cannot be fingerprinted: {type(exc).__name__}"
        ) from exc
    return f"v{TOOL_GATE_DEPLOYMENT_FINGERPRINT_VERSION}:sha256:{digest}"


def _is_policy_fingerprint(value: object) -> bool:
    return isinstance(value, str) and _POLICY_FINGERPRINT.fullmatch(value) is not None


def _is_context_contract_fingerprint(value: object) -> bool:
    return isinstance(value, str) and _CONTEXT_CONTRACT_FINGERPRINT.fullmatch(value) is not None


def _is_tool_gate_deployment_fingerprint(value: object) -> bool:
    return isinstance(value, str) and _TOOL_GATE_DEPLOYMENT_FINGERPRINT.fullmatch(value) is not None
