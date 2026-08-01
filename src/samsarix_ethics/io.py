# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Bounded JSON loading, sample generation, and privacy-minimized audit output."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any, BinaryIO

from ._policy_payload import MAX_POLICY_BYTES, serialize_policy_document
from .audit import AuditRecord, JsonlAuditSink
from .contracts import ContextContract
from .deployment import DeploymentLock
from .errors import (
    ContextContractValidationError,
    DeploymentLockValidationError,
    InputValidationError,
    PolicyDeploymentValidationError,
    PolicyValidationError,
    SamsarixEthicsError,
)
from .models import Decision, Policy
from .policy_deployment import PolicyDeployment
from .validation import validate_json_shape

MAX_INPUT_BYTES = 262_144
MAX_CONTEXT_CONTRACT_BYTES = 262_144
MAX_DEPLOYMENT_LOCK_BYTES = 65_536
MAX_POLICY_DEPLOYMENT_BYTES = 4_194_304

SAMPLE_POLICY: dict[str, Any] = {
    "schema_version": 1,
    "id": "safe-agent-actions",
    "version": "1.0.0",
    "description": "Example gate for read-only and explicitly approved agent actions.",
    "default_effect": "review",
    "rules": [
        {
            "id": "deny-destructive-action-without-approval",
            "effect": "deny",
            "priority": 5,
            "message": "Destructive actions require explicit human approval.",
            "conditions": [
                {
                    "field": "action.operation",
                    "operator": "in",
                    "value": ["delete", "destroy", "publish", "release", "send"],
                },
                {"field": "context.human_approved", "operator": "not_exists"},
            ],
        },
        {
            "id": "deny-unapproved-destructive-action",
            "effect": "deny",
            "priority": 10,
            "message": "Destructive actions require explicit human approval.",
            "conditions": [
                {
                    "field": "action.operation",
                    "operator": "in",
                    "value": ["delete", "destroy", "publish", "release", "send"],
                },
                {"field": "context.human_approved", "operator": "neq", "value": True},
            ],
        },
        {
            "id": "review-high-risk-action",
            "effect": "review",
            "priority": 20,
            "message": "High-risk actions require human review.",
            "conditions": [
                {"field": "action.risk", "operator": "in", "value": ["high", "critical"]}
            ],
        },
        {
            "id": "allow-read-only-action",
            "effect": "allow",
            "priority": 100,
            "message": "Read-only actions are permitted.",
            "conditions": [
                {
                    "field": "action.operation",
                    "operator": "in",
                    "value": ["inspect", "list", "read", "search"],
                }
            ],
        },
        {
            "id": "allow-approved-low-risk-action",
            "effect": "allow",
            "priority": 110,
            "message": "The action is low-risk and has explicit human approval.",
            "conditions": [
                {"field": "context.human_approved", "operator": "eq", "value": True},
                {"field": "action.risk", "operator": "in", "value": ["low", "medium"]},
            ],
        },
        {
            "id": "warn-sensitive-data",
            "effect": "warn",
            "priority": 200,
            "message": "The action references sensitive data; minimize audit content.",
            "conditions": [
                {
                    "field": "data.sensitivity",
                    "operator": "in",
                    "value": ["confidential", "restricted"],
                }
            ],
        },
    ],
}


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite number {value!r} is not valid JSON input")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate object key {key!r}")
        result[key] = value
    return result


