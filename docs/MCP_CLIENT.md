# MCP v2 client enforcement

Protect outbound tool calls even when you do not own the MCP server. The adapter discovers a
complete registry, matches it to your trusted capability catalog, pins its definitions, and
enforces policy before each `tools/call` round on one connected MCP v2 session.

## Install and try

Use a separate environment from the [MCP v1 server adapter](MCP.md):

```bash
python -m pip install -e '.[mcp-client]'
python examples/mcp_client_policy_demo.py
```

The exact supported contract is `mcp==2.1.1`. The existing `mcp` extra pins `mcp==1.28.1` for the
server adapter. These extras are **mutually incompatible in one environment**; neither silently
upgrades the other. The base Samsarix package still has zero runtime dependencies. MCP and AnyIO
are loaded lazily by the async factory. The v2 lock, CI lane, and in-memory tests are separate.

The demo reads a support ticket, requests simulated approval for a reply, and blocks deletion
before the remote handler receives it. It needs no network, credentials, sibling repo, or LLM.
Its fixed simulated approval must not be used as a production reviewer.

## Application wiring

`policy`, `catalog`, authentication, and the connected `client` belong to the embedding
application. Create catalog labels yourself; remote descriptions, annotations and model output
must never choose capabilities or authenticated actor facts.

```python
from samsarix_ethics import ToolGate, create_mcp_client_tool_policy

bindings = ToolGate(policy, audit_sink=durable_audit_sink).bind_catalog(
    catalog, registered_tools=catalog.tool_names,
)

# Inside the application's existing `async with Client(...) as client:` block:
protected = await create_mcp_client_tool_policy(
    bindings,
    client,
    server_id="support-primary",  # trusted local alias, not server-reported identity
    actor_provider=lambda: authenticated_actor(),
    context_provider=lambda: current_authorization_facts(),
    approval_provider=authenticated_review,
    timeout_seconds=30,
    review_timeout_seconds=300,
)

# Advertise only protected.tools to the model and route every selected call here.
result = await protected.call_tool("get_ticket", {"ticket_id": "T-100"})
```

The factory consumes every `list_tools` page directly through the public session API, bypassing
the high-level client's discovery cache. Unknown, duplicate, missing, and extra names fail
closed. It captures the session's bound methods; reconnecting the Client requires a new adapter.
`tools` returns fresh deep copies. A canonical SHA-256 fingerprint includes schemas, descriptions,
annotations, execution hints and metadata. Page boundaries and tool order do not affect it.

Before every call, discovery is repeated and must equal the pinned snapshot. Changed definitions
require deliberate review and re-binding, never automatic acceptance. Registration is bounded to
256 tools and 256 pages, with nonempty unique cursors up to 4,096 characters, the core JSON
depth/item/string limits, and a 1 MiB canonical snapshot limit. These are limits **after SDK
decoding**, not transport response-size limits. Bound transport resources separately.

## Arguments, metadata and continuations

`call_tool(name, arguments=None, read_timeout_seconds=None, progress_callback=None, *,
input_responses=None, request_state=None, meta=None)` accepts bounded JSON-native values. Absent
arguments become `{}`. The SDK validates the request-field types before discovery or review;
input response dictionaries are normalized into its typed models. The adapter does not validate
arguments against the tool's advertised JSON Schema or perform server-side coercion. Policy
authorizes the detached raw JSON arguments; the remote application must validate them again.

The reserved `context.mcp` object contains `server_id`, `registry_fingerprint`, `meta`,
`input_responses`, and `request_state`. These request fields can be explicitly constrained by
policy, but are not authenticated identity facts. A context provider that supplies `mcp` fails
closed. Extend any closed application context contract to declare the needed `context.mcp`
fields. SDK-generated protocol/trace/progress metadata is outside this supplied-request snapshot.

