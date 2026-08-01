# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Versioned, privacy-minimized audit records and delivery sinks."""

from __future__ import annotations

import inspect
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from .errors import AuditLogError
from .models import Decision

AUDIT_RECORD_VERSION = 1


@dataclass(frozen=True, slots=True)
class AuditRecord:
    """Immutable decision metadata that deliberately excludes evaluation input."""

    decision_id: str
    evaluated_at: str
    policy_id: str
    policy_version: str
    outcome: str
    matched_rules: tuple[str, ...]
    warning_count: int
    audit_record_version: int = AUDIT_RECORD_VERSION

    def __post_init__(self) -> None:
        if self.audit_record_version != AUDIT_RECORD_VERSION:
            raise ValueError(f"audit_record_version must be {AUDIT_RECORD_VERSION}")

    @classmethod
    def from_decision(cls, decision: Decision) -> AuditRecord:
        """Build the public metadata-only record for one decision."""

        if not isinstance(decision, Decision):
            raise TypeError("decision must be a Decision")
        return cls(
            decision_id=decision.decision_id,
            evaluated_at=decision.evaluated_at,
            policy_id=decision.policy_id,
            policy_version=decision.policy_version,
            outcome=decision.outcome.value,
            matched_rules=decision.matched_rules,
            warning_count=len(decision.warnings),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a detached JSON-compatible record."""

        return {
            "audit_record_version": self.audit_record_version,
            "decision_id": self.decision_id,
            "evaluated_at": self.evaluated_at,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "outcome": self.outcome,
            "matched_rules": list(self.matched_rules),
            "warning_count": self.warning_count,
        }


class AuditSink(Protocol):
    """Synchronous application-owned destination for one audit record."""

    def __call__(self, record: AuditRecord, /) -> None:
        """Store one record or raise when storage did not succeed."""


class JsonlAuditSink:
    """Append metadata-only records to a local JSON Lines file and flush each write."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        """Return the configured output path."""

        return self._path

    def __call__(self, record: AuditRecord, /) -> None:
        if not isinstance(record, AuditRecord):
            raise TypeError("record must be an AuditRecord")
        if not self._path.parent.exists():
            raise AuditLogError(f"audit-log parent directory does not exist: {self._path.parent}")
        payload = (
            json.dumps(record.to_dict(), separators=(",", ":"), sort_keys=True) + "\n"
        ).encode("utf-8")
        flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        descriptor: int | None = None
        try:
            descriptor = os.open(self._path, flags, 0o600)
            written = os.write(descriptor, payload)
            if written != len(payload):
                raise OSError(f"short audit-log write: {written} of {len(payload)} bytes")
            os.fsync(descriptor)
        except OSError as exc:
            raise AuditLogError(f"cannot append audit record to {self._path}: {exc}") from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)


def _validated_sink(sink: AuditSink) -> AuditSink:
    if not callable(sink):
        raise TypeError("audit_sink must be a synchronous callable")
    async_call = inspect.iscoroutinefunction(sink) or inspect.iscoroutinefunction(
        type(sink).__call__
    )
    if async_call:
        raise TypeError("audit_sink must be a synchronous callable")
    return sink


def _emit_audit_record(sink: AuditSink, decision: Decision) -> None:
    record = AuditRecord.from_decision(decision)
    try:
        result = cast(Any, sink(record))
    except AuditLogError:
        raise
    except Exception as exc:
        raise AuditLogError(f"audit sink failed: {type(exc).__name__}") from exc
    if inspect.iscoroutine(result):
        result.close()
    if result is not None:
        raise AuditLogError("audit sink must return None")