def _parse_json(raw: bytes, *, label: str) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InputValidationError(f"{label} must be UTF-8") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise InputValidationError(f"{label} is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise InputValidationError(f"{label} must contain a JSON object")
    validate_json_shape(value, label=label)
    return value


def _read_file(path: str | Path, *, max_bytes: int, label: str) -> bytes:
    file_path = Path(path)
    try:
        size = file_path.stat().st_size
    except OSError as exc:
        raise InputValidationError(f"cannot read {label} {file_path}: {exc}") from exc
    if not file_path.is_file():
        raise InputValidationError(f"{label} is not a regular file: {file_path}")
    if size > max_bytes:
        raise InputValidationError(f"{label} exceeds the byte limit of {max_bytes}")
    try:
        with file_path.open("rb") as stream:
            raw = stream.read(max_bytes + 1)
    except OSError as exc:
        raise InputValidationError(f"cannot read {label} {file_path}: {exc}") from exc
    if len(raw) > max_bytes:
        raise InputValidationError(f"{label} exceeds the byte limit of {max_bytes}")
    return raw


def _read_stream(stream: BinaryIO, *, max_bytes: int, label: str) -> bytes:
    raw = stream.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise InputValidationError(f"{label} exceeds the byte limit of {max_bytes}")
    return raw


def load_policy(path: str | Path) -> Policy:
    """Load and validate a bounded JSON policy file."""

    try:
        data = _parse_json(
            _read_file(path, max_bytes=MAX_POLICY_BYTES, label="policy"),
            label="policy",
        )
        return Policy.from_dict(data)
    except InputValidationError as exc:
        raise PolicyValidationError(str(exc)) from exc


def load_context_contract(path: str | Path) -> ContextContract:
    """Load and validate a bounded JSON context-contract file."""

    try:
        data = _parse_json(
            _read_file(
                path,
                max_bytes=MAX_CONTEXT_CONTRACT_BYTES,
                label="context contract",
            ),
            label="context contract",
        )
        return ContextContract.from_dict(data)
    except InputValidationError as exc:
        raise ContextContractValidationError(str(exc)) from exc


def load_deployment_lock(path: str | Path) -> DeploymentLock:
    """Load and validate a bounded JSON deployment-lock file."""

    try:
        data = _parse_json(
            _read_file(
                path,
                max_bytes=MAX_DEPLOYMENT_LOCK_BYTES,
                label="deployment lock",
            ),
            label="deployment lock",
        )
        return DeploymentLock.from_dict(data)
    except InputValidationError as exc:
        raise DeploymentLockValidationError(str(exc)) from exc


def load_policy_deployment(path: str | Path) -> PolicyDeployment:
    """Load and internally verify one bounded single-file policy deployment."""

    try:
        data = _parse_json(
            _read_file(
                path,
                max_bytes=MAX_POLICY_DEPLOYMENT_BYTES,
                label="policy deployment",
            ),
            label="policy deployment",
        )
        return PolicyDeployment.from_dict(data)
    except InputValidationError as exc:
        raise PolicyDeploymentValidationError(str(exc)) from exc


def load_context(path: str | Path | None, *, stdin: BinaryIO | None = None) -> dict[str, Any]:
    """Load a bounded evaluation object from a path or binary standard input."""

    if path is None or str(path) == "-":
        if stdin is None:
            raise InputValidationError("standard input was requested but no stream was provided")
        raw = _read_stream(stdin, max_bytes=MAX_INPUT_BYTES, label="input")
    else:
        raw = _read_file(path, max_bytes=MAX_INPUT_BYTES, label="input")
    return _parse_json(raw, label="input")


def write_sample_policy(path: str | Path, *, force: bool = False) -> Path:
    """Write the bundled sample atomically, refusing overwrite unless requested."""

    return _write_policy_payload(path, SAMPLE_POLICY, force=force, label="sample policy")


def write_policy(path: str | Path, policy: Policy, *, force: bool = False) -> Path:
    """Write a validated policy atomically, refusing overwrite unless requested."""

    if not isinstance(policy, Policy):
        raise TypeError("policy must be a Policy")
    return _write_policy_payload(path, policy.to_dict(), force=force, label="policy")


def write_policy_deployment(
    path: str | Path,
    deployment: PolicyDeployment,
    *,
    force: bool = False,
) -> Path:
    """Atomically write one verified deployment, refusing implicit overwrite."""

    if not isinstance(deployment, PolicyDeployment):
        raise TypeError("deployment must be a PolicyDeployment")
    encoder = json.JSONEncoder(allow_nan=False, ensure_ascii=True, indent=2, sort_keys=False)
    payload = bytearray()
    try:
        for part in encoder.iterencode(deployment.to_dict()):
            chunk = part.encode("ascii")
            if len(payload) + len(chunk) + 1 > MAX_POLICY_DEPLOYMENT_BYTES:
                raise PolicyDeploymentValidationError(
                    "policy deployment exceeds the byte limit of "
                    f"{MAX_POLICY_DEPLOYMENT_BYTES} when serialized"
                )
            payload.extend(chunk)
    except (TypeError, ValueError, UnicodeError) as exc:
        raise PolicyDeploymentValidationError(
            f"policy deployment cannot be serialized: {type(exc).__name__}"
        ) from exc
    payload.extend(b"\n")
    return _write_atomic_payload(
        path,
        bytes(payload),
        force=force,
        label="policy deployment",
        error_type=PolicyDeploymentValidationError,
    )


def _write_policy_payload(
    path: str | Path,
    value: dict[str, Any],
    *,
    force: bool,
    label: str,
) -> Path:
    payload = serialize_policy_document(value, label=label)
    return _write_atomic_payload(
        path,
        payload,
        force=force,
        label=label,
        error_type=PolicyValidationError,
    )


def _write_atomic_payload(
    path: str | Path,
    payload: bytes,
    *,
    force: bool,
    label: str,
    error_type: type[SamsarixEthicsError],
) -> Path:
    """Durably replace or exclusively create one already serialized JSON payload."""

    target = Path(path)
    if target.exists() and not force:
        raise error_type(f"refusing to overwrite existing file: {target}")
    if not target.parent.exists():
        raise error_type(f"parent directory does not exist: {target.parent}")
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=target.parent, prefix=f".{target.name}.", delete=False
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        if force:
            os.replace(temporary_name, target)
        else:
            try:
                os.link(temporary_name, target)
            except FileExistsError as exc:
                raise error_type(f"refusing to overwrite existing file: {target}") from exc
            Path(temporary_name).unlink()
        temporary_name = None
    except SamsarixEthicsError:
        if temporary_name:
            with suppress(OSError):
                Path(temporary_name).unlink(missing_ok=True)
        raise
    except OSError as exc:
        if temporary_name:
            with suppress(OSError):
                Path(temporary_name).unlink(missing_ok=True)
        raise error_type(f"cannot write {label} {target}: {exc}") from exc
    return target.resolve()


def append_audit_record(path: str | Path, decision: Decision) -> None:
    """Append one metadata-only decision record and flush it to disk.

    Raw evaluation input is deliberately absent. The caller controls retention and
    filesystem permissions for the selected path.
    """

    JsonlAuditSink(path)(AuditRecord.from_decision(decision))
