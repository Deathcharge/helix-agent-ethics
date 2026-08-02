# Pydantic AI toolset policy

Samsarix Agent Ethics can protect one exact Pydantic AI toolset registry with deterministic
allow, deny, and native deferred-review behavior. The adapter wraps the public `WrapperToolset`
execution seam and checks the complete real `ToolsetTool` registry on every agent run step.

Install the exact optional contract and run the no-network demo:

```bash
python -m pip install -e '.[pydantic-ai]'
python examples/pydantic_ai_policy_toolset_demo.py
```

The extra pins `pydantic-ai-slim==2.22.0`, which provides the agent and toolset runtime without the
full provider, CLI, and MCP metapackage. CI installs the complete graph from
`requirements-pydantic-ai.lock`, runs a real `Agent` with `TestModel`, and executes the example.
The dependency-free base package imports successfully without Pydantic AI; the optional runtime is
loaded only when `create_pydantic_ai_tool_policy` is called.

## Protect an exact toolset

Create and populate the toolset, then bind the same complete name set to a trusted Samsarix
catalog:

```python
from pydantic_ai import Agent, DeferredToolRequests, FunctionToolset
from samsarix_ethics import ToolGate, create_pydantic_ai_tool_policy

tools = FunctionToolset()

@tools.tool_plain
def read_ticket(ticket_id: str) -> str:
    return ticket_store.read(ticket_id)

@tools.tool_plain
def send_message(recipient: str, body: str) -> str:
    return messenger.send(recipient, body)

bindings = ToolGate(policy, audit_sink=audit_sink).bind_catalog(
    catalog,
    registered_tools=["read_ticket", "send_message"],
)
tool_policy = create_pydantic_ai_tool_policy(
    bindings,
    tools,
    actor_provider=lambda deps: {"id": deps.user_id},
    context_provider=lambda deps: {"tenant": deps.tenant_id},
)
agent = Agent(
    model,
    toolsets=[tool_policy.toolset],
    deps_type=ApplicationContext,
    output_type=[str, DeferredToolRequests],
)
```

The wrapped registry must contain only real Pydantic AI `ToolsetTool` values, each registry key
must equal its `ToolDefinition.name`, and its complete name set must exactly equal the bound
catalog. A missing, added, renamed, malformed, or dynamically different tool fails closed before
execution. Each resolved execution must also use the exact `ToolsetTool` object snapshotted for
that run step. Populate dynamic toolsets before binding, or ensure every run-step variant has the
same cataloged names.

Actor and context providers are synchronous application callbacks. They receive `RunContext.deps`,
not messages or model arguments, and run again on resume. Keep dependencies authenticated and
application-owned. Provider programming errors remain visible; malformed provider results never
call the tool.

## Native review and exact resume

Allow is audited and delegates once. Deny is audited and raises the ordinary typed Samsarix gate
error. Review raises Pydantic AI's native `ApprovalRequired` before delegation. The resulting
`DeferredToolRequests.metadata[tool_call_id]["samsarix.tool_call.review"]` contains the exact call
binding, proposed tool name and arguments, policy identity and fingerprint, and decisive rule IDs.

After separately authenticating and authorizing the reviewer, resolve any chosen subset of pending
calls through the adapter:

```python
from pydantic_ai import DeferredToolRequests

first = agent.run_sync(prompt)
assert isinstance(first.output, DeferredToolRequests)

decisions = {call.tool_call_id: reviewer_approved(call) for call in first.output.approvals}
results = tool_policy.build_results(first.output, decisions)
completed = agent.run_sync(
    "Continue.",
    message_history=first.all_messages(),
    deferred_tool_results=results,
)
```

`build_results` validates every selected pending call against the saved Samsarix review metadata.
An approval adds strict `samsarix.tool_call.approval` metadata bound to the exact call ID and
fingerprint; a rejection becomes a generic Pydantic AI `ToolDenied` result and never delegates.
Pydantic AI's plain native `True` approval is deliberately insufficient because its documentation
does not define approval as an application authorization boundary. Forging or omitting Samsarix
metadata fails closed.

On approved resume, the adapter recomputes the fingerprint from the tool-context format version,
current call ID, name, validated arguments, trusted catalog capabilities, and freshly supplied
actor. General context and the optional context-contract identity/version are deliberately not
fingerprint fields; current policy and context facts are re-evaluated instead. Changed bound fields,
missing or malformed evidence, replay against another call, or a current deny/review never invokes
the tool.

Approved `build_results` also records the fingerprint in a first-write approval store, and resume
atomically consumes it before final enforcement. Replaying the same result fails closed. The
bounded thread-safe default retains up to 4,096 calls in one process and fails closed after
reconstruction. Durable workflows supply `approval_store=` implementing synchronous `remember`
and atomic `consume` methods alongside protected Pydantic state. The store is trusted security
state; it does not authenticate a reviewer. The reviewer system still owns identity,
authorization, expiry, revocation, durable persistence, and prevention of repeatedly minting new
results from the same pending review.

For multiple deferred calls, an application can resolve a subset and later combine or supply the
result objects according to Pydantic AI's workflow contract. Samsarix does not make parallel tool
execution transactional and cannot roll back a tool that already produced a side effect.

## Validation timing and execution boundary

Pydantic AI validates the tool schema and runs any custom argument validator before
`WrapperToolset.call_tool`. Samsarix therefore authorizes Pydantic AI's schema-validated argument
dictionary, not the model's original JSON spelling. Keep validators deterministic and free of side
effects: a validator can run before this gate. The adapter then applies Samsarix's bounded
JSON-native validation and passes a detached copy to the wrapped toolset. Non-JSON values and
non-finite numbers fail closed.

The adapter covers calls routed through the wrapped toolset registered on that agent. It does not
cover another unwrapped toolset, direct toolset calls, provider/server-side or hosted tools,
built-in tools, model activity, output functions, or application code that performs a side effect
before delegating to the wrapper. Keep every consequential local tool in a protected exact
toolset, and enforce separate boundaries for other execution paths.

Pydantic AI message history and deferred results may contain proposed arguments and authorization
metadata. Production workflows must protect storage and conversation identifiers, authenticate
review endpoints, apply retention and encryption appropriate to the data, prevent cross-tenant
resume, and consume a decision once. The no-network example uses only in-memory state and is not a
durable workflow design.
