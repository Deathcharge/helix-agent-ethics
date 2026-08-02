# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator, ValidationError  # type: ignore[import-untyped]

import samsarix_ethics.audit_chain as audit_chain_module
from samsarix_ethics import (
    AUDIT_CHAIN_VERIFICATION_VERSION,
    AUDIT_CHAIN_VERSION,
    MAX_AUDIT_CHAIN_BYTES,
    MAX_AUDIT_CHAIN_ENTRIES,
    MAX_AUDIT_CHAIN_ENTRY_BYTES,
    MAX_AUDIT_CHAIN_KEY_BYTES,
    MIN_AUDIT_CHAIN_KEY_BYTES,
    AuditChainEntry,
    AuditChainError,
    AuditChainVerification,
    AuditLogError,
    AuditRecord,
    HmacAuditChainSink,
    Policy,
    ToolGate,
    generate_audit_chain_key,
    get_audit_chain_entry_schema,
    get_audit_chain_verification_schema,
    verify_audit_chain,
)
from samsarix_ethics.cli import EXIT_ALLOWED, EXIT_ERROR, main


def _record(index: int = 1) -> AuditRecord:
    return AuditRecord(
        decision_id=f"00000000-0000-4000-8000-{index:012x}",
        evaluated_at="2026-08-01T12:00:00+00:00",
        policy_id="production-agent",
        policy_version="1.4.0",
        policy_fingerprint=f"v1:sha256:{'a' * 64}",
        outcome="allow" if index % 2 else "deny",
        matched_rules=(f"rule-{index}",),
        warning_count=index % 3,
    )


def _write_chain(path: Path, key: bytes, *, count: int = 3) -> HmacAuditChainSink:
    sink = HmacAuditChainSink(path, key, stream_id="production-us-east-1")
    for index in range(1, count + 1):
        sink(_record(index))
    return sink


def _read_lines(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _write_lines(path: Path, lines: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(line, separators=(",", ":"), sort_keys=True) + "\n" for line in lines),
        encoding="utf-8",
    )


def test_append_verify_resume_and_checkpoint(tmp_path: Path) -> None:
    path = tmp_path / "audit-chain.jsonl"
    key = generate_audit_chain_key()
    assert len(key) == MIN_AUDIT_CHAIN_KEY_BYTES

    sink = _write_chain(path, key)
    assert sink.entry_count == 3
    assert sink.head_mac is not None
    checkpoint = sink.head_mac

    verification = verify_audit_chain(
        path,
        key,
        expected_head=checkpoint,
        expected_stream_id="production-us-east-1",
    )
    assert verification == AuditChainVerification(
        stream_id="production-us-east-1",
        entry_count=3,
        first_sequence=1,
        last_sequence=3,
        head_mac=checkpoint,
    )
    assert verification.audit_chain_verification_version == AUDIT_CHAIN_VERIFICATION_VERSION == 1
    assert verification.to_dict()["verified"] is True

    resumed = HmacAuditChainSink(
        path,
        key,
        stream_id="production-us-east-1",
        expected_head=checkpoint,
    )
    resumed(_record(4))
    assert resumed.entry_count == 4
    assert verify_audit_chain(path, key).head_mac == resumed.head_mac


def test_format_has_a_pinned_canonical_mac_vector(tmp_path: Path) -> None:
    path = tmp_path / "audit-chain.jsonl"
    sink = _write_chain(path, b"k" * MIN_AUDIT_CHAIN_KEY_BYTES, count=1)
    assert (
        sink.head_mac
        == "v1:hmac-sha256:a0fd633c430b222fb460307e95865bb2b542e4596a79918e2955b87cd08202e0"
    )


def test_entry_round_trip_is_immutable_and_metadata_only(tmp_path: Path) -> None:
    path = tmp_path / "audit-chain.jsonl"
    key = b"k" * MIN_AUDIT_CHAIN_KEY_BYTES
    sink = _write_chain(path, key, count=1)
    persisted = _read_lines(path)[0]
    entry = AuditChainEntry.from_dict(persisted)

    assert entry.audit_chain_version == AUDIT_CHAIN_VERSION == 1
    assert entry.to_dict() == persisted
    assert "arguments" not in path.read_text(encoding="utf-8")
    assert entry.previous_mac is None
    with pytest.raises((AttributeError, TypeError)):
        entry.sequence = 2  # type: ignore[misc]
    assert sink.path == path
    assert sink.stream_id == "production-us-east-1"


