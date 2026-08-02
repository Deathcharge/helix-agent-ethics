# LangChain tool-policy middleware

Samsarix Agent Ethics can enforce an exact trusted tool catalog inside LangChain's sync and async
agent tool-call paths. The middleware sees raw model-supplied arguments immediately before the
registered `BaseTool` handler and uses LangGraph's public interrupt primitive for review outcomes.

Install the exact optional framework contract and run the no-network demo:

```bash
python -m pip install -e '.[langchain]'
python examples/langchain_policy_middleware_demo.py
```

The optional extra pins `langchain==1.3.14`. CI installs its complete hash-locked graph from
`requirements-langchain.lock`, runs a real `create_agent` contract with an in-memory checkpointer,
and executes the example. The core package does not import or install LangChain until
`create_langchain_tool_policy` is called. LangChain documents `wrap_tool_call` as the hook around
each tool call and notes that the first middleware is outermost; the Samsarix middleware must be
last so it evaluates the final arguments after any outer transformations.

## Register an exact tool set

Create a trusted catalog and bind it to the gate before passing tools to LangChain:

```python
from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver
from samsarix_ethics import ToolGate, create_langchain_tool_policy

bindings = ToolGate(policy, audit_sink=audit_sink).bind_catalog(
    catalog,
    registered_tools=["read_ticket", "send_message"],
)
tool_policy = create_langchain_tool_policy(
    bindings,
    actor_provider=lambda app: {"id": app.user_id},
    context_provider=lambda app: {"tenant": app.tenant_id},
)
tools = tool_policy.validate_tools([read_ticket, send_message])

agent = create_agent(
    model=model,
    tools=tools,
    middleware=[other_middleware, tool_policy.middleware],  # Samsarix is last
    context_schema=ApplicationContext,
    checkpointer=InMemorySaver(),  # Demo/test only; replace in production
)
```

`validate_tools` accepts only real LangChain `BaseTool` instances and requires their names to
exactly equal the bound Samsarix catalog. At execution, the requested name must still resolve to a
registered `BaseTool` with the same name. Dynamic, missing, duplicated, uncataloged, or mismatched
tools fail closed.

Actor and context providers are synchronous application callbacks. They receive
`request.runtime.context`, not model messages or tool arguments, and are called again after an
interrupt so an approval cannot silently retain stale identity or tenant facts. Keep the runtime
context application-owned and authenticated. Provider programming errors propagate; malformed
provider results and expected Samsarix policy errors never call the tool handler.

## Review and exact-call resume

An allow decision is audited and the original handler is called once. A deny decision is audited
and raises `ToolCallDeniedError`. A review decision calls LangGraph `interrupt()` before execution
with a JSON-compatible payload shaped like:

```json
{
  "type": "samsarix.tool_call.review",
  "adapter_version": 1,
  "approval_binding": {
    "approval_version": 1,
    "tool_call_id": "call-123",
    "tool_call_fingerprint": "v1:sha256:..."
  },
  "tool": {
    "name": "send_message",
    "arguments": {"recipient": "customer@example.com", "body": "Case update"}
  },
  "policy": {
    "id": "support-tools",
    "version": "4",
    "fingerprint": "v1:sha256:...",
    "decisive_rule_ids": ["review-external-message"]
  }
}
```

After authenticating the reviewer and recording their decision, resume the same LangGraph thread
with the binding fields unchanged and one added boolean:

```python
from langgraph.types import Command

approval = {**payload["approval_binding"], "approved": True}
result = agent.invoke(Command(resume=approval), config=same_thread_config, version="v2")
```

The response is parsed as a strict `ToolCallApproval`. Its call ID and fingerprint must match the
current name, raw arguments, trusted capabilities, and freshly provided actor. Edited arguments,
a changed actor, a different call ID, missing fields, extra fields, malformed data, or a replay
against another call fails before the handler. Current policy and context facts are then evaluated
again with the exact approval; approval does not override deny precedence or a policy that still
requires review.

A response with `approved: false` returns a generic error `ToolMessage` and never calls the tool.
The pre-interrupt explanation and a rejection do not emit an authorization audit record; an exact
approved resume emits the final allow record, while a deny emits its deny record. Persist reviewer
identity and rejection evidence in the application's review system when that evidence is required.

`InMemorySaver` is included through LangChain and is only for tests and the demo. Production review
requires installing and configuring a durable LangGraph checkpointer separately, plus an
authenticated and authorized reviewer UI/API, CSRF/replay protection where relevant, approval
expiry, protected thread IDs, retention, and atomic one-time workflow resume. Samsarix approval
objects authenticate neither the reviewer nor the checkpoint transport.

## Security and execution boundary

The interrupt payload intentionally includes tool arguments so a reviewer can inspect the proposed
side effect. LangGraph persists interrupt and message state; treat the checkpointer as sensitive,
apply encryption and access controls, and avoid secrets in policy/rule identifiers. Actor and
context facts, policy messages, condition values, and exception details are excluded from the
payload.

LangChain validates the `BaseTool` schema inside the handler path, after middleware. Samsarix sees
the raw argument mapping first and rejects non-JSON values, non-finite numbers, excessive shape,
and policy type mismatches rather than relying on later Pydantic coercion. Keep Samsarix last in the
middleware list: an inner middleware could otherwise change arguments after authorization. Outer
retry middleware invokes the inner Samsarix gate for every attempted execution.

The adapter covers tools executed through the `create_agent` tool middleware stack. It does not
cover direct `BaseTool.invoke` calls, model-provider server-side tools, handoffs, code outside the
agent graph, or another middleware that performs a side effect without calling its handler.
Multiple tool nodes may execute independently; this integration does not provide all-calls-before-
dispatch batch atomicity, callback idempotency, transaction rollback, or exactly-once side effects.
Use Samsarix batch preflight before framework scheduling when no call may begin until the complete
set is allowed.
