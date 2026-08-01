"""Bound tool-call approval and fingerprint behavior."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from typing import Any

import pytest

from samsarix_ethics import (
    MAX_TOOL_CALL_FINGERPRINT_BYTES,
    TOOL_CALL_APPROVAL_VERSION,
    TOOL_CALL_FINGERPRINT_VERSION,
    InputValidationError,
    ToolCallApproval,
    fingerprint_tool_call,
)


def test_tool_call_fingerprint_is_deterministic_after_normalization() -> None:
    first = fingerprint_tool_call(
        "call-1",
        "send_email",
        {"subject": "Update", "to": "person@example.com"},
        capabilities=["data:sensitive", "external:write"],
        actor={"tenant": "acme", "id": "agent-1"},
    )
    second = fingerprint_tool_call(
        "call-1",
        "send_email",
        {"to": "person@example.com", "subject": "Update"},
        capabilities=["external:write", "data:sensitive"],
        actor={"id": "agent-1", "tenant": "acme"},
    )

    assert first == second
    assert first.startswith("v1:sha256:")
    assert len(first) == 74
    assert TOOL_CALL_FINGERPRINT_VERSION == 1


def test_tool_call_fingerprint_binds_every_consequential_call_field() -> None:
    base = fingerprint_tool_call(
        "call-1",
        "send_email",
        {"to": "person@example.com"},
        capabilities=["external:write"],
        actor={"id": "agent-1"},
    )

    changed = {
        fingerprint_tool_call(
            "call-2",
            "send_email",
            {"to": "person@example.com"},
            capabilities=["external:write"],
            actor={"id": "agent-1"},
        ),
        fingerprint_tool_call(
            "call-1",
            "delete_email",
            {"to": "person@example.com"},
            capabilities=["external:write"],
            actor={"id": "agent-1"},
        ),
        fingerprint_tool_call(
            "call-1",
            "send_email",
            {"to": "attacker@example.com"},
            capabilities=["external:write"],
            actor={"id": "agent-1"},
        ),
        fingerprint_tool_call(
            "call-1",
            "send_email",
            {"to": "person@example.com"},
            capabilities=["external:write", "data:sensitive"],
            actor={"id": "agent-1"},
        ),
        fingerprint_tool_call(
            "call-1",
            "send_email",
            {"to": "person@example.com"},
            capabilities=["external:write"],
            actor={"id": "agent-2"},
        ),
    }

    assert base not in changed
    assert len(changed) == 5


def test_tool_call_fingerprint_is_bounded_and_wraps_canonicalization_errors() -> None:
    oversized = {f"field-{index}": "x" * 65_536 for index in range(17)}
    with pytest.raises(InputValidationError, match=str(MAX_TOOL_CALL_FINGERPRINT_BYTES)):
        fingerprint_tool_call("call-1", "tool", oversized)
    with pytest.raises(InputValidationError, match="cannot be fingerprinted: ValueError"):
        fingerprint_tool_call("call-1", "tool", {"integer": 10**5_000})


def test_tool_call_fingerprint_rejects_an_invalid_call_id() -> None:
    with pytest.raises(InputValidationError, match="tool call ID"):
        fingerprint_tool_call("bad call id", "tool", {})


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (("bad call", True, "v1:sha256:" + "0" * 64, 1), "tool_call_id"),
        (("call-1", 1, "v1:sha256:" + "0" * 64, 1), "approved"),
        (("call-1", True, "sha256:" + "0" * 64, 1), "fingerprint"),
        (("call-1", True, "v1:sha256:" + "0" * 64, True), "approval_version"),
    ],
)
def test_tool_call_approval_rejects_invalid_public_construction(
    arguments: tuple[Any, ...], message: str
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        ToolCallApproval(*arguments)


def test_tool_call_approval_is_frozen_and_round_trips_strict_json() -> None:
    source = {
        "approval_version": 1,
        "tool_call_id": "call-1",
        "approved": True,
        "tool_call_fingerprint": "v1:sha256:" + "a" * 64,
    }
    approval = ToolCallApproval.from_dict(source)

    assert approval.to_dict() == source
    assert approval.approval_version == TOOL_CALL_APPROVAL_VERSION == 1
    assert ToolCallApproval.from_dict(approval.to_dict()) == approval
    with pytest.raises(FrozenInstanceError):
        approval.approved = False  # type: ignore[misc]
    with pytest.raises(ValueError, match="approval_version"):
        replace(approval, approval_version=2)


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ([], "JSON object"),
        (
            {
                "approval_version": 1,
                "tool_call_id": "call-1",
                "approved": True,
            },
            "missing: tool_call_fingerprint",
        ),
        (
            {
                "approval_version": 1,
                "tool_call_id": "call-1",
                "approved": True,
                "tool_call_fingerprint": "v1:sha256:" + "a" * 64,
                "unexpected": True,
            },
            "unknown fields: unexpected",
        ),
        (
            {
                "approval_version": 1,
                "tool_call_id": "bad call",
                "approved": True,
                "tool_call_fingerprint": "v1:sha256:" + "a" * 64,
            },
            "invalid tool-call approval: tool_call_id",
        ),
    ],
)
def test_tool_call_approval_parser_rejects_malformed_records(value: Any, message: str) -> None:
    with pytest.raises(InputValidationError, match=message):
        ToolCallApproval.from_dict(value)