def test_audit_record_strict_round_trip_and_rejections() -> None:
    record = _record()
    assert AuditRecord.from_dict(record.to_dict()) == record

    unknown = record.to_dict()
    unknown["input"] = {"secret": True}
    with pytest.raises(AuditLogError, match="unknown fields: input"):
        AuditRecord.from_dict(unknown)

    invalid_rules = record.to_dict()
    invalid_rules["matched_rules"] = "rule-1"
    with pytest.raises(AuditLogError, match="must be a JSON array"):
        AuditRecord.from_dict(invalid_rules)


@pytest.mark.parametrize("mutation", ["record", "mac", "previous_mac", "stream_id"])
def test_mutation_is_detected(tmp_path: Path, mutation: str) -> None:
    path = tmp_path / "audit-chain.jsonl"
    key = b"m" * MIN_AUDIT_CHAIN_KEY_BYTES
    _write_chain(path, key)
    lines = _read_lines(path)
    target = lines[1]
    if mutation == "record":
        record = target["record"]
        assert isinstance(record, dict)
        record["outcome"] = "review"
    elif mutation == "mac":
        target["mac"] = f"v1:hmac-sha256:{'0' * 64}"
    elif mutation == "previous_mac":
        target["previous_mac"] = f"v1:hmac-sha256:{'1' * 64}"
    else:
        target["stream_id"] = "other-stream"
    _write_lines(path, lines)

    with pytest.raises(AuditChainError):
        verify_audit_chain(path, key)


def test_reordering_and_middle_deletion_are_detected(tmp_path: Path) -> None:
    path = tmp_path / "audit-chain.jsonl"
    key = b"r" * MIN_AUDIT_CHAIN_KEY_BYTES
    _write_chain(path, key)
    lines = _read_lines(path)

    _write_lines(path, [lines[1], lines[0], lines[2]])
    with pytest.raises(AuditChainError, match=r"sequence mismatch|previous_mac"):
        verify_audit_chain(path, key)

    _write_lines(path, [lines[0], lines[2]])
    with pytest.raises(AuditChainError, match=r"sequence mismatch|link mismatch"):
        verify_audit_chain(path, key)


def test_external_checkpoint_detects_valid_prefix_rollback(tmp_path: Path) -> None:
    path = tmp_path / "audit-chain.jsonl"
    key = b"p" * MIN_AUDIT_CHAIN_KEY_BYTES
    sink = _write_chain(path, key)
    final_head = sink.head_mac
    assert final_head is not None
    lines = _read_lines(path)
    _write_lines(path, lines[:2])

    prefix = verify_audit_chain(path, key)
    assert prefix.entry_count == 2
    with pytest.raises(AuditChainError, match="external checkpoint"):
        verify_audit_chain(path, key, expected_head=final_head)
    with pytest.raises(AuditChainError, match="external checkpoint"):
        HmacAuditChainSink(
            path,
            key,
            stream_id="production-us-east-1",
            expected_head=final_head,
        )


def test_wrong_key_stream_and_invalid_key_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "audit-chain.jsonl"
    key = b"a" * MIN_AUDIT_CHAIN_KEY_BYTES
    _write_chain(path, key, count=1)

    with pytest.raises(AuditChainError, match="MAC verification failed"):
        verify_audit_chain(path, b"b" * MIN_AUDIT_CHAIN_KEY_BYTES)
    with pytest.raises(AuditChainError, match="does not match expected"):
        verify_audit_chain(path, key, expected_stream_id="other-stream")
    with pytest.raises(AuditChainError, match="32-4096"):
        verify_audit_chain(path, b"short")
    with pytest.raises(AuditChainError, match="bytes-like"):
        verify_audit_chain(path, "not-secret-bytes")  # type: ignore[arg-type]
    with pytest.raises(AuditChainError, match="expected_head"):
        verify_audit_chain(path, key, expected_head="not-a-mac")
    with pytest.raises(AuditChainError, match="stream_id"):
        verify_audit_chain(path, key, expected_stream_id="")
    with pytest.raises(ValueError, match="32-4096"):
        HmacAuditChainSink(path, b"short", stream_id="stream")
    with pytest.raises(TypeError, match="bytes-like"):
        HmacAuditChainSink(path, "not-secret-bytes", stream_id="stream")  # type: ignore[arg-type]


