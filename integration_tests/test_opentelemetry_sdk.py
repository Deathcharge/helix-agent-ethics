# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Exact-version contract test against the real OpenTelemetry API and SDK."""

from __future__ import annotations

from importlib.metadata import version

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from samsarix_ethics import (
    OPENTELEMETRY_DECISION_EVENT_NAME,
    AuditRecord,
    CompositeAuditSink,
    OpenTelemetryDecisionEventSink,
    Policy,
    ToolGate,
)


def test_real_opentelemetry_sdk_correlates_metadata_only_decision_event() -> None:
    assert version("opentelemetry-api") == "1.44.0"
    assert version("opentelemetry-sdk") == "1.44.0"
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("samsarix-agent-ethics-contract")
    records: list[AuditRecord] = []
    policy = Policy.from_dict(
        {
            "schema_version": 1,
            "id": "otel-contract",
            "version": "1",
            "default_effect": "deny",
            "rules": [
                {
                    "id": "allow-read",
                    "effect": "allow",
                    "message": "authored-message-secret",
                    "conditions": [
                        {"field": "action.arguments.mode", "operator": "eq", "value": "read"}
                    ],
                }
            ],
        }
    )
    gate = ToolGate(
        policy,
        audit_sink=CompositeAuditSink(records.append, OpenTelemetryDecisionEventSink()),
    )

    try:
        with tracer.start_as_current_span("agent-run"):
            decision = gate.evaluate(
                "read_file",
                {"mode": "read", "secret": "argument-secret"},
                capabilities=["workspace:read"],
            )
            denied = gate.evaluate(
                "write_file",
                {"mode": "write", "secret": "denied-argument-secret"},
                capabilities=["workspace:write"],
            )
    finally:
        provider.shutdown()

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert len(spans[0].events) == 2
    event, denied_event = spans[0].events
    assert event.name == OPENTELEMETRY_DECISION_EVENT_NAME
    assert event.attributes is not None
    assert event.attributes["samsarix.decision.id"] == decision.decision_id
    assert event.attributes["samsarix.decision.outcome"] == "allow"
    assert event.attributes["samsarix.policy.fingerprint"] == decision.policy_fingerprint
    assert event.attributes["samsarix.policy.matched_rules"] == ("allow-read",)
    assert denied_event.attributes is not None
    assert denied_event.attributes["samsarix.decision.id"] == denied.decision_id
    assert denied_event.attributes["samsarix.decision.outcome"] == "deny"
    assert denied_event.attributes["samsarix.policy.matched_rules"] == ()
    assert records == [AuditRecord.from_decision(decision), AuditRecord.from_decision(denied)]
    serialized = repr(spans[0].events)
    assert "argument-secret" not in serialized
    assert "denied-argument-secret" not in serialized
    assert "authored-message-secret" not in serialized
