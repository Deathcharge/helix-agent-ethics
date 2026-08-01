# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Deterministic provenance identifiers for validated policies."""

from __future__ import annotations

import hashlib
import json
import re

from .errors import PolicyValidationError
from .models import Policy

POLICY_FINGERPRINT_VERSION = 1

_POLICY_FINGERPRINT = re.compile(r"^v1:sha256:[0-9a-f]{64}$")


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
    encoder = json.JSONEncoder(
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    digest = hashlib.sha256()
    try:
        for part in encoder.iterencode(payload):
            chunk = part.encode("ascii")
            digest.update(chunk)
    except (TypeError, ValueError, UnicodeError) as exc:
        raise PolicyValidationError(
            f"policy cannot be fingerprinted: {type(exc).__name__}"
        ) from exc
    return f"v{POLICY_FINGERPRINT_VERSION}:sha256:{digest.hexdigest()}"


def _is_policy_fingerprint(value: object) -> bool:
    return isinstance(value, str) and _POLICY_FINGERPRINT.fullmatch(value) is not None
