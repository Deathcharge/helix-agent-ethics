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

The exact supported contract is `mcp==2.1.1`, `anyio==4.14.2` for deadlines, and
`httpx2==2.12.0` for optional response budgets.
The existing `mcp` extra pins `mcp==1.28.1` for the
server adapter. These extras are **mutually incompatible in one environment**; neither silently
upgrades the other. The base Samsarix package still has zero runtime dependencies. MCP and AnyIO
are loaded lazily by the async factory. The v2 lock and CI environment are separate.

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
decoding**. Enable the HTTP response budgets below before opening a network Client; an already
connected client is not retrofitted by `create_mcp_client_tool_policy`.

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
  retention in your deployment. CI exercises in-memory, loopback TCP and verified TLS with the
  stock SDK client-credentials OAuth provider against isolated test servers. It does not validate
  production hosting, your identity provider, TLS termination, or proxy configuration.

## Streamable HTTP integration

Keep the endpoint and credentials application-owned, never model-supplied. The SDK accepts a
caller-owned `httpx2.AsyncClient` through its public transport factory:

```python
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from samsarix_ethics import create_mcp_client_tool_policy, create_mcp_http_transport

# endpoint is a fixed, allowlisted HTTPS URL; auth is your configured SDK OAuth provider.
network_timeout = httpx2.Timeout(30, read=30)

async def supply_missing_timeout(request: httpx2.Request) -> None:
    # MCP 2.1.1 token requests bypass AsyncClient's default timeout insertion.
    request.extensions.setdefault("timeout", network_timeout.as_dict())

bounded_http = create_mcp_http_transport(
    httpx2.AsyncHTTPTransport(
        trust_env=False,
        retries=0,
        limits=httpx2.Limits(max_connections=20, max_keepalive_connections=10),
    ),
    max_wire_bytes=4 * 1024 * 1024,
    max_response_bytes=4 * 1024 * 1024,
)
async with httpx2.AsyncClient(
    transport=bounded_http,
    auth=auth,
    trust_env=False,
    follow_redirects=False,
    # HTTP network-idle limit, separate from the adapter's dispatch deadline.
    timeout=network_timeout,
    event_hooks={"request": [supply_missing_timeout]},
) as http:
    async with Client(streamable_http_client(endpoint, http_client=http)) as client:
        protected = await create_mcp_client_tool_policy(
            bindings, client, server_id="support-primary",
            actor_provider=authenticated_actor,
            context_provider=current_authorization_facts,
            approval_provider=authenticated_review,
        )
        result = await protected.call_tool("get_ticket", {"ticket_id": "T-100"})
```

