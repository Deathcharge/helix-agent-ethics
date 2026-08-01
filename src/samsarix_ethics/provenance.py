# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Deterministic provenance identifiers for validated policy artifacts."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from .contracts import ContextContract
from .errors import ContextContractValidationError, PolicyValidationError
from .models import Policy

POLICY_FINGERPRINT_VERSION = 1
CONTEXT_CONTRACT_FINGERPRINT_VERSION = 1

_POLICY_FINGERPRINT = re.compile(r"^v1:sha256:[0-9a-f]{64}$")
_CONTEXT_CONTRACT_FINGERPRINT = re.compile(r"^v1:sha256:[0-9a-f]{64}$")


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


def _is_policy_fingerprint(value: object) -> bool:
    return isinstance(value, str) and _POLICY_FINGERPRINT.fullmatch(value) is not None


def _is_context_contract_fingerprint(value: object) -> bool:
    return isinstance(value, str) and _CONTEXT_CONTRACT_FINGERPRINT.fullmatch(value) is not None
