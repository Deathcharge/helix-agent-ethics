# Tool-call integration contract

`ToolGate` is the dependency-free enforcement boundary for Python agent tools. It normalizes a
proposed call, evaluates policy, appends optional metadata-only audit evidence, and invokes a
callback only when the decision is `allow`.

## Context version 1

`build_tool_context` produces this JSON shape:

```json
{
  "tool_context_version": 1,
  "actor": {"id": "support-agent", "tenant": "acme"},
  "action": {
    "kind": "tool_call",
    "operation": "send_email",
    "capabilities": ["external:write", "data:sensitive"],
    "arguments": {"to": "customer@example.com"}
  },
  "context": {"human_approved": false, "request_id": "req-100"}
}
```

Export the matching Draft 2020-12 schema with
`samsarix-ethics schema tool-context > tool-context-v1.schema.json`.

The contract is intentionally ordinary JSON so other runtimes can build the same facts without
importing this package. `tool_context_version` matches the exported `TOOL_CONTEXT_VERSION`.
`operation` is the registered tool name. `arguments` are the validated arguments proposed for that
exact invocation. `actor` and `context` contain trusted facts supplied by the embedding
application.

Capabilities are policy-facing labels assigned by the tool registry, never by model output. The
builder rejects duplicates and returns them in canonical lexical order. The baseline pack
recognizes:

- `resource:read` for read-only access;
- `destructive` for deletion or irreversible mutation;
- `external:write` for messages, publication, payments, or other external side effects;
- `data:sensitive` for access to confidential or personal data.

Applications may add namespaced labels such as `filesystem:write`, `shell:execute`, or
`billing:refund`. Unknown capabilities fall through to the policy default; the bundled baseline
uses `review`. Its allow rules also require the complete capability array to be a subset of the
recognized baseline labels, so adding an unknown label to an otherwise allowed call cannot inherit
that allow.

## Synchronous enforcement

```python
from samsarix_ethics import (
    ToolCallDeniedError,
    ToolCallReviewRequiredError,
    ToolGate,
    load_policy,
)

gate = ToolGate(
    load_policy("examples/policies/tool-call-baseline.json"),
    audit_log="decisions.jsonl",
)

try:
    result = gate.execute(
        "send_email",
        {"to": "customer@example.com", "subject": "Case update"},
        lambda arguments: mailer.send(**arguments),
        capabilities=["external:write"],
        actor={"id": "support-agent"},
        context={"human_approved": True},
    )
except ToolCallDeniedError as exc:
    record_denial(exc.decision)
except ToolCallReviewRequiredError as exc:
    queue_for_review(exc.decision)
else:
    consume(result.value)
```

The executor receives a detached dictionary containing the exact arguments evaluated by policy.
Use that dictionary for the tool call so the proposed and executed arguments cannot diverge.

To route audit metadata into application-owned storage, supply one synchronous callable instead of
`audit_log`:

```python
from samsarix_ethics import AuditRecord

records: list[AuditRecord] = []
gate = ToolGate(policy, audit_sink=records.append)
```

`audit_log` and `audit_sink` are mutually exclusive. The gate computes the decision, invokes the
configured sink exactly once, and only then returns or enforces the outcome. A custom sink must
return `None`; any exception or other return becomes `AuditLogError` and prevents a tool callback.
The package never retries. If an application sink retries after an uncertain external commit, its
destination may receive the same `decision_id` more than once and must own idempotency.

## Asynchronous enforcement

`execute_async` has identical decision behavior and awaits an async callback:

```python
result = await gate.execute_async(
    "read_ticket",
    {"ticket_id": "T-100"},
    lambda arguments: ticket_client.read(arguments["ticket_id"]),
    capabilities=["resource:read"],
)
```

## Existing tool registries

Keep the registry as the canonical executor and put the gate directly in front of its public call:

```python
result = gate.execute(
    "read_ticket",
    {"ticket_id": "T-100"},
    lambda arguments: registry.call("read_ticket", **arguments),
    capabilities=["resource:read"],
    actor={"id": current_agent_id},
)
```

This works with Samsarix Agent Framework's `ToolRegistry` and any equivalent registry without an
import-time dependency. The policy package and runtime remain independently versioned.

## Human review lifecycle

A review decision is not authorization. Persist the application's own pending call and approval
state, obtain a human decision, then call `execute` or `execute_async` again with fresh trusted
facts such as `context={"human_approved": True}`. The second evaluation happens immediately before
the side effect and produces the decision that authorizes it.

Do not execute from a stale decision, let model output set `human_approved`, or treat evaluation,
validation, or audit failures as allow. If the callback itself fails, its exception propagates;
the audit record proves authorization, not successful completion.

## Privacy and audit

Tool arguments may contain secrets or personal data. Decisions, block exceptions, policy-test
reports, and the built-in JSONL audit omit arguments. The embedding application owns redaction of
its own logs and traces, custom-sink transport security and idempotency, durable pending-call
storage, reviewer authentication, audit retention, and post-execution outcome records.
