# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Optional OpenTelemetry decision events and ordered audit composition."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import samsarix_ethics.otel as otel_module
from samsarix_ethics import (
    OPENTELEMETRY_DECISION_EVENT_NAME,
    OPENTELEMETRY_DECISION_EVENT_VERSION,
    AuditLogError,
    AuditRecord,
    CompositeAuditSink,
    OpenTelemetryDecisionEventSink,
    OpenTelemetryIntegrationError,
    Policy,
    ToolGate,
)


def _record() -> AuditRecord:
    return AuditRecord(
        decision_id="01234567-89ab-cdef-0123-456789abcdef",
        evaluated_at="2026-08-02T12:00:00Z",
        policy_id="otel-test",
        policy_version="1",
        policy_fingerprint="v1:sha256:" + "a" * 64,
        outcome="allow",
        matched_rules=("allow-read",),
        warning_count=1,
    )


class _Span:
    def __init__(self, *, recording: Any = True) -> None:
        self.recording = recording
        self.events: list[tuple[str, dict[str, Any]]] = []

    def is_recording(self) -> Any:
        return self.recording

    def add_event(self, name: str, *, attributes: dict[str, Any]) -> None:
        self.events.append((name, attributes))


def _install_fake_trace(monkeypatch: pytest.MonkeyPatch, span: Any) -> None:
    monkeypatch.setattr(
        otel_module,
        "import_module",
        lambda name: (
            SimpleNamespace(get_current_span=lambda: span)
            if name == "opentelemetry.trace"
            else None
        ),
    )


def test_opentelemetry_sink_emits_exact_metadata_only_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    span = _Span()
    _install_fake_trace(monkeypatch, span)

    sink = OpenTelemetryDecisionEventSink()
    assert sink(_record()) is None

    assert span.events == [
        (
            OPENTELEMETRY_DECISION_EVENT_NAME,
            {
                "samsarix.event.version": OPENTELEMETRY_DECISION_EVENT_VERSION,
                "samsarix.audit_record.version": 1,
                "samsarix.decision.id": "01234567-89ab-cdef-0123-456789abcdef",
                "samsarix.decision.evaluated_at": "2026-08-02T12:00:00Z",
                "samsarix.decision.outcome": "allow",
                "samsarix.policy.id": "otel-test",
                "samsarix.policy.version": "1",
                "samsarix.policy.fingerprint": "v1:sha256:" + "a" * 64,
                "samsarix.policy.matched_rules": ("allow-read",),
                "samsarix.policy.warning_count": 1,
            },
        )
    ]
    assert "argument-secret" not in repr(span.events)
    assert "authored-message-secret" not in repr(span.events)


def test_opentelemetry_sink_is_a_noop_for_nonrecording_span(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    span = _Span(recording=False)
    _install_fake_trace(monkeypatch, span)

    OpenTelemetryDecisionEventSink()(_record())

    assert span.events == []


def test_opentelemetry_sink_validates_dependency_and_api_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing(_name: str) -> Any:
        raise ImportError("missing")

    monkeypatch.setattr(otel_module, "import_module", missing)
    with pytest.raises(OpenTelemetryIntegrationError, match=r"\[opentelemetry\]"):
        OpenTelemetryDecisionEventSink()

    monkeypatch.setattr(
        otel_module,
        "import_module",
        lambda _name: SimpleNamespace(get_current_span=None),
    )
    with pytest.raises(OpenTelemetryIntegrationError, match="must be callable"):
        OpenTelemetryDecisionEventSink()

    _install_fake_trace(monkeypatch, object())
    with pytest.raises(OpenTelemetryIntegrationError, match="incompatible API shape"):
        OpenTelemetryDecisionEventSink()(_record())

    _install_fake_trace(monkeypatch, _Span(recording="yes"))
    with pytest.raises(OpenTelemetryIntegrationError, match="return a boolean"):
        OpenTelemetryDecisionEventSink()(_record())

    _install_fake_trace(monkeypatch, _Span())
    with pytest.raises(TypeError, match="AuditRecord"):
        OpenTelemetryDecisionEventSink()(object())  # type: ignore[arg-type]


def test_opentelemetry_delivery_error_blocks_tool_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenSpan(_Span):
        def add_event(self, name: str, *, attributes: dict[str, Any]) -> None:
            raise RuntimeError("private exporter detail")

    _install_fake_trace(monkeypatch, BrokenSpan())
    policy = Policy.from_dict(
        {
            "schema_version": 1,
            "id": "otel-failure",
            "version": "1",
            "default_effect": "deny",
            "rules": [
                {
                    "id": "allow-read",
                    "effect": "allow",
                    "message": "Read is allowed.",
                    "conditions": [
                        {"field": "action.arguments.mode", "operator": "eq", "value": "read"}
                    ],
                }
            ],
        }
    )
    called = False

    def callback(_arguments: dict[str, Any]) -> None:
        nonlocal called
        called = True

    with pytest.raises(AuditLogError, match="RuntimeError") as captured:
        ToolGate(policy, audit_sink=OpenTelemetryDecisionEventSink()).execute(
            "read", {"mode": "read"}, callback
        )

    assert "private exporter detail" not in str(captured.value)
    assert called is False


def test_composite_audit_sink_delivers_in_order_and_stops_on_failure() -> None:
    events: list[str] = []

    def first(_record: AuditRecord) -> None:
        events.append("first")

    def failing(_record: AuditRecord) -> str:
        events.append("failing")
        return "not-none"

    def last(_record: AuditRecord) -> None:
        events.append("last")

    sink = CompositeAuditSink(first, failing, last)  # type: ignore[arg-type]
    assert sink.sinks == (first, failing, last)
    with pytest.raises(AuditLogError, match="must return None"):
        sink(_record())
    assert events == ["first", "failing"]


def test_composite_audit_sink_validates_configuration() -> None:
    def sink(_record: AuditRecord) -> None:
        return None

    with pytest.raises(ValueError, match="1-32"):
        CompositeAuditSink()
    with pytest.raises(ValueError, match="1-32"):
        CompositeAuditSink(*(sink for _ in range(33)))
    with pytest.raises(ValueError, match="duplicate"):
        CompositeAuditSink(sink, sink)
    with pytest.raises(TypeError, match="synchronous callable"):
        CompositeAuditSink(object())  # type: ignore[arg-type]

    async def async_sink(_record: AuditRecord) -> None:
        return None

    with pytest.raises(TypeError, match="synchronous callable"):
        CompositeAuditSink(async_sink)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="AuditRecord"):
        CompositeAuditSink(sink)(object())  # type: ignore[arg-type]
