# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Keyed, metadata-only integrity chains for audit records."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import stat
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .audit import AuditRecord
from .errors import AuditChainError, AuditLogError, InputValidationError
from .validation import validate_json_shape

AUDIT_CHAIN_VERSION = 1
AUDIT_CHAIN_VERIFICATION_VERSION = 1
MIN_AUDIT_CHAIN_KEY_BYTES = 32
MAX_AUDIT_CHAIN_KEY_BYTES = 4_096
MAX_AUDIT_CHAIN_ENTRY_BYTES = 262_144
MAX_AUDIT_CHAIN_ENTRIES = 1_000_000
MAX_AUDIT_CHAIN_BYTES = 1_073_741_824

_ALGORITHM = "hmac-sha256"
_DOMAIN = b"samsarix-agent-ethics:audit-chain:v1\x00"
_STREAM_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_MAC = re.compile(r"^v1:hmac-sha256:[0-9a-f]{64}$")


class _DuplicateKeyError(ValueError):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise _DuplicateKeyError(f"duplicate JSON field {key!r}")
        value[key] = item
    return value


def _validated_key(key: bytes | bytearray | memoryview) -> bytes:
    if not isinstance(key, (bytes, bytearray, memoryview)):
        raise TypeError("key must be bytes-like")
    value = bytes(key)
    if not MIN_AUDIT_CHAIN_KEY_BYTES <= len(value) <= MAX_AUDIT_CHAIN_KEY_BYTES:
        raise ValueError(
            f"key must contain {MIN_AUDIT_CHAIN_KEY_BYTES}-{MAX_AUDIT_CHAIN_KEY_BYTES} bytes"
        )
    return value


def _validated_stream_id(stream_id: Any) -> str:
    if not isinstance(stream_id, str) or not _STREAM_ID.fullmatch(stream_id):
        raise ValueError("stream_id must be a 1-128 character identifier")
    return stream_id


