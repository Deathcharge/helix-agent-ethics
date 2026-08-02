# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Correlate one metadata-only policy decision with an in-memory trace."""

from __future__ import annotations

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from samsarix_ethics import OpenTelemetryDecisionEventSink, Policy, ToolGate


def main() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("samsarix-agent-ethics-demo")
    policy = Policy.from_dict(
        {
            "schema_version": 1,
            "id": "trace-demo",
            "version": "1",
            "default_effect": "deny",
            "rules": [
                {
                    "id": "allow-read",
                    "effect": "allow",
                    "message": "Contained reads are allowed.",
                    "conditions": [
                        {"field": "action.arguments.mode", "operator": "eq", "value": "read"}
                    ],
                }
            ],
        }
    )
    gate = ToolGate(policy, audit_sink=OpenTelemetryDecisionEventSink())

    try:
        with tracer.start_as_current_span("agent-turn"):
            decision = gate.evaluate(
                "read_file",
                {"mode": "read", "path": "README.md"},
                capabilities=["workspace:read"],
            )
    finally:
        provider.shutdown()

    event = exporter.get_finished_spans()[0].events[0]
    attributes = event.attributes
    if attributes is None or attributes["samsarix.decision.id"] != decision.decision_id:
        raise RuntimeError("the in-memory exporter did not retain the decision event")
    print(f"{event.name}: {attributes['samsarix.decision.outcome']}")


if __name__ == "__main__":
    main()