Unlike high-level `Client.call_tool`, this adapter uses public `ClientSession.call_tool` for
exactly one round. An SDK `InputRequiredResult` is returned unchanged. The application must vet
any requested sampling, roots, or elicitation, resolve it under separate controls, and call
`protected.call_tool` again with the explicit state and JSON-native responses. That next round
gets new discovery, policy enforcement, and (if required) fresh review. No automatic retry or
input resolver is driven by this adapter. Claimed extension results are not automatically
resolved; the SDK raises `UnexpectedClaimedResult` instead.

## Review and final enforcement

```python
async def authenticated_review(review):
    # The application authenticates/authorizes the reviewer and protects this payload.
    approved = await review_ui(review.to_dict())
    return review.approval(approved=approved)
```

`MCPClientReviewRequest` is immutable. `request` and `to_dict()` return detached, **sensitive**
data including arguments, metadata, and continuation state; never send them to ordinary logs.
Its repr omits those values. Evidence binds a fresh random invocation ID, application-assigned
server identity, pinned registry, tool, arguments, trusted capabilities, actor, and complete
normalized request. It is unsigned evidence, not reviewer authentication. Only this adapter
translates matching evidence into the final gate approval; do not pass it directly to `ToolGate`.

After the async reviewer returns, the adapter refreshes discovery and actor/context facts and
enforces the current policy. An actor change invalidates evidence; revoked context or policy can
still deny. Missing/rejected/malformed approval, replay from another invocation, provider error,
or timeout cannot dispatch. Approval is not an unconditional grant: the policy must contain a
deliberate grant for approved calls, and a still-matching deny or review continues to block.

Each discovery phase and dispatch phase has its own 30-second default timeout; review defaults to
300 seconds. Configurable values must be finite numbers in `(0, 3600]`. The per-call read timeout
changes dispatch only. These are cooperative async deadlines, not a total wall-clock limit or
preemption of blocking synchronous providers. Cancellation and SDK exceptions propagate, error
tool results remain error results, and the adapter never retries. A timeout **does not prove that
the remote side effect did not happen**; reconcile state before any application retry.

Final gate enforcement emits the configured metadata-only authorization record before dispatch,
and audit-sink failure prevents dispatch. Preflight validation/discovery failures and rejected,
missing, timed-out or malformed reviewer responses do not produce final gate audit records.
Without a reviewer, an ordinary review outcome does reach the gate and is recorded. Applications
must record review lifecycle and transport outcomes separately, without logging sensitive data.

## Boundary and deployment checklist

- Only calls through this adapter are protected. Direct Client/session calls, resources, prompts,
  background sampling/elicitation callbacks already configured on the session, other clients,
  and external processes remain outside its boundary. Keep those entrypoints trusted/private.
- Server identity is a local alias, not cryptographic authentication. The application owns TLS,
  OAuth, target allowlists, SSRF protection, transport lifetimes, and subprocess sandboxing.
- Discovery pinning detects advertised changes, not hidden implementation changes or atomic
  server-side revisions. A server can change behavior between listing and execution. Use trusted
  servers and independent server-side policy at the actual side-effect boundary.
- SDK middleware/transport may add metadata or headers (including v2 `x-mcp-header` argument
  mirroring). Auth, callbacks, extensions, and any code before or after this boundary need
  independent review. Keep the selected session and its SDK configuration application-owned.
- Keep fact providers synchronous and side-effect-free; authenticate reviewers, restrict payload
  access, and enforce reviewer-specific authorization. The timeout is not a durable approval queue.
- Parallel calls are independently authorized, not transactional. No cross-call rollback,
  distributed locking, or resource-state snapshot is provided.
- Validate the selected network transport, disconnects, cancellation, secrets handling, and audit
  retention in your deployment. CI proves the in-memory exact SDK contract, not production hosting.

References: [official v2 migration guide](https://py.sdk.modelcontextprotocol.io/migration/),
[client API](https://py.sdk.modelcontextprotocol.io/client/),
[pagination](https://py.sdk.modelcontextprotocol.io/advanced/pagination/), and
[MCP tools specification](https://modelcontextprotocol.io/specification/2026-07-28/server/tools).
Version evidence was checked on 2026-08-31.