def test_entry_and_verification_models_reject_invalid_shapes(tmp_path: Path) -> None:
    path = tmp_path / "audit-chain.jsonl"
    key = b"v" * MIN_AUDIT_CHAIN_KEY_BYTES
    _write_chain(path, key, count=1)
    valid = _read_lines(path)[0]

    invalid_values: list[object] = [[], {"unexpected": object()}]
    for value in invalid_values:
        with pytest.raises(AuditChainError):
            AuditChainEntry.from_dict(value)

    missing = dict(valid)
    del missing["mac"]
    with pytest.raises(AuditChainError, match="is missing: mac"):
        AuditChainEntry.from_dict(missing)

    extra = dict(valid)
    extra["extra"] = True
    with pytest.raises(AuditChainError, match="unknown fields: extra"):
        AuditChainEntry.from_dict(extra)

    mutations: list[tuple[str, object]] = [
        ("audit_chain_version", True),
        ("algorithm", "sha256"),
        ("stream_id", ""),
        ("sequence", True),
        ("mac", "invalid"),
        ("record", "invalid"),
    ]
    for field, value in mutations:
        changed = dict(valid)
        changed[field] = value
        with pytest.raises(AuditChainError):
            AuditChainEntry.from_dict(changed)

    first_with_link = dict(valid)
    first_with_link["previous_mac"] = valid["mac"]
    with pytest.raises(AuditChainError, match="first audit chain entry"):
        AuditChainEntry.from_dict(first_with_link)

    later_without_link = dict(valid)
    later_without_link["sequence"] = 2
    with pytest.raises(AuditChainError, match="after the first"):
        AuditChainEntry.from_dict(later_without_link)

    head = valid["mac"]
    assert isinstance(head, str)
    invalid_reports = [
        {"audit_chain_verification_version": 2},
        {"entry_count": 0},
        {"first_sequence": True},
        {"last_sequence": 2},
        {"verified": False},
        {"head_mac": "invalid"},
        {"stream_id": ""},
    ]
    for replacement in invalid_reports:
        values: dict[str, object] = {
            "stream_id": "stream",
            "entry_count": 1,
            "head_mac": head,
            "first_sequence": 1,
            "last_sequence": 1,
            "verified": True,
            "audit_chain_verification_version": 1,
        }
        values.update(replacement)
        with pytest.raises(ValueError):
            AuditChainVerification(**values)  # type: ignore[arg-type]


def test_constructor_and_sink_boundary_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = b"f" * MIN_AUDIT_CHAIN_KEY_BYTES
    path = tmp_path / "audit-chain.jsonl"
    with pytest.raises(ValueError, match="stream_id"):
        HmacAuditChainSink(path, key, stream_id="")
    with pytest.raises(AuditChainError, match="expected_head"):
        HmacAuditChainSink(path, key, stream_id="stream", expected_head="invalid")

    sink = HmacAuditChainSink(path, key, stream_id="stream")
    with pytest.raises(TypeError, match="AuditRecord"):
        sink(object())  # type: ignore[arg-type]

    missing_parent = HmacAuditChainSink(tmp_path / "missing" / "chain.jsonl", key, stream_id="x")
    with pytest.raises(AuditChainError, match="parent directory"):
        missing_parent(_record())

    monkeypatch.setattr(audit_chain_module, "MAX_AUDIT_CHAIN_ENTRIES", 0)
    with pytest.raises(AuditChainError, match="exceeds the limit"):
        sink(_record())


