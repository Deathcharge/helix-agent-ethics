"""Input bounds, duplicate-key handling, and audit privacy tests."""

from __future__ import annotations

import io
import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import Any

import pytest

import samsarix_ethics.audit as audit_module
from samsarix_ethics import (
    AUDIT_RECORD_VERSION,
    AuditLogError,
    AuditRecord,
    InputValidationError,
    JsonlAuditSink,
    Outcome,
    Policy,
    PolicyEngine,
    PolicyValidationError,
)
from samsarix_ethics.io import (
    MAX_INPUT_BYTES,
    append_audit_record,
    load_context,
    load_policy,
    write_sample_policy,
)
from samsarix_ethics.validation import MAX_JSON_DEPTH, MAX_STRING_LENGTH


def test_duplicate_policy_key_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")

    with pytest.raises(PolicyValidationError, match="duplicate object key"):
        load_policy(path)


def test_oversized_standard_input_is_rejected() -> None:
    stream = io.BytesIO(b"{" + b'"x":"' + (b"a" * MAX_INPUT_BYTES) + b'"}')

    with pytest.raises(InputValidationError, match="byte limit"):
        load_context(None, stdin=stream)


def test_non_object_input_is_rejected() -> None:
    with pytest.raises(InputValidationError, match="JSON object"):
        load_context(None, stdin=io.BytesIO(b"[]"))


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"\xff", "must be UTF-8"),
        (b'{"value":NaN}', "non-finite number"),
        (
            json.dumps({"value": "x" * (MAX_STRING_LENGTH + 1)}).encode(),
            "string longer",
        ),
    ],
    ids=("invalid-utf8", "non-finite-number", "long-string"),
)
def test_invalid_json_encodings_and_values(payload: bytes, message: str) -> None:
    with pytest.raises(InputValidationError, match=message):
        load_context(None, stdin=io.BytesIO(payload))


def test_excessive_json_depth_is_rejected() -> None:
    value: dict[str, Any] = {}
    cursor = value
    for _ in range(MAX_JSON_DEPTH + 1):
        child: dict[str, Any] = {}
        cursor["child"] = child
        cursor = child

    with pytest.raises(InputValidationError, match="maximum JSON depth"):
        load_context(None, stdin=io.BytesIO(json.dumps(value).encode()))


def test_deeply_nested_json_becomes_an_input_error() -> None:
    payload = ("[" * 2_000 + "]" * 2_000).encode()

    with pytest.raises(InputValidationError, match=r"not valid JSON|maximum JSON depth"):
        load_context(None, stdin=io.BytesIO(b'{"value":' + payload + b"}"))


def test_context_file_and_missing_stdin(tmp_path: Path) -> None:
    path = tmp_path / "input.json"
    path.write_text('{"action":{"operation":"read"}}', encoding="utf-8")

    assert load_context(path)["action"]["operation"] == "read"
    with pytest.raises(InputValidationError, match="no stream"):
        load_context(None)


