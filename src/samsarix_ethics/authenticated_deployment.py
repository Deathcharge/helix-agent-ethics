# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Freshness-aware HMAC authentication for complete tool-gate deployments."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from secrets import token_bytes
from typing import Any

from .errors import (
    DeploymentAuthenticationError,
    InputValidationError,
    ToolGateDeploymentValidationError,
)
from .provenance import (
    _is_tool_gate_deployment_fingerprint,
    fingerprint_tool_gate_deployment,
)
from .tool_gate_deployment import ToolGateDeployment
from .validation import validate_json_shape

TOOL_GATE_DEPLOYMENT_AUTH_VERSION = 1
MIN_DEPLOYMENT_AUTH_KEY_BYTES = 32
MAX_DEPLOYMENT_AUTH_KEY_BYTES = 4_096
MAX_DEPLOYMENT_AUTH_KEYS = 32
MAX_DEPLOYMENT_AUTH_SEQUENCE = 9_223_372_036_854_775_807
MAX_DEPLOYMENT_AUTH_LIFETIME_SECONDS = 2_592_000
MAX_DEPLOYMENT_AUTH_CLOCK_SKEW_SECONDS = 3_600

_ALGORITHM = "hmac-sha256"
_DOMAIN = b"samsarix-agent-ethics:tool-gate-deployment-auth:v1\x00"
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_AUDIENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_MAC_PREFIX = f"v{TOOL_GATE_DEPLOYMENT_AUTH_VERSION}:{_ALGORITHM}"
_MAC = re.compile(rf"^{re.escape(_MAC_PREFIX)}:[0-9a-f]{{64}}$")


def _key(value: object, *, label: str = "deployment authentication key") -> bytes:
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise DeploymentAuthenticationError(f"{label} must be bytes-like")
    copied = bytes(value)
    if not MIN_DEPLOYMENT_AUTH_KEY_BYTES <= len(copied) <= MAX_DEPLOYMENT_AUTH_KEY_BYTES:
        raise DeploymentAuthenticationError(
            f"{label} must contain {MIN_DEPLOYMENT_AUTH_KEY_BYTES}-"
            f"{MAX_DEPLOYMENT_AUTH_KEY_BYTES} bytes"
        )
    return copied


def _identifier(value: object, *, label: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise DeploymentAuthenticationError(f"{label} must be a 1-128 character identifier")
    return value


def _audience(value: object) -> str:
    if not isinstance(value, str) or _AUDIENCE.fullmatch(value) is None:
        raise DeploymentAuthenticationError(
            "audience must be 1-256 characters using letters, digits, '.', '_', ':', '/', or '-'"
        )
    return value


def _sequence(value: object, *, label: str = "sequence") -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= MAX_DEPLOYMENT_AUTH_SEQUENCE
    ):
        raise DeploymentAuthenticationError(
            f"{label} must be an integer from 1 to {MAX_DEPLOYMENT_AUTH_SEQUENCE}"
        )
    return value


def _timestamp(value: object, *, label: str) -> datetime:
    if not isinstance(value, str) or _TIMESTAMP.fullmatch(value) is None:
        raise DeploymentAuthenticationError(
            f"{label} must be an RFC 3339 UTC timestamp with whole seconds"
        )
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise DeploymentAuthenticationError(f"{label} is not a valid UTC timestamp") from exc


def _verification_time(value: datetime | None) -> datetime:
    selected = datetime.now(UTC) if value is None else value
    if not isinstance(selected, datetime) or selected.tzinfo is None:
        raise TypeError("now must be a timezone-aware datetime or None")
    return selected.astimezone(UTC)


def _clock_skew(value: object) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= MAX_DEPLOYMENT_AUTH_CLOCK_SKEW_SECONDS
    ):
        raise ValueError(
            "clock_skew_seconds must be an integer from 0 to "
            f"{MAX_DEPLOYMENT_AUTH_CLOCK_SKEW_SECONDS}"
        )
    return value