def test_chain_sink_failure_prevents_tool_callback(tmp_path: Path) -> None:
    sink = HmacAuditChainSink(
        tmp_path / "missing" / "audit-chain.jsonl",
        b"g" * MIN_AUDIT_CHAIN_KEY_BYTES,
        stream_id="gate",
    )
    policy = Policy.from_dict(
        {
            "schema_version": 1,
            "id": "audit-chain-gate",
            "version": "1",
            "default_effect": "allow",
            "rules": [],
        }
    )
    callbacks: list[str] = []
    bound = ToolGate(policy, audit_sink=sink).bind("read_file", capabilities=["workspace:read"])

    with pytest.raises(AuditChainError, match="parent directory"):
        bound.execute({}, lambda _arguments: callbacks.append("executed"))
    assert callbacks == []


def test_encoding_and_write_failures_are_explicit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(AuditChainError, match="canonically encoded"):
        audit_chain_module._canonical_bytes({"invalid": float("nan")})

    key = b"w" * MIN_AUDIT_CHAIN_KEY_BYTES
    path = tmp_path / "short-write.jsonl"
    sink = HmacAuditChainSink(path, key, stream_id="stream")
    monkeypatch.setattr(audit_chain_module.os, "write", lambda _descriptor, _payload: 0)
    with pytest.raises(AuditChainError, match="short audit-chain write"):
        sink(_record())


def test_read_and_stat_failures_are_explicit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = b"o" * MIN_AUDIT_CHAIN_KEY_BYTES
    path = tmp_path / "audit-chain.jsonl"
    _write_chain(path, key, count=1)
    original_open = Path.open

    class BrokenReader:
        def __init__(self) -> None:
            self._source = original_open(path, "rb")

        def __enter__(self) -> BrokenReader:
            return self

        def __exit__(self, *_args: object) -> None:
            self._source.close()

        def fileno(self) -> int:
            return self._source.fileno()

        def readline(self, _limit: int) -> bytes:
            raise OSError("simulated read failure")

    def broken_open(target: Path, *args: object, **kwargs: object) -> object:
        if target == path:
            return BrokenReader()
        return original_open(target, *args, **kwargs)

    monkeypatch.setattr(Path, "open", broken_open)
    with pytest.raises(AuditChainError, match="cannot read audit chain"):
        verify_audit_chain(path, key)
    monkeypatch.setattr(Path, "open", original_open)

    original_stat = Path.stat

    def broken_stat(target: Path, *args: object, **kwargs: object) -> object:
        if target == path:
            raise OSError("simulated stat failure")
        return original_stat(target, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", broken_stat)
    with pytest.raises(AuditChainError, match="cannot inspect audit chain"):
        HmacAuditChainSink(path, key, stream_id="stream")


def test_verifier_rejects_a_file_that_changes_during_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = b"c" * MIN_AUDIT_CHAIN_KEY_BYTES
    path = tmp_path / "changing.jsonl"
    _write_chain(path, key, count=1)
    original_fstat = audit_chain_module.os.fstat
    calls = 0

    def changing_fstat(descriptor: int) -> object:
        nonlocal calls
        status = original_fstat(descriptor)
        calls += 1
        if calls == 2:
            return SimpleNamespace(
                st_dev=status.st_dev,
                st_ino=status.st_ino,
                st_size=status.st_size + 1,
                st_mtime_ns=status.st_mtime_ns + 1,
            )
        return status

    monkeypatch.setattr(audit_chain_module.os, "fstat", changing_fstat)
    with pytest.raises(AuditChainError, match="changed while it was being verified"):
        verify_audit_chain(path, key)


def test_new_chain_syncs_parent_directory_when_supported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[tuple[object, int]] = []
    synced: list[int] = []
    closed: list[int] = []

    def fake_open(path: object, flags: int, _mode: int = 0o777) -> int:
        opened.append((path, flags))
        return 101 if len(opened) == 1 else 202

    monkeypatch.setattr(audit_chain_module.os, "O_DIRECTORY", 0x10000, raising=False)
    monkeypatch.setattr(audit_chain_module.os, "open", fake_open)
    monkeypatch.setattr(
        audit_chain_module.os,
        "write",
        lambda _descriptor, payload: len(payload),
    )
    monkeypatch.setattr(audit_chain_module.os, "fsync", synced.append)
    monkeypatch.setattr(audit_chain_module.os, "close", closed.append)
    path = tmp_path / "new-chain.jsonl"
    HmacAuditChainSink(
        path,
        b"d" * MIN_AUDIT_CHAIN_KEY_BYTES,
        stream_id="directory-sync",
    )(_record())

    assert opened[0][0] == path
    assert opened[1][0] == path.parent
    assert synced == [101, 202]
    assert closed == [101, 202]


@pytest.mark.parametrize("failure_point", ["fsync", "close"])
def test_parent_directory_sync_failures_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
) -> None:
    opened = 0

    def fake_open(_path: object, _flags: int, _mode: int = 0o777) -> int:
        nonlocal opened
        opened += 1
        return 101 if opened == 1 else 202

    def fake_fsync(descriptor: int) -> None:
        if descriptor == 202 and failure_point == "fsync":
            raise OSError("simulated directory fsync failure")

    def fake_close(descriptor: int) -> None:
        if descriptor == 202 and failure_point == "close":
            raise OSError("simulated directory close failure")

    monkeypatch.setattr(audit_chain_module.os, "O_DIRECTORY", 0x10000, raising=False)
    monkeypatch.setattr(audit_chain_module.os, "open", fake_open)
    monkeypatch.setattr(
        audit_chain_module.os,
        "write",
        lambda _descriptor, payload: len(payload),
    )
    monkeypatch.setattr(audit_chain_module.os, "fsync", fake_fsync)
    monkeypatch.setattr(audit_chain_module.os, "close", fake_close)
    sink = HmacAuditChainSink(
        tmp_path / f"directory-{failure_point}.jsonl",
        b"e" * MIN_AUDIT_CHAIN_KEY_BYTES,
        stream_id="directory-failure",
    )

    with pytest.raises(AuditChainError, match=f"directory {failure_point} failure"):
        sink(_record())


