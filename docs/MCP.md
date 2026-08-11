# MCP Python SDK server integration

Samsarix can enforce an exact trusted tool catalog at the stable MCP Python SDK's low-level
server handler. It uses only public version 1 SDK contracts and leaves the base package
dependency-free.

## Install and run

```bash
python -m pip install -e '.[mcp]'
python examples/mcp_server_policy_demo.py
```

The optional extra pins `mcp==1.28.1`. CI installs its complete hash-locked dependency graph from
`requirements-mcp.lock`, connects the real `ClientSession` and `Server` through the SDK's
in-memory transport, tests allow/deny/review/schema and registry failures, and runs the demo with
no network access. MCP is imported only when `create_mcp_server_tool_policy` is called.

## Protect a server

Build a trusted Samsarix catalog and exact bindings separately from remote tool metadata. Define
the server's real MCP `Tool` objects and application handler, then expose only the adapter copies
and protected handler:

```python
from mcp.server.lowlevel import Server
from mcp.types import Tool
from samsarix_ethics import ToolGate, create_mcp_server_tool_policy

server = Server("protected-server")
bindings = ToolGate(policy).bind_catalog(
    catalog,
    registered_tools=["read_file"],
)
tools = [
    Tool(
        name="read_file",
        description="Read a contained workspace file",
        inputSchema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    )
]


async def handler(name: str, arguments: dict[str, object]) -> object:
    return await application_registry[name](arguments)


tool_policy = create_mcp_server_tool_policy(
    bindings,
    tools,
    handler,
    application_context_provider=lambda: server.request_context,
    actor_provider=lambda request: authenticated_actor(request),
    context_provider=lambda request: trusted_context(request),
)


@server.list_tools()
async def list_tools():
    return list(tool_policy.tools)


server.call_tool()(tool_policy.call_tool)
```

Keep the SDK decorator's default `validate_input=True`. The adapter exact-matches the real MCP
tool names to the complete trusted catalog at construction, deep-copies each definition, and
returns fresh deep copies from `tools`. Unknown, missing, duplicate, extra, or non-`Tool` registry
entries fail closed. MCP `ToolAnnotations`, descriptions, and schemas never become Samsarix
capability labels automatically.

## Request and review flow

For each schema-valid call, `call_tool`:

1. resolves the name only from the exact bindings;
2. bounds, validates, and detaches the argument object;
3. retrieves the current SDK request context and fresh application-owned actor/context facts;
4. checks whether current policy requires review;
5. optionally asks the application review provider for exact-call evidence;
6. after a review response, re-reads application, actor, and context facts;
7. enforces current policy and emits the configured Samsarix audit record; and
8. invokes the async application handler exactly once only after allow.

An async review provider receives the application context and an immutable
`MCPToolReviewRequest`. Its `arguments` property returns a detached copy, `to_dict()` returns the
complete sensitive review payload, and `approval(approved=...)` builds unsigned
`ToolCallApproval` evidence for that request. An approval is bound to a fresh random one-shot call
ID, tool name, arguments, trusted capabilities, actor, and the enforcement fingerprint. It is
valid only inside that invocation; a retry creates a new review request.
If the actor changes during review, approval fingerprint verification fails; changed context facts
are evaluated by the current policy before any callback.

```python
async def approval_provider(request_context, review):
    approved = await authenticated_review_ui(request_context, review.to_dict())
    return review.approval(approved=approved)
```

The application must authenticate and authorize the reviewer, protect the payload, impose expiry
and timeout/cancellation behavior, and prevent the reviewer UI from becoming a confused deputy.
The returned record is binding evidence, not a signature. `None`, rejection, malformed evidence,
provider failure, or missing provider cannot authorize a review outcome.

## Exact enforcement boundary

Covered:

- the stable MCP Python SDK 1.28.1 low-level `Server.call_tool` handler;
- calls whose full registry exactly matches the trusted `BoundToolCatalog`;
- bounded validated JSON argument objects and fresh request-scoped application facts; and
- a handler invoked only by `tool_policy.call_tool` after final Samsarix enforcement.

Not covered:

- direct calls to the original application handler or another registered tool handler;
- FastMCP private/internal dispatch routes or future MCP SDK contracts;
- resources, prompts, sampling, roots, elicitation, logging, completion, or other MCP primitives;
- upstream client-side tools, gateways, proxies, provider-hosted tools, or tool calls dispatched by
  another process;
- side effects in JSON Schema/custom validation, actor/context/review providers, middleware, or
  work performed before the protected handler; and
- callback authentication, sandboxing, cancellation, rollback, or transactionality across
  concurrent calls.

The SDK validates the advertised `inputSchema` before it calls the adapter. Schema-invalid calls
therefore produce an MCP error without a Samsarix decision or authorization audit record. Keep
schema validators side-effect-free. The SDK normally translates handler exceptions into MCP tool
errors; do not expose those errors to untrusted clients without reviewing the application's MCP
error policy. Samsarix block messages omit arguments and authored policy reasons.

## Production checklist

- Pin and verify the supported SDK lock; add a real contract lane before supporting another SDK
  version.
- Prefer stdio or Streamable HTTP. If an application deliberately uses the deprecated WebSocket
  transport, pass strict `TransportSecuritySettings` for Host/Origin validation; 1.28.1 fixes the
  absence of that control in older releases but does not enable it automatically.
- Advertise only `tool_policy.tools` and register only `tool_policy.call_tool` for protected tools.
- Derive actor/context facts from authenticated server state, never model arguments or MCP hints.
- Keep the original handler and binding registry private to trusted server code.
- Use an application-owned durable audit sink when authorization evidence must survive the
  process; ordinary MCP responses are not audit evidence.
- Put network, filesystem, process, tenant, and credential controls at the actual side-effect
  boundary as defense in depth.
- Test disconnects, cancellation, concurrent calls, review timeout, handler errors, and shutdown
  behavior for the selected MCP transport and server host.

The runnable reference is `examples/mcp_server_policy_demo.py`; the real-SDK compatibility contract
is `integration_tests/test_mcp_sdk.py`.