def _unsigned_fields(
    *,
    key_id: str,
    audience: str,
    sequence: int,
    issued_at: str,
    expires_at: str,
    deployment: ToolGateDeployment,
    deployment_fingerprint: str,
) -> dict[str, Any]:
    return {
        "tool_gate_deployment_auth_version": TOOL_GATE_DEPLOYMENT_AUTH_VERSION,
        "algorithm": _ALGORITHM,
        "key_id": key_id,
        "audience": audience,
        "sequence": sequence,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "deployment_fingerprint": deployment_fingerprint,
        "deployment": deployment.to_dict(),
    }


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    except (TypeError, UnicodeError, ValueError) as exc:
        raise DeploymentAuthenticationError(
            f"deployment envelope cannot be canonically encoded: {type(exc).__name__}"
        ) from exc


def _mac(key: bytes, unsigned: Mapping[str, Any]) -> str:
    digest = hmac.new(key, _DOMAIN + _canonical_bytes(unsigned), hashlib.sha256).hexdigest()
    return f"{_MAC_PREFIX}:{digest}"


def generate_deployment_auth_key() -> bytes:
    """Return a fresh 256-bit key for deployment-envelope authentication."""

    return token_bytes(MIN_DEPLOYMENT_AUTH_KEY_BYTES)