def test_file_read_remains_bounded_if_file_grows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "input.json"
    path.write_bytes(b"{}")
    original_open = Path.open

    def growing_open(file_path: Path, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if file_path == path and mode == "rb":
            return io.BytesIO(b"x" * (MAX_INPUT_BYTES + 1))
        return original_open(file_path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", growing_open)

    with pytest.raises(InputValidationError, match="byte limit"):
        load_context(path)


def test_missing_and_non_file_paths_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(PolicyValidationError, match="cannot read policy"):
        load_policy(tmp_path / "missing.json")
    with pytest.raises(PolicyValidationError, match="not a regular file"):
        load_policy(tmp_path)


def test_sample_policy_is_valid_and_overwrite_is_explicit(tmp_path: Path) -> None:
    path = tmp_path / "policy.json"
    resolved = write_sample_policy(path)

    assert resolved == path.resolve()
    assert load_policy(path).id == "safe-agent-actions"
    with pytest.raises(PolicyValidationError, match="refusing to overwrite"):
        write_sample_policy(path)
    assert write_sample_policy(path, force=True) == path.resolve()


def test_sample_policy_denies_destructive_actions_without_explicit_approval(tmp_path: Path) -> None:
    path = tmp_path / "policy.json"
    write_sample_policy(path)
    engine = PolicyEngine(load_policy(path))

    missing = engine.evaluate({"action": {"operation": "delete"}})
    false = engine.evaluate(
        {"action": {"operation": "delete"}, "context": {"human_approved": False}}
    )

    assert missing.outcome is Outcome.DENY
    assert false.outcome is Outcome.DENY


def test_sample_policy_requires_existing_parent(tmp_path: Path) -> None:
    with pytest.raises(PolicyValidationError, match="parent directory"):
        write_sample_policy(tmp_path / "missing" / "policy.json")


def test_audit_record_excludes_raw_input(tmp_path: Path, policy_document: dict[str, Any]) -> None:
    decision = PolicyEngine(Policy.from_dict(policy_document)).evaluate(
        {"action": {"operation": "read"}, "secret": "do-not-log"}
    )
    audit_path = tmp_path / "audit.jsonl"

    append_audit_record(audit_path, decision)
    record = json.loads(audit_path.read_text(encoding="utf-8"))

    assert record["outcome"] == "allow"
    assert record["audit_record_version"] == AUDIT_RECORD_VERSION
    assert record["decision_id"] == decision.decision_id
    assert record["policy_fingerprint"] == decision.policy_fingerprint
    assert "secret" not in record
    assert "do-not-log" not in audit_path.read_text(encoding="utf-8")


def test_audit_record_is_frozen_versioned_and_detached(
    policy_document: dict[str, Any],
) -> None:
    decision = PolicyEngine(Policy.from_dict(policy_document)).evaluate(
        {"action": {"operation": "read"}, "secret": "do-not-log"}
    )
    record = AuditRecord.from_decision(decision)

    assert record.audit_record_version == 1
    assert record.outcome == "allow"
    assert record.matched_rules == decision.matched_rules
    assert record.warning_count == len(decision.warnings)
    assert record.policy_fingerprint == decision.policy_fingerprint
    with pytest.raises(FrozenInstanceError):
        record.outcome = "deny"  # type: ignore[misc]

    exported = record.to_dict()
    exported["matched_rules"].append("changed")
    assert "changed" not in record.matched_rules
    assert "secret" not in exported
    assert "do-not-log" not in json.dumps(exported)


def test_audit_record_and_jsonl_sink_reject_invalid_objects(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="Decision"):
        AuditRecord.from_decision(object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="audit_record_version"):
        AuditRecord("id", "time", "policy", "1", "bad", "allow", (), 0, 2)
    with pytest.raises(TypeError, match="AuditRecord"):
        JsonlAuditSink(tmp_path / "audit.jsonl")(object())  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("audit_record_version", True, "audit_record_version"),
        ("decision_id", "not-a-uuid", "decision_id"),
        ("evaluated_at", "not-a-time", "evaluated_at"),
        ("evaluated_at", "20260801T120000+00:00", "RFC 3339"),
        ("evaluated_at", "2026-08-01T12:00:00", "RFC 3339"),
        ("evaluated_at", "2026-08-01T12:00:00+99:99", "valid RFC 3339"),
        ("policy_id", "bad policy", "policy_id"),
        ("policy_version", "", "policy_version"),
        ("policy_fingerprint", "sha256:bad", "policy_fingerprint"),
        ("outcome", "warn", "outcome"),
        ("matched_rules", ["allow-read"], "tuple"),
        ("matched_rules", ("allow-read", "allow-read"), "duplicates"),
        ("matched_rules", ("bad rule",), "identifiers"),
        ("matched_rules", tuple(f"rule-{index}" for index in range(1_001)), "limit"),
        ("warning_count", True, "warning_count"),
        ("warning_count", 1_001, "warning_count"),
    ],
)
def test_audit_record_rejects_invalid_public_fields(
    policy_document: dict[str, Any], field: str, value: Any, message: str
) -> None:
    decision = PolicyEngine(Policy.from_dict(policy_document)).evaluate(
        {"action": {"operation": "read"}}
    )
    record = AuditRecord.from_decision(decision)

    with pytest.raises((TypeError, ValueError), match=message):
        replace(record, **{field: value})


def test_jsonl_audit_sink_exposes_path_and_writes_record(
    tmp_path: Path, policy_document: dict[str, Any]
) -> None:
    path = tmp_path / "audit.jsonl"
    sink = JsonlAuditSink(path)
    decision = PolicyEngine(Policy.from_dict(policy_document)).evaluate(
        {"action": {"operation": "read"}}
    )

    sink(AuditRecord.from_decision(decision))

    assert sink.path == path
    assert json.loads(path.read_text(encoding="utf-8"))["decision_id"] == decision.decision_id


@pytest.mark.parametrize("failure", ["open", "short-write", "close"])
def test_jsonl_audit_sink_wraps_write_failures(
    tmp_path: Path,
    policy_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    decision = PolicyEngine(Policy.from_dict(policy_document)).evaluate(
        {"action": {"operation": "read"}}
    )
    sink = JsonlAuditSink(tmp_path / "audit.jsonl")

    if failure == "open":

        def fail_open(*_args: Any, **_kwargs: Any) -> int:
            raise OSError("private filesystem details")

        monkeypatch.setattr(audit_module.os, "open", fail_open)  # type: ignore[attr-defined]
    elif failure == "short-write":
        monkeypatch.setattr(
            audit_module.os,  # type: ignore[attr-defined]
            "write",
            lambda *_: 0,
        )
    else:
        real_close = audit_module.os.close  # type: ignore[attr-defined]

        def fail_close(descriptor: int) -> None:
            real_close(descriptor)
            raise OSError("private close details")

        monkeypatch.setattr(audit_module.os, "close", fail_close)  # type: ignore[attr-defined]

    with pytest.raises(AuditLogError, match="cannot append audit record"):
        sink(AuditRecord.from_decision(decision))


def test_audit_log_requires_existing_parent(
    tmp_path: Path, policy_document: dict[str, Any]
) -> None:
    decision = PolicyEngine(Policy.from_dict(policy_document)).evaluate(
        {"action": {"operation": "read"}}
    )

    with pytest.raises(AuditLogError, match="parent directory"):
        append_audit_record(tmp_path / "missing" / "audit.jsonl", decision)
