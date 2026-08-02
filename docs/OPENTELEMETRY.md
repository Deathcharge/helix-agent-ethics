# OpenTelemetry decision events

Samsarix Agent Ethics can attach one privacy-minimized policy-decision event to the current
OpenTelemetry span. This lets an application correlate an agent tool span, HTTP request, workflow,
or other active operation with the exact policy decision that preceded execution.

Install the optional API integration and choose an application-owned SDK/exporter:

```bash
python -m pip install -e '.[opentelemetry]'
python -m pip install 'opentelemetry-sdk==1.44.0'
python examples/opentelemetry_decision_event_demo.py
```

The package extra contains only `opentelemetry-api==1.44.0`. OpenTelemetry's
[library guidance](https://opentelemetry.io/docs/languages/python/instrumentation/) recommends that
instrumentation libraries depend only on the API and leave SDK/exporter configuration to the
application. CI installs the exact hash-locked API/SDK graph from
`requirements-opentelemetry.lock`, runs the real in-memory-exporter contract, and executes the
example. Ordinary imports and the default Python matrix do not install OpenTelemetry.

## Use the current span

Configure an SDK and exporter in the application, then use `OpenTelemetryDecisionEventSink` as the
gate's synchronous audit sink:

```python
from opentelemetry import trace
from samsarix_ethics import OpenTelemetryDecisionEventSink, ToolGate

gate = ToolGate(policy, audit_sink=OpenTelemetryDecisionEventSink())

with trace.get_tracer("support-agent").start_as_current_span("agent-turn"):
    decision = gate.enforce(
        "send_message",
        {"recipient": "customer@example.com", "body": "Case update"},
        capabilities=["external:write"],
        actor={"id": "support-agent"},
    )
```

The sink does not create or end a span. It adds one point-in-time event to the active span, which
preserves the caller's existing trace hierarchy and sampling policy. This follows the
[OpenTelemetry tracing API](https://opentelemetry.io/docs/specs/otel/trace/api/), where events
represent occurrences within an operation. When no span is recording—because no SDK is configured,
the span ended, or sampling disabled it—the API path is an intentional no-op and authorization
continues. Trace telemetry is therefore not a durable audit store or proof of delivery.

## Event contract

`OPENTELEMETRY_DECISION_EVENT_NAME` is `samsarix.policy.decision` and
`OPENTELEMETRY_DECISION_EVENT_VERSION` is `1`. A recording span receives these attributes:

| Attribute | Value |
| --- | --- |
| `samsarix.event.version` | event contract version |
| `samsarix.audit_record.version` | source audit-record version |
| `samsarix.decision.id` | lowercase decision UUID |
| `samsarix.decision.evaluated_at` | RFC 3339 evaluation time |
| `samsarix.decision.outcome` | `allow`, `deny`, or `review` |
| `samsarix.policy.id` | operator-authored policy ID |
| `samsarix.policy.version` | operator-authored policy version |
| `samsarix.policy.fingerprint` | exact canonical policy fingerprint |
| `samsarix.policy.matched_rules` | ordered matched-rule IDs |
| `samsarix.policy.warning_count` | warning count |

The event is built only from `AuditRecord`. It excludes action input, actor/context facts, tool
names, capabilities, arguments, policy descriptions, condition fields and values, reason/warning
text, approval evidence, and callback results. This deliberately avoids the sensitive tool-call
argument/result attributes described by the evolving OpenTelemetry GenAI conventions. Policy and
rule identifiers plus fingerprints remain operational metadata; do not place secrets in authored
identifiers and protect trace access.

These `samsarix.*` attributes are a versioned Samsarix contract, not an OpenTelemetry semantic
convention. Consumers should key dashboards and alerts on the exported constants and event-version
attribute rather than treating experimental GenAI convention names as stable.

## Combine durable storage and correlation

Use `CompositeAuditSink` when the same decision must reach durable storage and the current trace:

```python
from samsarix_ethics import (
    CompositeAuditSink,
    JsonlAuditSink,
    OpenTelemetryDecisionEventSink,
    ToolGate,
)

sink = CompositeAuditSink(
    JsonlAuditSink("decisions.jsonl"),
    OpenTelemetryDecisionEventSink(),
)
gate = ToolGate(policy, audit_sink=sink)
```

The composite accepts 1-32 distinct synchronous sink objects, preserves the supplied order, and
stops on the first failure. A child exception, coroutine result, or non-`None` return becomes
`AuditLogError` and prevents authorization. Earlier successful deliveries cannot be rolled back,
later sinks are not called, and the package never retries. Put the authoritative durable sink
first, deduplicate external retries by `decision_id`, and treat partial delivery as an application
recovery concern.

## Failure and ownership boundary

Construction fails if the compatible OpenTelemetry API is absent or malformed. Errors from
retrieving the current span, checking its recording state, or adding an event propagate through the
ordinary fail-closed audit-sink boundary before a callback can execute. Export normally occurs
after `add_event` returns, so later batch-export or collector failure is not visible to the gate.

The application owns SDK/exporter configuration, resource identity, trace-context extraction and
propagation, sampling, attribute/event limits, queues, network credentials, TLS, collector
availability, retention, redaction of non-Samsarix spans, and backend access. The sink proves only
that the local OpenTelemetry API accepted an event on a recording span; it does not prove export,
storage, callback execution, or callback success.
