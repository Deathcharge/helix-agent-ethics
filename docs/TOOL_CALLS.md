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
  "context": {"request_id": "req-100"}
}
```

Export the matching Draft 2020-12 schema with
`samsarix-ethics schema tool-context > tool-context-v1.schema.json`.

The contract is intentionally ordinary JSON so other runtimes can build the same facts without
importing this package. `tool_context_version` matches the exported `TOOL_CONTEXT_VERSION`.
`operation` is the registered tool name. `arguments` are the validated arguments proposed for that
exact invocation. `actor` and `context` contain trusted facts supplied by the embedding
application. The `context.approval` field is reserved for a verified `ToolCallApproval` supplied
through the dedicated API; normal context input cannot populate it.

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

## Registration-time binding

Prefer binding the application-owned tool name and capabilities once when a tool is registered:

```python
gate = ToolGate(load_policy("examples/policies/tool-call-baseline.json"))
send_email = gate.bind("send_email", capabilities=["external:write"])
```

The returned frozen `BoundToolGate` exposes `fingerprint`, `evaluate`, `enforce`, `execute`, and
`execute_async` without per-call tool-name or capability parameters. Its canonical capability tuple
is detached from the input iterable. This makes the secure integration shape easier: untrusted
model or protocol call data supplies the arguments and framework call ID, while the application
selects the pre-registered binding by tool name.

Keep the binding registry on the trusted side of the application. MCP annotations such as
`readOnlyHint` and `destructiveHint` are explicitly hints; do not translate annotations from an
untrusted server directly into authorization capabilities. Direct `ToolGate` methods remain
available for framework adapters whose own trusted registry already owns this metadata.

## Synchronous enforcement

```python
from samsarix_ethics import (
    ToolCallApproval,
    ToolCallDeniedError,
    ToolCallReviewRequiredError,
    ToolGate,
    load_policy,
)

gate = ToolGate(
    load_policy("examples/policies/tool-call-baseline.json"),
    audit_log="decisions.jsonl",
)
send_email = gate.bind("send_email", capabilities=["external:write"])

call_id = "call_01JXYZ"
arguments = {"to": "customer@example.com", "subject": "Case update"}
actor = {"id": "support-agent"}

# Create and persist this fingerprint with the pending call before review.
pending_fingerprint = send_email.fingerprint(call_id, arguments, actor=actor)

# Construct this only after an authenticated reviewer approves the stored pending call.
approval = ToolCallApproval(call_id, True, pending_fingerprint)

try:
    result = send_email.execute(
        arguments,
        lambda arguments: mailer.send(**arguments),
        actor=actor,
        tool_call_id=call_id,
        approval=approval,
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
Export the record's Draft 2020-12 contract with
`samsarix-ethics schema audit-record > audit-record-v1.schema.json`.

## Asynchronous enforcement

`execute_async` has identical decision behavior and awaits an async callback:

```python
read_ticket = gate.bind("read_ticket", capabilities=["resource:read"])
result = await read_ticket.execute_async(
    {"ticket_id": "T-100"},
    lambda arguments: ticket_client.read(arguments["ticket_id"]),
)
```

## Existing tool registries

Keep the registry as the canonical executor and create bindings from its trusted registration
metadata:

```python
bindings = {
    "read_ticket": gate.bind("read_ticket", capabilities=["resource:read"]),
}
binding = bindings[requested_tool_name]
result = binding.execute(
    {"ticket_id": "T-100"},
    lambda arguments: registry.call(binding.tool_name, **arguments),
    actor={"id": current_agent_id},
)
```

This works with Samsarix Agent Framework's `ToolRegistry` and any equivalent registry without an
import-time dependency. The policy package and runtime remain independently versioned.

## Human review lifecycle

A review decision is not authorization. A safe resume flow is:

1. Assign a unique framework `tool_call_id`, call `fingerprint_tool_call(...)`, and persist that
   fingerprint with the exact pending tool name, arguments, capability labels, and actor before
   asking for review.
2. Authenticate the reviewer and record their decision against that server-side pending record.
3. Atomically mark an approved pending record consumed while constructing
   `ToolCallApproval(tool_call_id, approved, stored_fingerprint)`. Enforce an application-defined
   expiry and reject already-consumed records.
4. Call `execute` or `execute_async` with the proposed call, its current `tool_call_id`, and the
   approval. `ToolGate` normalizes the current call, recomputes its fingerprint, and rejects a changed ID, tool, arguments,
   capabilities, or actor before policy evaluation, audit delivery, or callback execution.
5. Re-read other time-sensitive authorization and risk facts immediately before execution.

Do not recompute the stored approval fingerprint from resubmitted client input after review. That
would approve the mutation instead of detecting it. The v1 fingerprint deliberately excludes
general runtime `context`, allowing fresh session, risk, and authorization facts to be evaluated;
it binds the call ID, context-contract version, tool name, validated arguments, canonical
capabilities, and actor. Use `fingerprint_tool_call` as the authoritative v1 serializer rather than
inventing a language-specific encoding.

`ToolCallApproval.from_dict` performs strict shape validation only. It does not authenticate the
record, verify reviewer identity, apply an expiry, or prove one-time use. Those stateful controls
belong to the embedding application and should use durable server-side state. Model output and
untrusted client context must never construct or select an approval.

Do not execute from a stale decision or treat evaluation, validation, approval-store, or audit
failures as allow. If the callback itself fails, its exception propagates; the audit record proves
authorization, not successful completion.

## Privacy and audit

Tool arguments may contain secrets or personal data. Decisions, block exceptions, policy-test
reports, and the built-in JSONL audit omit arguments. The embedding application owns redaction of
its own logs and traces, custom-sink transport security and idempotency, durable pending-call
storage, reviewer authentication, audit retention, and post-execution outcome records.

Export the approval transport/storage shape with
`samsarix-ethics schema tool-approval > tool-approval-v1.schema.json`. The fingerprint is opaque
evidence generated by the Python API; schema validity is not approval authenticity.
