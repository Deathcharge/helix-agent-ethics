# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Versioned, privacy-minimized audit records and delivery sinks."""

from __future__ import annotations

import inspect
import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, cast

from .errors import AuditLogError, InputValidationError
from .models import Decision
from .provenance import _is_policy_fingerprint
from .validation import validate_json_shape

AUDIT_RECORD_VERSION = 1
MAX_COMPOSITE_AUDIT_SINKS = 32
_AUDIT_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_DECISION_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_EVALUATED_AT = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$"
)


@dataclass(frozen=True, slots=True)
class AuditRecord:
    """Immutable decision metadata that deliberately excludes evaluation input."""

    decision_id: str
    evaluated_at: str
    policy_id: str
    policy_version: str
    policy_fingerprint: str
    outcome: str
    matched_rules: tuple[str, ...]
    warning_count: int
    audit_record_version: int = AUDIT_RECORD_VERSION

    def __post_init__(self) -> None:
        if (
            isinstance(self.audit_record_version, bool)
            or self.audit_record_version != AUDIT_RECORD_VERSION
        ):
            raise ValueError(f"audit_record_version must be {AUDIT_RECORD_VERSION}")
        if not isinstance(self.decision_id, str) or not _DECISION_ID.fullmatch(self.decision_id):
            raise ValueError("decision_id must be a lowercase UUID string")
        if (
            not isinstance(self.evaluated_at, str)
            or len(self.evaluated_at) > 64
            or not _EVALUATED_AT.fullmatch(self.evaluated_at)
        ):
            raise ValueError("evaluated_at must be an RFC 3339 date-time of at most 64 characters")
        try:
            datetime.fromisoformat(self.evaluated_at)
        except ValueError as exc:
            raise ValueError("evaluated_at must be a valid RFC 3339 date-time") from exc
        for field, value in (
            ("policy_id", self.policy_id),
            ("policy_version", self.policy_version),
        ):
            if not isinstance(value, str) or not _AUDIT_IDENTIFIER.fullmatch(value):
                raise ValueError(f"{field} must be a 1-128 character identifier")
        if not _is_policy_fingerprint(self.policy_fingerprint):
            raise ValueError("policy_fingerprint must use the current v1:sha256 lowercase format")
        if not isinstance(self.outcome, str) or self.outcome not in {"allow", "deny", "review"}:
            raise ValueError("outcome must be allow, deny, or review")
        if not isinstance(self.matched_rules, tuple):
            raise TypeError("matched_rules must be a tuple")
        if len(self.matched_rules) > 1_000:
            raise ValueError("matched_rules exceeds the limit of 1000")
        if any(
            not isinstance(rule_id, str) or not _AUDIT_IDENTIFIER.fullmatch(rule_id)
            for rule_id in self.matched_rules
        ):
            raise ValueError("matched_rules must contain 1-128 character identifiers")
        if len(set(self.matched_rules)) != len(self.matched_rules):
            raise ValueError("matched_rules must not contain duplicates")
        if (
            isinstance(self.warning_count, bool)
            or not isinstance(self.warning_count, int)
            or not 0 <= self.warning_count <= 1_000
        ):
            raise ValueError("warning_count must be an integer from 0 to 1000")

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
            policy_fingerprint=decision.policy_fingerprint,
            outcome=decision.outcome.value,
            matched_rules=decision.matched_rules,
            warning_count=len(decision.warnings),
        )

    @classmethod
    def from_dict(cls, value: Any) -> AuditRecord:
        """Parse one strict persisted metadata-only audit record."""

        try:
            validate_json_shape(value, label="audit record")
        except InputValidationError as exc:
            raise AuditLogError(str(exc)) from exc
        if not isinstance(value, Mapping):
            raise AuditLogError("audit record must be a JSON object")
        required = {
            "audit_record_version",
            "decision_id",
            "evaluated_at",
            "policy_id",
            "policy_version",
            "policy_fingerprint",
            "outcome",
            "matched_rules",
            "warning_count",
        }
        missing = required - value.keys()
        extra = value.keys() - required
        if missing:
            raise AuditLogError(f"audit record is missing: {', '.join(sorted(missing))}")
        if extra:
            raise AuditLogError(f"audit record has unknown fields: {', '.join(sorted(extra))}")
        matched_rules = value["matched_rules"]
        if not isinstance(matched_rules, list):
            raise AuditLogError("audit record matched_rules must be a JSON array")
        try:
            return cls(
                audit_record_version=value["audit_record_version"],
                decision_id=value["decision_id"],
                evaluated_at=value["evaluated_at"],
                policy_id=value["policy_id"],
                policy_version=value["policy_version"],
                policy_fingerprint=value["policy_fingerprint"],
                outcome=value["outcome"],
                matched_rules=tuple(matched_rules),
                warning_count=value["warning_count"],
            )
        except (TypeError, ValueError) as exc:
            raise AuditLogError(f"invalid audit record: {exc}") from exc

    def to_dict(self) -> dict[str, Any]:
        """Return a detached JSON-compatible record."""

        return {
            "audit_record_version": self.audit_record_version,
            "decision_id": self.decision_id,
            "evaluated_at": self.evaluated_at,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "policy_fingerprint": self.policy_fingerprint,
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
        failure: OSError | None = None
        try:
            descriptor = os.open(self._path, flags, 0o600)
            written = os.write(descriptor, payload)
            if written != len(payload):
                raise OSError(f"short audit-log write: {written} of {len(payload)} bytes")
            os.fsync(descriptor)
        except OSError as exc:
            failure = exc
        finally:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError as exc:
                    if failure is None:
                        failure = exc
        if failure is not None:
            raise AuditLogError(
                f"cannot append audit record to {self._path}: {failure}"
            ) from failure


def _validated_sink(sink: AuditSink) -> AuditSink:
    if not callable(sink):
        raise TypeError("audit_sink must be a synchronous callable")
    async_call = inspect.iscoroutinefunction(sink) or inspect.iscoroutinefunction(
        type(sink).__call__
    )
    if async_call:
        raise TypeError("audit_sink must be a synchronous callable")
    return sink


def _deliver_audit_record(sink: AuditSink, record: AuditRecord) -> None:
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


class CompositeAuditSink:
    """Deliver one record to a bounded ordered set of synchronous sinks."""

    def __init__(self, *sinks: AuditSink) -> None:
        if not 1 <= len(sinks) <= MAX_COMPOSITE_AUDIT_SINKS:
            raise ValueError(f"composite audit sink requires 1-{MAX_COMPOSITE_AUDIT_SINKS} sinks")
        if len({id(sink) for sink in sinks}) != len(sinks):
            raise ValueError("composite audit sink must not contain duplicate sink objects")
        self._sinks = tuple(_validated_sink(sink) for sink in sinks)

    @property
    def sinks(self) -> tuple[AuditSink, ...]:
        """Return the immutable delivery order."""

        return self._sinks

    def __call__(self, record: AuditRecord, /) -> None:
        if not isinstance(record, AuditRecord):
            raise TypeError("record must be an AuditRecord")
        for sink in self._sinks:
            _deliver_audit_record(sink, record)


def _emit_audit_record(sink: AuditSink, decision: Decision) -> None:
    _deliver_audit_record(sink, AuditRecord.from_decision(decision))