def test_sink_copies_mutable_key_and_repr_excludes_it(tmp_path: Path) -> None:
    path = tmp_path / "audit-chain.jsonl"
    mutable_key = bytearray(b"q" * MIN_AUDIT_CHAIN_KEY_BYTES)
    original = bytes(mutable_key)
    sink = HmacAuditChainSink(path, mutable_key, stream_id="stream")
    mutable_key[:] = b"x" * len(mutable_key)
    sink(_record())

    assert verify_audit_chain(path, original).entry_count == 1
    assert original.hex() not in repr(sink)
    assert "qqqq" not in repr(sink)


def test_sink_serializes_threads_and_rejects_observed_external_change(tmp_path: Path) -> None:
    path = tmp_path / "audit-chain.jsonl"
    key = b"t" * MIN_AUDIT_CHAIN_KEY_BYTES
    sink = HmacAuditChainSink(path, key, stream_id="threaded")
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(sink, (_record(index) for index in range(1, 33))))
    assert verify_audit_chain(path, key).entry_count == 32

    competing_sink = HmacAuditChainSink(path, key, stream_id="threaded")
    competing_sink(_record(33))
    with pytest.raises(AuditChainError, match="changed outside this sink"):
        sink(_record(34))


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"\n", "blank"),
        (b'{"audit_chain_version":1}\n', "audit chain entry is missing"),
        (b'{"mac":"one","mac":"two"}\n', "duplicate JSON field"),
        (b"not-json\n", "invalid audit chain JSON"),
        (b"\xff\n", "invalid audit chain JSON"),
        (b'{"audit_chain_version":1}', "incomplete"),
    ],
)
def test_malformed_streams_are_rejected(tmp_path: Path, payload: bytes, message: str) -> None:
    path = tmp_path / "malformed.jsonl"
    path.write_bytes(payload)
    with pytest.raises(AuditChainError, match=message):
        verify_audit_chain(path, b"z" * MIN_AUDIT_CHAIN_KEY_BYTES)