def _validated_mac(value: Any, *, label: str, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not _MAC.fullmatch(value):
        raise ValueError(f"{label} must use the v1:hmac-sha256 lowercase format")
    return value


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise AuditChainError(
            f"audit chain entry cannot be canonically encoded: {type(exc).__name__}"
        ) from exc


def _entry_mac(key: bytes, unsigned: Mapping[str, Any]) -> str:
    digest = hmac.new(key, _DOMAIN + _canonical_bytes(unsigned), hashlib.sha256)
    return f"v{AUDIT_CHAIN_VERSION}:{_ALGORITHM}:{digest.hexdigest()}"


def _unsigned_fields(
    *,
    stream_id: str,
    sequence: int,
    previous_mac: str | None,
    record: AuditRecord,
) -> dict[str, Any]:
    return {
        "audit_chain_version": AUDIT_CHAIN_VERSION,
        "algorithm": _ALGORITHM,
        "stream_id": stream_id,
        "sequence": sequence,
        "previous_mac": previous_mac,
        "record": record.to_dict(),
    }


def _file_state(status: os.stat_result) -> tuple[int, int, int, int]:
    return (status.st_dev, status.st_ino, status.st_size, status.st_mtime_ns)


def generate_audit_chain_key() -> bytes:
    """Generate a new 256-bit key; the caller owns its secret storage and rotation."""

    return secrets.token_bytes(MIN_AUDIT_CHAIN_KEY_BYTES)


@dataclass(frozen=True, slots=True)
class AuditChainEntry:
    """One authenticated audit record and its position in a stream."""

    stream_id: str
    sequence: int
    previous_mac: str | None
    record: AuditRecord
    mac: str
    algorithm: str = _ALGORITHM
    audit_chain_version: int = AUDIT_CHAIN_VERSION

    def __post_init__(self) -> None:
        if (
            isinstance(self.audit_chain_version, bool)
            or self.audit_chain_version != AUDIT_CHAIN_VERSION
        ):
            raise ValueError(f"audit_chain_version must be {AUDIT_CHAIN_VERSION}")
        if self.algorithm != _ALGORITHM:
            raise ValueError(f"algorithm must be {_ALGORITHM}")
        _validated_stream_id(self.stream_id)
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or not 1 <= self.sequence <= MAX_AUDIT_CHAIN_ENTRIES
        ):
            raise ValueError(f"sequence must be an integer from 1 to {MAX_AUDIT_CHAIN_ENTRIES}")
        _validated_mac(self.previous_mac, label="previous_mac", optional=True)
        if self.sequence == 1 and self.previous_mac is not None:
            raise ValueError("the first audit chain entry must have previous_mac null")
        if self.sequence > 1 and self.previous_mac is None:
            raise ValueError("audit chain entries after the first require previous_mac")
        if not isinstance(self.record, AuditRecord):
            raise TypeError("record must be an AuditRecord")
        _validated_mac(self.mac, label="mac")

    @classmethod
    def from_dict(cls, value: Any) -> AuditChainEntry:
        """Parse an entry shape without yet trusting its cryptographic claims."""

        try:
            validate_json_shape(value, label="audit chain entry")
        except InputValidationError as exc:
            raise AuditChainError(str(exc)) from exc
        if not isinstance(value, Mapping):
            raise AuditChainError("audit chain entry must be a JSON object")
        required = {
            "audit_chain_version",
            "algorithm",
            "stream_id",
            "sequence",
            "previous_mac",
            "record",
            "mac",
        }
        missing = required - value.keys()
        extra = value.keys() - required
        if missing:
            raise AuditChainError(f"audit chain entry is missing: {', '.join(sorted(missing))}")
        if extra:
            raise AuditChainError(
                f"audit chain entry has unknown fields: {', '.join(sorted(extra))}"
            )
        try:
            record = AuditRecord.from_dict(value["record"])
            return cls(
                audit_chain_version=value["audit_chain_version"],
                algorithm=value["algorithm"],
                stream_id=value["stream_id"],
                sequence=value["sequence"],
                previous_mac=value["previous_mac"],
                record=record,
                mac=value["mac"],
            )
        except AuditLogError as exc:
            raise AuditChainError(f"invalid audit chain record: {exc}") from exc
        except (TypeError, ValueError) as exc:
            raise AuditChainError(f"invalid audit chain entry: {exc}") from exc

    def unsigned_dict(self) -> dict[str, Any]:
        """Return the canonical authenticated fields, excluding the MAC itself."""

        return _unsigned_fields(
            stream_id=self.stream_id,
            sequence=self.sequence,
            previous_mac=self.previous_mac,
            record=self.record,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a detached JSON-compatible entry."""

        return {**self.unsigned_dict(), "mac": self.mac}


@dataclass(frozen=True, slots=True)
class AuditChainVerification:
    """Successful verification summary suitable for an external checkpoint."""

    stream_id: str
    entry_count: int
    head_mac: str
    first_sequence: int = 1
    last_sequence: int = 1
    verified: bool = True
    audit_chain_verification_version: int = AUDIT_CHAIN_VERIFICATION_VERSION

    def __post_init__(self) -> None:
        if (
            isinstance(self.audit_chain_verification_version, bool)
            or self.audit_chain_verification_version != AUDIT_CHAIN_VERIFICATION_VERSION
        ):
            raise ValueError(
                f"audit_chain_verification_version must be {AUDIT_CHAIN_VERIFICATION_VERSION}"
            )
        _validated_stream_id(self.stream_id)
        if (
            isinstance(self.entry_count, bool)
            or not isinstance(self.entry_count, int)
            or not 1 <= self.entry_count <= MAX_AUDIT_CHAIN_ENTRIES
        ):
            raise ValueError(f"entry_count must be an integer from 1 to {MAX_AUDIT_CHAIN_ENTRIES}")
        if (
            isinstance(self.first_sequence, bool)
            or not isinstance(self.first_sequence, int)
            or isinstance(self.last_sequence, bool)
            or not isinstance(self.last_sequence, int)
            or self.first_sequence != 1
            or self.last_sequence != self.entry_count
        ):
            raise ValueError("verification sequence range must be 1 through entry_count")
        if self.verified is not True:
            raise ValueError("successful audit chain verification must set verified to true")
        _validated_mac(self.head_mac, label="head_mac")

    def to_dict(self) -> dict[str, Any]:
        """Return a detached JSON-compatible verification summary."""

        return {
            "audit_chain_verification_version": self.audit_chain_verification_version,
            "verified": self.verified,
            "stream_id": self.stream_id,
            "entry_count": self.entry_count,
            "first_sequence": self.first_sequence,
            "last_sequence": self.last_sequence,
            "head_mac": self.head_mac,
        }


def _load_entry(line: bytes, *, sequence: int, path: Path) -> AuditChainEntry:
    try:
        value = json.loads(line, object_pairs_hook=_reject_duplicate_keys)
    except (_DuplicateKeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise AuditChainError(
            f"invalid audit chain JSON at sequence {sequence} in {path}: {exc}"
        ) from exc
    return AuditChainEntry.from_dict(value)


def verify_audit_chain(
    path: str | Path,
    key: bytes | bytearray | memoryview,
    *,
    expected_head: str | None = None,
    expected_stream_id: str | None = None,
) -> AuditChainVerification:
    """Verify a non-empty chain and optionally bind it to an external checkpoint."""

    target = Path(path)
    try:
        secret = _validated_key(key)
    except (TypeError, ValueError) as exc:
        raise AuditChainError(str(exc)) from exc
    if expected_head is not None:
        try:
            _validated_mac(expected_head, label="expected_head")
        except ValueError as exc:
            raise AuditChainError(str(exc)) from exc
    if expected_stream_id is not None:
        try:
            _validated_stream_id(expected_stream_id)
        except ValueError as exc:
            raise AuditChainError(str(exc)) from exc

    previous_mac: str | None = None
    stream_id: str | None = None
    entry_count = 0
    bytes_read = 0
    try:
        source = target.open("rb")
    except OSError as exc:
        raise AuditChainError(f"cannot open audit chain {target}: {exc}") from exc
    try:
        with source:
            initial_status = os.fstat(source.fileno())
            if not stat.S_ISREG(initial_status.st_mode):
                raise AuditChainError(f"audit chain must be a regular file: {target}")
            initial_state = _file_state(initial_status)
            while True:
                line = source.readline(MAX_AUDIT_CHAIN_ENTRY_BYTES + 2)
                if not line:
                    break
                entry_count += 1
                bytes_read += len(line)
                if bytes_read > MAX_AUDIT_CHAIN_BYTES:
                    raise AuditChainError(
                        f"audit chain exceeds the limit of {MAX_AUDIT_CHAIN_BYTES} bytes"
                    )
                if entry_count > MAX_AUDIT_CHAIN_ENTRIES:
                    raise AuditChainError(
                        f"audit chain exceeds the limit of {MAX_AUDIT_CHAIN_ENTRIES} entries"
                    )
                if len(line) > MAX_AUDIT_CHAIN_ENTRY_BYTES:
                    raise AuditChainError(
                        f"audit chain entry {entry_count} exceeds the limit of "
                        f"{MAX_AUDIT_CHAIN_ENTRY_BYTES} bytes"
                    )
                if not line.endswith(b"\n"):
                    raise AuditChainError(
                        f"audit chain entry {entry_count} is incomplete (missing newline)"
                    )
                if line == b"\n" or line == b"\r\n":
                    raise AuditChainError(f"audit chain entry {entry_count} is blank")
                entry = _load_entry(line, sequence=entry_count, path=target)
                if entry.sequence != entry_count:
                    raise AuditChainError(
                        f"audit chain sequence mismatch at entry {entry_count}: "
                        f"found {entry.sequence}"
                    )
                if stream_id is None:
                    stream_id = entry.stream_id
                    if expected_stream_id is not None and stream_id != expected_stream_id:
                        raise AuditChainError(
                            f"audit chain stream_id {stream_id!r} does not match expected "
                            f"{expected_stream_id!r}"
                        )
                elif entry.stream_id != stream_id:
                    raise AuditChainError(
                        f"audit chain stream changed at entry {entry_count}: {entry.stream_id!r}"
                    )
                if entry.previous_mac != previous_mac:
                    raise AuditChainError(f"audit chain link mismatch at entry {entry_count}")
                calculated = _entry_mac(secret, entry.unsigned_dict())
                if not hmac.compare_digest(entry.mac, calculated):
                    raise AuditChainError(
                        f"audit chain MAC verification failed at entry {entry_count}"
                    )
                previous_mac = entry.mac
            final_state = _file_state(os.fstat(source.fileno()))
            if final_state != initial_state or bytes_read != initial_status.st_size:
                raise AuditChainError("audit chain changed while it was being verified")
        if _file_state(target.stat()) != final_state:
            raise AuditChainError("audit chain path changed while it was being verified")
    except OSError as exc:
        raise AuditChainError(f"cannot read audit chain {target}: {exc}") from exc

    if entry_count == 0 or stream_id is None or previous_mac is None:
        raise AuditChainError(f"audit chain is empty: {target}")
    if expected_head is not None and not hmac.compare_digest(previous_mac, expected_head):
        raise AuditChainError("audit chain head does not match the expected external checkpoint")
    return AuditChainVerification(
        stream_id=stream_id,
        entry_count=entry_count,
        first_sequence=1,
        last_sequence=entry_count,
        head_mac=previous_mac,
    )


class HmacAuditChainSink:
    """Append authenticated audit records for one single-writer stream."""

    def __init__(
        self,
        path: str | Path,
        key: bytes | bytearray | memoryview,
        *,
        stream_id: str,
        expected_head: str | None = None,
    ) -> None:
        self._path = Path(path)
        self._key = _validated_key(key)
        self._stream_id = _validated_stream_id(stream_id)
        self._lock = threading.Lock()
        self._entry_count = 0
        self._head_mac: str | None = None
        self._file_state: tuple[int, int, int, int] | None = None
        if expected_head is not None:
            try:
                _validated_mac(expected_head, label="expected_head")
            except ValueError as exc:
                raise AuditChainError(str(exc)) from exc
        self._resume(expected_head=expected_head)

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(path={str(self._path)!r}, "
            f"stream_id={self._stream_id!r}, entry_count={self._entry_count})"
        )

    @property
    def path(self) -> Path:
        """Return the configured output path."""

        return self._path

    @property
    def stream_id(self) -> str:
        """Return the authenticated stream identifier."""

        return self._stream_id

    @property
    def entry_count(self) -> int:
        """Return the count known to this sink instance."""

        with self._lock:
            return self._entry_count

    @property
    def head_mac(self) -> str | None:
        """Return the latest MAC, or ``None`` before the first append."""

        with self._lock:
            return self._head_mac

    def _stat(self) -> tuple[int, int, int, int] | None:
        try:
            status = self._path.stat()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise AuditChainError(f"cannot inspect audit chain {self._path}: {exc}") from exc
        return _file_state(status)

    def _resume(self, *, expected_head: str | None = None) -> None:
        state = self._stat()
        if state is None or state[2] == 0:
            if expected_head is not None:
                raise AuditChainError(
                    "audit chain is empty but an external head checkpoint was supplied"
                )
            self._entry_count = 0
            self._head_mac = None
            self._file_state = state
            return
        verification = verify_audit_chain(
            self._path,
            self._key,
            expected_head=expected_head,
            expected_stream_id=self._stream_id,
        )
        self._entry_count = verification.entry_count
        self._head_mac = verification.head_mac
        self._file_state = self._stat()

    def __call__(self, record: AuditRecord, /) -> None:
        if not isinstance(record, AuditRecord):
            raise TypeError("record must be an AuditRecord")
        with self._lock:
            if not self._path.parent.exists():
                raise AuditChainError(
                    f"audit-chain parent directory does not exist: {self._path.parent}"
                )
            current_state = self._stat()
            if current_state != self._file_state:
                raise AuditChainError(
                    "audit chain changed outside this sink; verify and create a new sink "
                    "before appending"
                )
            next_sequence = self._entry_count + 1
            if next_sequence > MAX_AUDIT_CHAIN_ENTRIES:
                raise AuditChainError(
                    f"audit chain exceeds the limit of {MAX_AUDIT_CHAIN_ENTRIES} entries"
                )
            unsigned = _unsigned_fields(
                stream_id=self._stream_id,
                sequence=next_sequence,
                previous_mac=self._head_mac,
                record=record,
            )
            entry = AuditChainEntry(
                stream_id=self._stream_id,
                sequence=next_sequence,
                previous_mac=self._head_mac,
                record=record,
                mac=_entry_mac(self._key, unsigned),
            )
            payload = _canonical_bytes(entry.to_dict()) + b"\n"
            if len(payload) > MAX_AUDIT_CHAIN_ENTRY_BYTES:
                raise AuditChainError(
                    f"audit chain entry exceeds the limit of {MAX_AUDIT_CHAIN_ENTRY_BYTES} bytes"
                )
            current_size = 0 if current_state is None else current_state[2]
            if current_size + len(payload) > MAX_AUDIT_CHAIN_BYTES:
                raise AuditChainError(
                    f"audit chain exceeds the limit of {MAX_AUDIT_CHAIN_BYTES} bytes"
                )
            flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
            if hasattr(os, "O_BINARY"):
                flags |= os.O_BINARY
            descriptor: int | None = None
            failure: OSError | None = None
            created = current_state is None
            try:
                descriptor = os.open(self._path, flags, 0o600)
                written = os.write(descriptor, payload)
                if written != len(payload):
                    raise OSError(f"short audit-chain write: {written} of {len(payload)} bytes")
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
            if failure is None and created and hasattr(os, "O_DIRECTORY"):
                directory_descriptor: int | None = None
                try:
                    directory_descriptor = os.open(
                        self._path.parent,
                        os.O_RDONLY | os.O_DIRECTORY,
                    )
                    os.fsync(directory_descriptor)
                except OSError as exc:
                    failure = exc
                finally:
                    if directory_descriptor is not None:
                        try:
                            os.close(directory_descriptor)
                        except OSError as exc:
                            if failure is None:
                                failure = exc
            if failure is not None:
                raise AuditChainError(
                    f"cannot append audit chain entry to {self._path}: {failure}"
                ) from failure
            self._entry_count = next_sequence
            self._head_mac = entry.mac
            self._file_state = self._stat()