@dataclass(frozen=True, slots=True, repr=False)
class ToolGateDeploymentEnvelope:
    """An untrusted deployment plus authenticated routing and freshness claims."""

    key_id: str
    audience: str
    sequence: int
    issued_at: str
    expires_at: str
    deployment_fingerprint: str
    deployment: ToolGateDeployment
    mac: str
    algorithm: str = _ALGORITHM
    tool_gate_deployment_auth_version: int = TOOL_GATE_DEPLOYMENT_AUTH_VERSION

    def __repr__(self) -> str:
        """Return authentication metadata without policy or catalog contents."""

        return (
            "ToolGateDeploymentEnvelope("
            f"key_id={self.key_id!r}, audience={self.audience!r}, "
            f"sequence={self.sequence}, expires_at={self.expires_at!r})"
        )

    def __post_init__(self) -> None:
        if (
            isinstance(self.tool_gate_deployment_auth_version, bool)
            or self.tool_gate_deployment_auth_version != TOOL_GATE_DEPLOYMENT_AUTH_VERSION
        ):
            raise DeploymentAuthenticationError("tool_gate_deployment_auth_version must be 1")
        if self.algorithm != _ALGORITHM:
            raise DeploymentAuthenticationError(f"algorithm must be {_ALGORITHM!r}")
        _identifier(self.key_id, label="key_id")
        _audience(self.audience)
        _sequence(self.sequence)
        issued = _timestamp(self.issued_at, label="issued_at")
        expires = _timestamp(self.expires_at, label="expires_at")
        if expires <= issued:
            raise DeploymentAuthenticationError("expires_at must be later than issued_at")
        if expires - issued > timedelta(seconds=MAX_DEPLOYMENT_AUTH_LIFETIME_SECONDS):
            raise DeploymentAuthenticationError(
                "deployment authentication lifetime exceeds the limit of "
                f"{MAX_DEPLOYMENT_AUTH_LIFETIME_SECONDS} seconds"
            )
        if not isinstance(self.deployment, ToolGateDeployment):
            raise DeploymentAuthenticationError("deployment must be a ToolGateDeployment")
        expected_fingerprint = fingerprint_tool_gate_deployment(self.deployment)
        if not _is_tool_gate_deployment_fingerprint(self.deployment_fingerprint):
            raise DeploymentAuthenticationError(
                "deployment_fingerprint must use the v1 SHA-256 fingerprint format"
            )
        if not hmac.compare_digest(self.deployment_fingerprint, expected_fingerprint):
            raise DeploymentAuthenticationError(
                "deployment fingerprint does not match the embedded deployment"
            )
        if not isinstance(self.mac, str) or _MAC.fullmatch(self.mac) is None:
            raise DeploymentAuthenticationError(
                "mac must use the current v1:hmac-sha256 lowercase format"
            )

    @classmethod
    def from_dict(cls, value: Any) -> ToolGateDeploymentEnvelope:
        """Strictly parse an envelope without trusting its MAC or claims."""

        try:
            validate_json_shape(value, label="tool gate deployment envelope")
        except InputValidationError as exc:
            raise DeploymentAuthenticationError(str(exc)) from exc
        if not isinstance(value, dict):
            raise DeploymentAuthenticationError(
                "tool gate deployment envelope must be a JSON object"
            )
        required = {
            "tool_gate_deployment_auth_version",
            "algorithm",
            "key_id",
            "audience",
            "sequence",
            "issued_at",
            "expires_at",
            "deployment_fingerprint",
            "deployment",
            "mac",
        }
        missing = sorted(required - value.keys())
        unknown = sorted(value.keys() - required)
        if missing:
            raise DeploymentAuthenticationError(
                f"tool gate deployment envelope is missing: {', '.join(missing)}"
            )
        if unknown:
            raise DeploymentAuthenticationError(
                f"tool gate deployment envelope has unknown fields: {', '.join(unknown)}"
            )
        try:
            deployment = ToolGateDeployment.from_dict(value["deployment"])
        except ToolGateDeploymentValidationError as exc:
            raise DeploymentAuthenticationError(
                f"deployment envelope contains an invalid tool gate deployment: {exc}"
            ) from exc
        return cls(
            tool_gate_deployment_auth_version=value["tool_gate_deployment_auth_version"],
            algorithm=value["algorithm"],
            key_id=value["key_id"],
            audience=value["audience"],
            sequence=value["sequence"],
            issued_at=value["issued_at"],
            expires_at=value["expires_at"],
            deployment_fingerprint=value["deployment_fingerprint"],
            deployment=deployment,
            mac=value["mac"],
        )

    def unsigned_dict(self) -> dict[str, Any]:
        """Return fresh canonical fields authenticated by the envelope MAC."""

        return _unsigned_fields(
            key_id=self.key_id,
            audience=self.audience,
            sequence=self.sequence,
            issued_at=self.issued_at,
            expires_at=self.expires_at,
            deployment=self.deployment,
            deployment_fingerprint=self.deployment_fingerprint,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a fresh JSON-compatible envelope document."""

        value = self.unsigned_dict()
        value["mac"] = self.mac
        return value


@dataclass(frozen=True, slots=True, init=False, repr=False)
class VerifiedToolGateDeployment:
    """A deployment whose envelope was authenticated against current trust inputs."""

    envelope: ToolGateDeploymentEnvelope
    verified_at: str

    def __init__(self) -> None:
        raise TypeError(
            "VerifiedToolGateDeployment objects are created by verify_tool_gate_deployment_envelope"
        )

    @classmethod
    def _create(
        cls,
        envelope: ToolGateDeploymentEnvelope,
        verified_at: datetime,
    ) -> VerifiedToolGateDeployment:
        verified = object.__new__(cls)
        object.__setattr__(verified, "envelope", envelope)
        object.__setattr__(
            verified,
            "verified_at",
            verified_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        return verified

    def __repr__(self) -> str:
        """Return authenticated identity without policy or catalog contents."""

        return (
            "VerifiedToolGateDeployment("
            f"key_id={self.key_id!r}, audience={self.audience!r}, "
            f"sequence={self.sequence}, verified_at={self.verified_at!r})"
        )

    @property
    def deployment(self) -> ToolGateDeployment:
        """Return the complete deployment authenticated by this verification."""

        return self.envelope.deployment

    @property
    def key_id(self) -> str:
        """Return the trusted key identifier selected during verification."""

        return self.envelope.key_id

    @property
    def audience(self) -> str:
        """Return the authenticated deployment audience."""

        return self.envelope.audience

    @property
    def sequence(self) -> int:
        """Return the authenticated monotonic deployment sequence."""

        return self.envelope.sequence

    @property
    def deployment_fingerprint(self) -> str:
        """Return the authenticated exact deployment fingerprint."""

        return self.envelope.deployment_fingerprint


def authenticate_tool_gate_deployment(
    deployment: ToolGateDeployment,
    key: bytes | bytearray | memoryview,
    *,
    key_id: str,
    audience: str,
    sequence: int,
    issued_at: str,
    expires_at: str,
) -> ToolGateDeploymentEnvelope:
    """Create an HMAC-authenticated envelope for one complete deployment."""

    if not isinstance(deployment, ToolGateDeployment):
        raise TypeError("deployment must be a ToolGateDeployment")
    selected_key = _key(key)
    selected_key_id = _identifier(key_id, label="key_id")
    selected_audience = _audience(audience)
    selected_sequence = _sequence(sequence)
    deployment_fingerprint = fingerprint_tool_gate_deployment(deployment)
    unsigned = _unsigned_fields(
        key_id=selected_key_id,
        audience=selected_audience,
        sequence=selected_sequence,
        issued_at=issued_at,
        expires_at=expires_at,
        deployment=deployment,
        deployment_fingerprint=deployment_fingerprint,
    )
    return ToolGateDeploymentEnvelope(
        key_id=selected_key_id,
        audience=selected_audience,
        sequence=selected_sequence,
        issued_at=issued_at,
        expires_at=expires_at,
        deployment_fingerprint=deployment_fingerprint,
        deployment=deployment,
        mac=_mac(selected_key, unsigned),
    )


def verify_tool_gate_deployment_envelope(
    envelope: ToolGateDeploymentEnvelope,
    keys: Mapping[str, bytes | bytearray | memoryview],
    *,
    expected_audience: str,
    minimum_sequence: int = 1,
    now: datetime | None = None,
    clock_skew_seconds: int = 0,
) -> VerifiedToolGateDeployment:
    """Authenticate an envelope and enforce audience, sequence, and validity claims."""

    if not isinstance(envelope, ToolGateDeploymentEnvelope):
        raise TypeError("envelope must be a ToolGateDeploymentEnvelope")
    if not isinstance(keys, Mapping):
        raise TypeError("keys must be a mapping of key IDs to bytes-like secrets")
    if len(keys) > MAX_DEPLOYMENT_AUTH_KEYS:
        raise DeploymentAuthenticationError(
            f"deployment authentication keyring exceeds {MAX_DEPLOYMENT_AUTH_KEYS} keys"
        )
    trusted_key_id = _identifier(envelope.key_id, label="authentication key ID")
    try:
        raw_selected_key = keys[trusted_key_id]
    except KeyError:
        raise DeploymentAuthenticationError(
            f"deployment authentication key {envelope.key_id!r} is not trusted"
        ) from None
    selected_key = _key(
        raw_selected_key,
        label=f"deployment authentication key {trusted_key_id!r}",
    )
    expected_mac = _mac(selected_key, envelope.unsigned_dict())
    if not hmac.compare_digest(envelope.mac, expected_mac):
        raise DeploymentAuthenticationError("deployment envelope MAC verification failed")

    trusted_audience = _audience(expected_audience)
    if not hmac.compare_digest(envelope.audience, trusted_audience):
        raise DeploymentAuthenticationError("deployment envelope audience does not match")
    trusted_minimum = _sequence(minimum_sequence, label="minimum_sequence")
    if envelope.sequence < trusted_minimum:
        raise DeploymentAuthenticationError(
            "deployment envelope sequence is older than the trusted minimum"
        )
    skew = _clock_skew(clock_skew_seconds)
    verified_at = _verification_time(now)
    issued = _timestamp(envelope.issued_at, label="issued_at")
    expires = _timestamp(envelope.expires_at, label="expires_at")
    allowed_skew = timedelta(seconds=skew)
    if issued - verified_at > allowed_skew:
        raise DeploymentAuthenticationError("deployment envelope is not yet valid")
    if verified_at - expires >= allowed_skew:
        raise DeploymentAuthenticationError("deployment envelope has expired")
    return VerifiedToolGateDeployment._create(envelope, verified_at)