def test_empty_missing_oversized_and_bounded_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = b"z" * MIN_AUDIT_CHAIN_KEY_BYTES
    empty = tmp_path / "empty.jsonl"
    empty.write_bytes(b"")
    with pytest.raises(AuditChainError, match="is empty"):
        verify_audit_chain(empty, key)
    with pytest.raises(AuditChainError, match="cannot open"):
        verify_audit_chain(tmp_path / "missing.jsonl", key)
    with pytest.raises(AuditChainError, match="empty but an external head"):
        HmacAuditChainSink(
            empty,
            key,
            stream_id="stream",
            expected_head=f"v1:hmac-sha256:{'0' * 64}",
        )

    oversized = tmp_path / "oversized.jsonl"
    oversized.write_bytes(b"x" * 34 + b"\n")
    monkeypatch.setattr(audit_chain_module, "MAX_AUDIT_CHAIN_ENTRY_BYTES", 32)
    with pytest.raises(AuditChainError, match="exceeds the limit"):
        verify_audit_chain(oversized, key)

    assert MAX_AUDIT_CHAIN_ENTRY_BYTES == 262_144
    assert MAX_AUDIT_CHAIN_ENTRIES == 1_000_000
    assert MAX_AUDIT_CHAIN_BYTES == 1_073_741_824
    assert MAX_AUDIT_CHAIN_KEY_BYTES == 4_096


def test_total_chain_byte_limit_applies_to_read_and_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = b"b" * MIN_AUDIT_CHAIN_KEY_BYTES
    existing = tmp_path / "existing.jsonl"
    _write_chain(existing, key, count=1)
    monkeypatch.setattr(audit_chain_module, "MAX_AUDIT_CHAIN_BYTES", 1)
    with pytest.raises(AuditChainError, match="exceeds the limit of 1 bytes"):
        verify_audit_chain(existing, key)

    fresh = HmacAuditChainSink(tmp_path / "fresh.jsonl", key, stream_id="fresh")
    with pytest.raises(AuditChainError, match="exceeds the limit of 1 bytes"):
        fresh(_record())


def test_schema_matches_runtime_objects_and_returns_fresh_values(tmp_path: Path) -> None:
    path = tmp_path / "audit-chain.jsonl"
    key = b"s" * MIN_AUDIT_CHAIN_KEY_BYTES
    _write_chain(path, key, count=1)
    entry = _read_lines(path)[0]
    verification = verify_audit_chain(path, key).to_dict()

    entry_schema = get_audit_chain_entry_schema()
    verification_schema = get_audit_chain_verification_schema()
    Draft202012Validator.check_schema(entry_schema)
    Draft202012Validator.check_schema(verification_schema)
    Draft202012Validator(entry_schema).validate(entry)
    Draft202012Validator(verification_schema).validate(verification)

    invalid_entry = dict(entry)
    invalid_entry["raw_input"] = {"private": True}
    with pytest.raises(ValidationError):
        Draft202012Validator(entry_schema).validate(invalid_entry)
    entry_schema["title"] = "changed"
    assert get_audit_chain_entry_schema()["title"] != "changed"


def test_cli_verifies_chain_and_never_outputs_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "audit-chain.jsonl"
    key_path = tmp_path / "audit.key"
    key = b"cli-secret-material-is-not-output!"
    assert len(key) >= MIN_AUDIT_CHAIN_KEY_BYTES
    key_path.write_bytes(key)
    sink = _write_chain(path, key, count=2)
    head = sink.head_mac
    assert head is not None

    exit_code = main(
        [
            "audit-chain",
            "verify",
            str(path),
            "--key-file",
            str(key_path),
            "--expected-head",
            head,
            "--stream-id",
            "production-us-east-1",
            "--format",
            "json",
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == EXIT_ALLOWED
    assert json.loads(captured.out)["head_mac"] == head
    assert key.decode("ascii") not in captured.out
    assert captured.err == ""

    exit_code = main(
        ["audit-chain", "verify", str(path), "--key-file", str(tmp_path / "missing.key")]
    )
    captured = capsys.readouterr()
    assert exit_code == EXIT_ERROR
    assert captured.out == ""
    assert "cannot read audit-chain key file" in captured.err


def test_cli_exports_both_schemas(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["schema", "audit-chain-entry"]) == EXIT_ALLOWED
    assert json.loads(capsys.readouterr().out)["properties"]["mac"]
    assert main(["schema", "audit-chain-verification"]) == EXIT_ALLOWED
    assert json.loads(capsys.readouterr().out)["properties"]["head_mac"]
