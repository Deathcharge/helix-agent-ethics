# OpenAI Agents SDK integration

Samsarix Agent Ethics can protect top-level Python `FunctionTool` objects from the OpenAI Agents
SDK while keeping the core package dependency-free. The adapter turns a Samsarix `review` outcome
into the SDK's resumable approval flow and performs the authoritative policy evaluation as the
last input guardrail immediately before the function callback.

Install the optional integration:

```bash
python -m pip install -e '.[openai-agents]'
python examples/openai_agents_guardrail_demo.py
```

The optional extra supports `openai-agents>=0.18.3,<0.19`. CI separately installs the exact
`0.18.3` dependency graph from `requirements-openai-agents.lock` and runs the real SDK contract
test. Ordinary imports and the default test matrix do not install the SDK.

## Protect a function tool

Create a strict function tool, bind its trusted name and capabilities outside model-controlled
arguments, then protect a copy:

```python
from agents import Agent, function_tool
from samsarix_ethics import ToolGate, create_openai_agents_tool_policy

@function_tool(strict_mode=True)
def send_message(recipient: str, body: str) -> str:
    return application_mailer.send(recipient, body)

binding = ToolGate(policy, audit_sink=decision_store.append).bind(
    "send_message",
    capabilities=["external:write"],
)
adapter = create_openai_agents_tool_policy(
    binding,
    actor_provider=lambda app: {"id": app.authenticated_actor_id},
    context_provider=lambda app: {
        "tenant": app.tenant_id,
        "incident_mode": app.incident_mode,
    },
)
protected_send_message = adapter.protect(send_message)
agent = Agent(name="support-agent", tools=[protected_send_message])
```

`protect` returns an SDK `FunctionTool` copy. It rejects a name mismatch, non-strict schema,
namespace, `Agent.as_tool()` result, incompatible SDK shape, or a tool already protected by this
adapter. Existing input guardrails remain first and existing approval logic is combined with a
logical OR. Samsarix is appended as the final input guardrail.

The providers receive the application object passed as the Agents SDK run context. They must be
synchronous and must derive authenticated actor and current policy facts from application-owned
state, never from model arguments. They run again at the final guardrail so a resumed call is
checked against fresh facts.

`approval_store` implements `OpenAIAgentsApprovalStore.remember(...)` and `.get(...)`.
`remember` must atomically retain and return the first fingerprint for one application/tool/call-ID
key without replacing it; `get` must return that value without creating it. Protect this state with
the pending run and apply reviewer authentication, expiry, one-time consumption, and retention in
the surrounding application. Omitting the store selects a thread-safe in-memory implementation
bounded to `MAX_PENDING_OPENAI_APPROVALS` (4,096). That default is convenient for one live process
but deliberately fails closed after adapter/process reconstruction; use an application-owned store
for serialized or durable SDK run state.

## Review and resume

The adapter's approval callback uses `BoundToolGate.explain`, which emits no audit record and cannot
authorize execution. Only an exact `review` outcome asks the SDK to interrupt. An `allow` continues
to the final guardrail; a `deny` or malformed evaluation proceeds to that guardrail and fails
closed instead of becoming human-overridable.

Before returning `True` to create an interruption, the adapter fingerprints the reviewed call and
records it through the store's first-write contract. Use the SDK's ordinary interruption API to
display and resolve pending calls. Approve the specific interruption, persist the SDK run state and
matching fingerprint in protected storage when the workflow is durable, then resume the same run.
On resume, the adapter reads the SDK approval status only when that policy-review fingerprint
already exists, binds it to the current call ID, raw arguments, trusted name/capabilities, and
fresh actor, and calls `BoundToolGate.enforce`. That final call emits the configured Samsarix audit
record. Missing state, same-ID mutation, or an approval requested only by some other SDK rule cannot
create Samsarix approval evidence.

Policies must explicitly describe what approval changes. Because precedence is
`deny > review > allow`, a review rule that still matches after approval continues to block. A
typical review condition checks that `context.approval` does not exist, while a higher-priority
allow rule checks `context.approval.approved == true` plus any current risk constraints.

The SDK also offers “always approve.” That intentionally grants future SDK calls approval status;
it is broader than per-call human evidence. The adapter does not translate it for a future call
unless Samsarix previously recorded that exact call ID and fingerprint as a review. Applications
should still offer only call-scoped approval when they require one-time reviewer evidence.

## Exact boundary

The supported interception path is a top-level Python `FunctionTool` with
`strict_json_schema=True`. The adapter does not cover hosted tools, built-in computer/shell/apply
patch tools, MCP-hosted tools, handoffs, namespaced tools, or `Agent.as_tool()`. Use a separate
framework boundary or Samsarix `ToolDispatcher` for those paths.

The SDK guardrail receives raw JSON before its Pydantic function schema converts Python callback
values. Samsarix rejects duplicate keys, non-finite numbers, non-object JSON, oversized input, and
policy type mismatches. The real-SDK test proves that a coercible string such as `"1"` is blocked
when policy requires a number even though the SDK callback would later coerce it to `1`. Still use
precise JSON-compatible annotations and keep coercion-sensitive authorization in Samsarix policy,
not inside the callback.

Leave the SDK's `pre_approval_tool_input_guardrails` option at its default `False` for Samsarix
review tools. Enabling it can run the authoritative guardrail before the SDK creates the approval
interruption; the SDK already reruns input guardrails after approval and immediately before the
callback.

Guardrail trace output contains only the adapter identity and `allowed` or `blocked` status. It
does not contain arguments, actor/context facts, policy messages, rule IDs, or exception text.
Unexpected application programming errors propagate; expected Samsarix validation, audit, deny,
and review errors become a halting SDK guardrail tripwire.