This is application wiring, not an OAuth setup or runnable credential-free example. Use the SDK's
[OAuth client guide](https://py.sdk.modelcontextprotocol.io/client/oauth-clients/) to configure your actual
provider. Do not disable certificate verification. `trust_env=False` ignores ambient HTTP proxy
configuration; configure TLS, a required corporate proxy and pool limits on the **wrapped
AsyncHTTPTransport**, not on AsyncClient. Do not add client `proxy`/`mounts` that bypass the bounded
transport; every used route must have its own bounded wrapper. Redirect following is deliberately
disabled: select the canonical endpoint and review any target change before creating a new client.
Connection limits are not response-size, rate, cost, or whole-workflow limits.
The response-budget wrapper does not select or validate credential destinations or URL schemes.
Enforce the HTTPS allowlist in application configuration before supplying credentials; local
cleartext HTTP in the integration suite uses only isolated loopback servers and ephemeral test tokens.

The hook fills only **missing** request timeouts, including those on this SDK's generated token
requests; `AsyncClient(timeout=...)` alone does not cover those requests. It preserves explicit
SDK/per-request values, so it is not a universal timeout ceiling. This is application wiring via
HTTPX2's public [request hooks](https://httpx2.pydantic.dev/advanced/event-hooks/) and
[timeout extension](https://httpx2.pydantic.dev/advanced/extensions/#timeout), not an SDK monkeypatch.
Also bound the application's connection/authentication phase and overall workflow with cooperative
deadlines: the policy adapter is constructed **after** the initial OAuth/SDK handshake and cannot
time it out. Keep async Client entry, use and exit in the same task/cancel-scope lifetime.

This example defaults ordinary MCP HTTP read inactivity to 30 seconds; explicit SDK/per-request
HTTP timeout values still take precedence. A larger adapter `read_timeout_seconds` alone does not
configure the HTTP timeout. For a longer silent tool, configure **both** the HTTP read-idle limit and
the adapter dispatch deadline deliberately. Network activity can reset the HTTP idle timer but
does not extend the adapter's total dispatch-phase deadline. Neither limit bounds the entire
discovery/review/dispatch workflow.

One HTTP client per credential/tenant boundary prevents mutable default headers or cookies being
shared accidentally. Scope the auth provider and its token store to the same boundary; separate
HTTP clients do not isolate an incorrectly shared token store. Authenticate actor facts
independently; neither `_meta` nor `server_id`
establishes tenant identity. A changed token or registry during approval can reject the final
preflight. Remote credentials revoked *after* preflight still require server-side enforcement.
The SDK does not close a caller-supplied HTTP client: keep the outer `async with` shown above.

Handle transport failures around the **whole Client context**, including context exit. With the
tested SDK, 401/403 failures can surface as `MCPError` rather than `HTTPStatusError`; background
transport errors may be nested in Python `ExceptionGroup`. Do not parse error text for authorization
decisions or log complete exception/request objects containing credentials or payloads. Preserve
cancellation and reconcile remote state before considering a separately authorized retry.
The adapter itself never retries. OAuth authentication/refresh hooks, custom transports, or proxies
may replay HTTP requests independently; review that behavior separately. Neither suite below
establishes at-most-once execution across arbitrary authentication middleware or remote services.

### Service-to-service OAuth acceptance

For a pre-registered machine client, configure the SDK provider on the caller-owned HTTP client:

```python
from mcp.client.auth.extensions.client_credentials import ClientCredentialsOAuthProvider

auth = ClientCredentialsOAuthProvider(
    server_url=endpoint,
    storage=tenant_token_storage,
    client_id=registered_client_id,
    client_secret=secret_from_credential_store,
    token_endpoint_auth_method="client_secret_basic",
    scope="support:tools",
)
```

Use the [SDK OAuth guide](https://py.sdk.modelcontextprotocol.io/client/oauth-clients/) for provider
and storage contracts. Credentials, issuer/endpoint allowlists, encrypted durable storage, absolute
token expiry on reload, revocation/rotation, and reviewer identity remain application-owned. Scope
each provider/store/client together; discard the provider as well as the client after a token-store
failure. In this SDK, in-memory token state is updated before storage completes; retrying with the
same provider is not a fail-closed storage-recovery strategy.

The loopback TLS acceptance tests use this exact provider, not a stubbed auth flow, and independently
observe protected handlers and token grants. Important observed limits:

- Both Basic and form-post client authentication work over verified HTTPS. Credentials go to the
  separate token endpoint, not the resource or metadata endpoints; opaque access tokens identify
  the server-authenticated tenant independently of supplied MCP metadata.
- The SDK validates resource/issuer metadata identity, but discovery can introduce additional URL
  destinations. An allowlisted MCP URL alone is not an egress/SSRF policy for metadata and token
  endpoints. Enforce permitted HTTPS destinations before credentials leave the application.
- A resource challenge can replace the provider's constructor scope. That scope is **not** a grant
  ceiling: the authorization server must enforce the client's allowed scopes/resource audience.
  The test server rejects a challenged `support:admin` scope; no tool runs.
- Revoked access tokens can cause a fresh client-credentials exchange and replay. The tested read
  executes once per authorized invocation; this is reacquisition, not a refresh-token grant.
  Revoking both the token and client during review prevents final tool dispatch.
- A plain 403 is retried once by this SDK auth provider without obtaining another token. The test
  middleware rejects both requests **before** the handler. Do not extrapolate exactly-once behavior
  to a server that performs a side effect before returning 401/403.
- Discovery/token response bodies pass through the same budgets and latch. TLS, token-service,
  token-storage, scope and network-timeout errors do not themselves latch a body-budget failure.
- SDK OAuth exceptions/logs can include the authorization server's error response body. The fixed
  Samsarix budget labels and metadata-only audit sink do not sanitize third-party loggers. Apply
  application logging/redaction policy and never log provider/token/request objects or raw errors.

The test-only CA, certificates, clients, in-memory stores and narrow authorization server are
generated locally and are **not production authentication components**. Certificates are trusted
only by the test clients; no system trust store is changed. No real account or provider credentials
are needed. Browser authorization-code/PKCE, CIMD/registration, persistent credential recovery,
and long-lived OAuth-authenticated SSE subscriptions are not covered.

### Post-grant refresh acceptance

The separate `test_mcp_client_refresh.py` contracts exercise the stock `OAuthClientProvider` from
MCP 2.1.1 over verified TLS in auto/JSON sessions with the bounded transport and Samsarix adapter.
They **seed an existing confidential-client grant and trusted cached issuer metadata**.
Test-only SDK context updates force
expiry without sleeping; these are not application setup instructions or proof of browser login,
metadata discovery, or restart recovery.

- Basic and form-post authentication refresh twice across a read and a human-reviewed send.
  Rotated refresh tokens replace the old token; omitted refresh-token and scope fields retain the
  prior values. The fixture enforces client/tenant and resource binding. Policy-denied calls never
  reach the tool, and refresh tokens/client secrets are absent from resource bodies and Samsarix
  audit records. See [RFC 6749 section 6](https://www.rfc-editor.org/rfc/rfc6749.html#section-6).
- Two concurrent calls through one provider produce one refresh and two authorized handler calls.
  This is one provider's in-process lock, **not coordination across clients, processes or hosts**.
- Revoked/wrong-tenant grants, a 503, malformed success data and failed storage during review
  prevent tool dispatch. A failed grant can trigger full reauthorization; the fixture has no browser
  callbacks, so it stops with `OAuthFlowError`. Do not wrap this in an unattended reauthorization loop.
- A store failure after rotation leaves the old token in the store while the issuer has invalidated
  it and the provider has the replacement in memory. Discard the provider/client and reconcile with
  the selected identity provider; retrying stale storage is not a rollback strategy. Durable storage
  and rotation-loss recovery remain deployment acceptance gates.
- Oversized refresh responses latch the body-budget failure; a timeout/cancellation disconnects the
  test exchange without a tool effect. A timeout after an issuer commits rotation can still lose the
  replacement token. The fixture's interrupted exchange stops before issuance and does not prove
  safe retry after a lost response. Request-hook timeouts and the outer operation deadline remain
  necessary for auth-generated requests.
- A fresh provider loading a token with `expires_in=0` does not reconstruct an absolute expiry
  timestamp. In the tested case, the server rejects the old access token and the SDK attempts full
  reauthorization, not a refresh. Persisting relative lifetime alone is insufficient; qualify the
  application's actual storage/expiry/restart policy against its SDK and issuer.

This narrow fixture is not a complete authorization server and does not implement refresh-token
family replay detection, sender-constrained tokens, or cross-process credential transactions.
Production issuer selection should account for the rotation/replay guidance in
[RFC 9700 section 4.14](https://www.rfc-editor.org/rfc/rfc9700.html#section-4.14).
There is no new Samsarix auth API, automatic retry, dependency or credential storage component.

### Response budgets and recovery

`create_mcp_http_transport(transport, *, max_wire_bytes=4194304, max_response_bytes=4194304)`
returns an `MCPHTTPTransport` implementing the HTTPX2 async transport interface. Each budget must
be an integer in `[1, 67108864]`; booleans/floats are rejected before optional imports. The factory
requires exactly HTTPX2 2.12.0 and imports it lazily. The base package still needs no HTTP dependency.
The wrapper owns its supplied transport: do not share or independently close that transport.

- The wire budget counts encoded response-body bytes; the response budget counts decoded bytes
  before they reach MCP JSON/SSE parsing. Each applies to a **whole HTTP response**, including a
  long-lived SSE stream, not to individual events. Defaults are 4 MiB each.
- Oversized valid Content-Length values reject before reading the body. Missing lengths and
  chunked bodies are counted while streaming; malformed/ambiguous lengths reject. A declared
  length must contain 1–20 ASCII digits, with only spaces/tabs allowed around it. HEAD/204/304
  representation lengths do not predict a response body and are not used for early size rejection.
- The request advertises `gzip, deflate, identity`. A single one of these encodings is supported;
  other/stacked encodings reject before decoding. HTTPX2's bounded gzip/deflate decoder chunks are
  counted without aggregation. Decoder errors latch the transport too. Returned response headers
  omit Content-Encoding and Content-Length because the exposed stream is already decoded.
- A contract violation closes the offending response and permanently sets `failure_reason`.
  Further HTTP dispatches fail before reaching the wrapped transport, so reconnect/refresh hooks
  cannot reset a breached budget on this instance. Concurrent streams check the latch before
  delivering their next decoded chunk; they are not proactively interrupted while awaiting data.
- `MCPHTTPResponseError.reason` and `failure_reason` contain fixed diagnostic labels, not URLs,
  credentials, headers, or body fragments. The SDK can wrap/translate these errors: catch around the
  whole Client lifetime and inspect the application-owned transport, not remote error text.
- Transport/response cleanup uses a cooperative, shielded five-second deadline. Close failures
  do not replace an active primary error/cancellation; cleanup adds a fixed recovery note without
  payload data. A close failure with no primary error propagates. `failure_reason` retains a prior
  response-contract rejection even if the SDK translates or wraps the exception.
  Normal network errors, pool timeouts, and caller cancellation do not themselves latch
  a response-budget failure. No automatic retry or telemetry is added.

After a latched failure, reconcile any remote side effects and review the server/limits before
creating a **new** HTTP client, transport and policy adapter. Do not automatically rebuild them in
a retry loop. Previously delivered SSE events, completed concurrent work, and remote mutations
cannot be recalled. A rejected result does not mean its tool never executed.

These are body-delivery budgets, **not a hard process-memory, CPU, request-body, header, rate or
whole-workflow cap**. The wrapped transport and HTTP parser allocate buffers before this boundary;
the pinned decoder may allocate a chunk up to 1 MiB before the decoded counter checks it. JSON
objects and earlier accepted chunks also take memory. Pass an application-owned streaming transport
(the guide uses AsyncHTTPTransport), not one that preloads responses. Apply process/resource limits,
deadlines and workflow quotas separately. Existing SDK decoding semantics remain in effect; this
wrapper is not a general compression-conformance validator.

### Reproduce the network contract

After installing the development and v2 client locks as described in [RELEASING.md](../RELEASING.md):

```bash
python -m pytest --no-cov integration_tests/test_mcp_client_sdk.py integration_tests/test_mcp_client_http.py integration_tests/test_mcp_http_transport.py integration_tests/test_mcp_client_oauth.py integration_tests/test_mcp_client_refresh.py
```

The HTTP suite owns an ephemeral `127.0.0.1` socket, real Uvicorn/ASGI server, SDK HTTP client and
bounded teardown. It requires no internet, paid API, persistent credential, or separate server.
Its random bearer tokens and authentication middleware are **test fixtures, not production auth**.
Linux and Windows CI run the same tests.

| Exercised boundary | Evidence asserted |
| --- | --- |
| Auto/legacy negotiation; JSON/SSE responses | Read and reviewed send arrive; denied delete does not |
| Concurrent clients; forged tenant metadata | Server sees each connection's authenticated principal |
| Invalid credentials/origin | Actual HTTP 401/403; no handler invocation |
| Revocation or advertised drift during review | Recheck fails before any `tools/call` |
| Unknown tool or failed audit delivery | No remote invocation; unknown tool causes no extra HTTP request |
| Deadline, task cancellation, result-stream disconnect | One wire call and handler invocation; no tool retry; owned resources close |
| Identity/gzip/deflate; declared and chunked body overruns | Exact decoded boundary accepted; wire/decoded overflow closes and latches |
| Unsupported/corrupt encodings; simultaneous responses | No post-latch request dispatch or delivery of the next pending chunk |
| Single-connection pool pressure/cancellation | Pool timeout is distinct; closing/cancelling a response releases the connection |
| TLS on resource and issuer origins | Untrusted CA, expired certificate and hostname mismatch reject before HTTP credentials reach that origin |
| Stock client-credentials OAuth, Basic/form-post, JSON/SSE, auto/legacy | Read/review/deny workflow; scoped audience-bound grants; separate tenant stores |
| Invalid client, resource/issuer mismatch, challenged scope, token-service/storage failure | No protected handler; no successful token persistence |
| Oversized resource metadata, issuer metadata or token response | Body-budget latch prevents subsequent HTTP dispatch |
| Revoked token/client; plain 403 | Explicitly counted grant/replay behavior, with no unauthorized handler invocation |
| Token exchange network timeout/cancellation | Request timeout hook works; server observes disconnect; no token persistence or tool effect |
| Existing-grant refresh | Rotation/omission, concurrency, review-time failures, budgets and interruption; seeded issuer/grant, not browser or durable recovery |

The injected disconnect happens after the handler has run. An `allow` audit record therefore does
**not** establish delivery, success, rollback, or exactly-once execution. Cancellation tests observe
cleanup by client/server shutdown, not a universal remote-cancellation deadline. These tests do not
cover internet/identity-provider infrastructure, hostile response headers/parser memory, reverse
proxies, long-lived OAuth SSE subscriptions/event-store resumption, or durability across process
crashes. Reproduce those with
your selected deployment.

References: [official v2 migration guide](https://py.sdk.modelcontextprotocol.io/migration/),
[client API](https://py.sdk.modelcontextprotocol.io/client/),
[HTTP transport configuration](https://py.sdk.modelcontextprotocol.io/client/transports/),
[HTTPX2 custom transports](https://httpx2.pydantic.dev/advanced/transports/),
[Streamable HTTP specification](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http),
[pagination](https://py.sdk.modelcontextprotocol.io/advanced/pagination/), and
[MCP tools specification](https://modelcontextprotocol.io/specification/2026-07-28/server/tools).
Version evidence was checked on 2026-08-31.
