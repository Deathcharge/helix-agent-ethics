"""Bounded JSON loading, sample generation, and privacy-minimized audit output."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path
from typing import Any, BinaryIO

from .errors import AuditLogError, InputValidationError, PolicyValidationError
from .models import Decision, Policy

MAX_POLICY_BYTES = 1_048_576
MAX_INPUT_BYTES = 262_144
MAX_JSON_DEPTH = 32
MAX_CONTAINER_ITEMS = 10_000
MAX_STRING_LENGTH = 65_536

SAMPLE_POLICY: dict[str, Any] = {
    "schema_version": 1,
    "id": "safe-agent-actions",
    "version": "1.0.0",
    "description": "Example gate for read-only and explicitly approved agent actions.",
    "default_effect": "review",
    "rules": [
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


def _validate_json_shape(root: Any, *, label: str) -> None:
    stack: list[tuple[Any, int]] = [(root, 1)]
    seen_items = 0
    while stack:
        value, depth = stack.pop()
        if depth > MAX_JSON_DEPTH:
            raise InputValidationError(
                f"{label} exceeds the maximum JSON depth of {MAX_JSON_DEPTH}"
            )
        if isinstance(value, str) and len(value) > MAX_STRING_LENGTH:
            raise InputValidationError(
                f"{label} contains a string longer than {MAX_STRING_LENGTH} characters"
            )
        if isinstance(value, Mapping):
            seen_items += len(value)
            stack.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list):
            seen_items += len(value)
            stack.extend((item, depth + 1) for item in value)
        if seen_items > MAX_CONTAINER_ITEMS:
            raise InputValidationError(
                f"{label} exceeds the maximum of {MAX_CONTAINER_ITEMS} container items"
            )


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
    _validate_json_shape(value, label=label)
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
        raw = file_path.read_bytes()
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

    target = Path(path)
    if target.exists() and not force:
        raise PolicyValidationError(f"refusing to overwrite existing file: {target}")
    if not target.parent.exists():
        raise PolicyValidationError(f"parent directory does not exist: {target.parent}")
    payload = (json.dumps(SAMPLE_POLICY, indent=2, sort_keys=False) + "\n").encode("utf-8")
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=target.parent, prefix=f".{target.name}.", delete=False
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, target)
    except OSError as exc:
        if temporary_name:
            with suppress(OSError):
                Path(temporary_name).unlink(missing_ok=True)
        raise PolicyValidationError(f"cannot write sample policy {target}: {exc}") from exc
    return target.resolve()


def append_audit_record(path: str | Path, decision: Decision) -> None:
    """Append one metadata-only decision record and flush it to disk.

    Raw evaluation input is deliberately absent. The caller controls retention and
    filesystem permissions for the selected path.
    """

    target = Path(path)
    if not target.parent.exists():
        raise AuditLogError(f"audit-log parent directory does not exist: {target.parent}")
    record = {
        "decision_id": decision.decision_id,
        "evaluated_at": decision.evaluated_at,
        "policy_id": decision.policy_id,
        "policy_version": decision.policy_version,
        "outcome": decision.outcome.value,
        "matched_rules": list(decision.matched_rules),
        "warning_count": len(decision.warnings),
    }
    payload = (json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")
    flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    descriptor: int | None = None
    try:
        descriptor = os.open(target, flags, 0o600)
        written = os.write(descriptor, payload)
        if written != len(payload):
            raise OSError(f"short audit-log write: {written} of {len(payload)} bytes")
        os.fsync(descriptor)
    except OSError as exc:
        raise AuditLogError(f"cannot append audit record to {target}: {exc}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
