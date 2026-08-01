# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Approval evidence bound to one exact, normalized tool call."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .errors import InputValidationError
from .validation import validate_json_shape

TOOL_CALL_APPROVAL_VERSION = 1
TOOL_CALL_FINGERPRINT_VERSION = 1
MAX_TOOL_CALL_FINGERPRINT_BYTES = 1_048_576

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_FINGERPRINT = re.compile(r"^v1:sha256:[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class ToolCallApproval:
    """A caller-owned approval result bound to one framework tool-call ID and fingerprint."""

    tool_call_id: str
    approved: bool
    tool_call_fingerprint: str
    approval_version: int = TOOL_CALL_APPROVAL_VERSION

    def __post_init__(self) -> None:
        if (
            isinstance(self.approval_version, bool)
            or self.approval_version != TOOL_CALL_APPROVAL_VERSION
        ):
            raise ValueError(f"approval_version must be {TOOL_CALL_APPROVAL_VERSION}")
        if not isinstance(self.tool_call_id, str) or not _IDENTIFIER.fullmatch(self.tool_call_id):
            raise ValueError("tool_call_id must be a 1-128 character identifier")
        if not isinstance(self.approved, bool):
            raise TypeError("approved must be a boolean")
        if not isinstance(self.tool_call_fingerprint, str) or not _FINGERPRINT.fullmatch(
            self.tool_call_fingerprint
        ):
            raise ValueError(
                "tool_call_fingerprint must use the current v1:sha256 lowercase format"
            )

    @classmethod
    def from_dict(cls, value: Any) -> ToolCallApproval:
        """Parse a strict persisted approval record without authenticating its source."""

        validate_json_shape(value, label="tool-call approval")
        if not isinstance(value, Mapping):
            raise InputValidationError("tool-call approval must be a JSON object")
        required = {
            "approval_version",
            "tool_call_id",
            "approved",
            "tool_call_fingerprint",
        }
        missing = required - value.keys()
        extra = value.keys() - required
        if missing:
            raise InputValidationError(
                f"tool-call approval is missing: {', '.join(sorted(missing))}"
            )
        if extra:
            raise InputValidationError(
                f"tool-call approval has unknown fields: {', '.join(sorted(extra))}"
            )
        try:
            return cls(
                approval_version=value["approval_version"],
                tool_call_id=value["tool_call_id"],
                approved=value["approved"],
                tool_call_fingerprint=value["tool_call_fingerprint"],
            )
        except (TypeError, ValueError) as exc:
            raise InputValidationError(f"invalid tool-call approval: {exc}") from exc

    def to_dict(self) -> dict[str, Any]:
        """Return the detached JSON-compatible approval record."""

        return {
            "approval_version": self.approval_version,
            "tool_call_id": self.tool_call_id,
            "approved": self.approved,
            "tool_call_fingerprint": self.tool_call_fingerprint,
        }


def _fingerprint_prepared_tool_call(
    tool_call_id: str,
    *,
    tool_context_version: int,
    actor: dict[str, Any],
    action: dict[str, Any],
) -> str:
    if not isinstance(tool_call_id, str) or not _IDENTIFIER.fullmatch(tool_call_id):
        raise InputValidationError("tool call ID must be a 1-128 character identifier")
    payload = {
        "fingerprint_version": TOOL_CALL_FINGERPRINT_VERSION,
        "tool_context_version": tool_context_version,
        "tool_call_id": tool_call_id,
        "actor": actor,
        "action": action,
    }
    encoder = json.JSONEncoder(
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    digest = hashlib.sha256()
    encoded_bytes = 0
    try:
        for part in encoder.iterencode(payload):
            chunk = part.encode("ascii")
            encoded_bytes += len(chunk)
            if encoded_bytes > MAX_TOOL_CALL_FINGERPRINT_BYTES:
                raise InputValidationError(
                    "canonical tool call exceeds the fingerprint limit of "
                    f"{MAX_TOOL_CALL_FINGERPRINT_BYTES} bytes"
                )
            digest.update(chunk)
    except InputValidationError:
        raise
    except (TypeError, ValueError, UnicodeError) as exc:
        raise InputValidationError(
            f"tool call cannot be fingerprinted: {type(exc).__name__}"
        ) from exc
    return f"v{TOOL_CALL_FINGERPRINT_VERSION}:sha256:{digest.hexdigest()}"
