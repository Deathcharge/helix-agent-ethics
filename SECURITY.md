# Security policy

## Supported versions

Until the first public release, the current default branch and the `0.1.x` release-candidate line
receive security fixes. No older repository snapshot is supported as an installable package.

## Reporting

Please use GitHub's private **Report a vulnerability** flow for this repository; private
vulnerability reporting is enabled. Do not include credentials, personal data, production policy
files, or sensitive action inputs in a public issue. If the private flow is inaccessible, email
[support@samsarix.com](mailto:support@samsarix.com) with a minimal description and request a safer
channel before sending secrets, production data, or exploit details.

No response-time SLA or bounty program is currently promised.

## Security boundary

Policy files are trusted developer/operator configuration. Evaluation inputs may be untrusted and
are bounded and type-checked. The embedding application remains responsible for:

- authenticating the actor and supplying trustworthy facts;
- assigning tool capability labels outside model control;
- binding tool names and capability labels once at trusted registration time where practical;
- storing pending-call fingerprints before review, authenticating reviewers, enforcing approval
  expiry, and atomically consuming approvals once;
- enforcing the returned decision immediately before the protected side effect, either with
  `ToolGate` or an equivalent boundary;
- treating every exception and nonzero CLI exit as non-authorization;
- preventing time-of-check/time-of-use races;
- protecting and reviewing policy files;
- creating, reviewing, authenticating, and enforcing a deployment lock when exact policy and
  context-contract provenance matters;
- authenticating the source and transport of a single-file `PolicyDeployment`; its embedded lock
  proves internal equality but not who approved or delivered it;
- enforcing only the authoritative baseline decision during shadow rollout and separately
  monitoring candidate status, latency, changes, and errors;
- authenticating deployment actors, protecting desired state, and coordinating activation across
  processes or hosts when using `PolicyRuntime`;
- controlling audit destination credentials, network egress, idempotency, access, rotation,
  retention, integrity, and deletion.

When using `OpenTelemetryDecisionEventSink`, the application also owns SDK/exporter configuration,
trace-context propagation, sampling, attribute/event limits, collector authentication and TLS,
queue/export failures, backend access, and retention. The sink emits only versioned event
attributes derived from `AuditRecord`, plus the event-version and audit-record-version attributes,
but policy/rule identifiers and fingerprints are still operational metadata. A non-recording span
intentionally accepts no event, and a successful local `add_event` does not prove export. Never use
trace events as the sole durable authorization record.

When using the optional OpenAI Agents SDK adapter, applications must also keep actor/context
providers application-owned, use strict top-level `FunctionTool` objects, leave pre-approval input
guardrails disabled for review flows, and treat SDK “always approve” as a broad future-call grant
rather than per-call reviewer evidence. Durable runs must persist the adapter's first-write call
fingerprint alongside protected SDK state; the bounded in-memory default fails closed after
reconstruction.

When using the optional LangChain adapter, put Samsarix last in the middleware list so no inner
middleware can change arguments after authorization. Protect LangGraph thread IDs, checkpointer
state, and reviewer endpoints; review interrupts intentionally persist proposed tool arguments.
Authenticate and authorize reviewers, preserve the exact approval binding, enforce expiry and
one-time resume, and treat direct `BaseTool` calls or side effects performed by middleware itself as
outside this adapter. Parallel tool nodes are not a transaction and may produce partial side
effects. A rejected interrupt returns a generic tool error but is not an authorization audit record.

When using the optional Pydantic AI adapter, register only `tool_policy.toolset` for the protected
tools and require the complete run-step registry to remain equal to the trusted catalog. Pydantic
schema and custom argument validators run before the wrapper; validators must not perform side
effects, and policy sees their validated JSON-native result rather than the model's original
spelling. A native Pydantic approval boolean is not Samsarix authorization: approved resume must
carry adapter-built exact-call evidence and still pass current-policy enforcement. Protect
message/deferred state and conversation IDs, authenticate reviewers, enforce expiry and atomic
one-time consumption, and treat other toolsets, direct calls, provider tools, and pre-delegation
side effects as outside this adapter. Parallel calls remain non-transactional.
The default first-write/consume store blocks result replay only inside one live adapter instance;
durable reconstruction requires an application-owned implementation stored with workflow state.

When using the optional MCP Python SDK adapter, advertise only `tool_policy.tools` and register
only `tool_policy.call_tool` for protected tools. Keep the original handler private, preserve the
SDK decorator's default input-schema validation, and derive actor/context facts from authenticated
server state rather than arguments, descriptions, schemas, or `ToolAnnotations`. Review requests
intentionally disclose proposed arguments and trusted capability labels to application code;
authenticate and authorize reviewers, protect that payload, impose expiry and timeout/cancellation,
and treat `review.approval(...)` as unsigned binding evidence. Every retry requires a fresh review.
After a review response, the adapter re-reads request, actor, and context providers; an actor change
invalidates the approval fingerprint and current context is re-evaluated.
Schema validation occurs before the protected handler and therefore produces no Samsarix decision
or authorization audit record. Direct handler calls, FastMCP internal routes, other MCP primitives,
gateways/proxies/providers, validation/provider side effects, and callbacks registered outside the
exact adapter bypass this boundary. The adapter does not provide sandboxing, cancellation,
rollback, or transactionality across concurrent calls.
The exact 1.28.1 contract includes the SDK fix for deprecated WebSocket Host/Origin validation,
but applications using that transport must still enable and configure `TransportSecuritySettings`.
Prefer stdio or Streamable HTTP and follow the SDK's transport-specific authentication, DNS
rebinding, Host, Origin, and TLS guidance; the policy adapter is not transport security.

`ToolGate` invokes only the explicit callback supplied by the embedding application and only after
an allow decision; it is not a sandbox. The package makes no network requests, executes no policy
code, loads no plugins, and stores no raw evaluation input in its built-in audit record.
`ToolDispatcher` optionally snapshots final application callback references and selects them by a
cataloged name after authorization. It does not authenticate callback code, validate a framework's
tool schema, freeze mutable callback/closure/global state, or isolate the resulting side effect.
Policy-test, comparison, and coverage reports exclude case inputs but expose case names. Shadow
reports exclude action inputs and have no case-name field. These report types still expose policy
and rule identifiers, fingerprints, and bounded evaluation errors; do not place secrets in those
operator-authored labels, and protect reports as operational metadata. Coverage proves only that a
supplied case matched a rule, not that every condition path or input is safe.
Lint reports omit condition values, descriptions, and rule messages, but expose rule identifiers
and zero-based condition locations. A clean lint report covers only documented deterministic
findings and is not evidence that an allow rule reflects application intent or least privilege.
Explanation reports additionally expose condition field paths, operators, match/miss/skip status,
effects, priorities, outcomes, and policy/contract fingerprints. They omit input, policy values,
messages, UUIDs, and timestamps, but repeated queries remain an authorization oracle. Restrict the
`explain` CLI/API and its reports to trusted operators; never expose it as an unauthenticated
production endpoint.
Composition reports omit source paths, descriptions, rules, conditions, messages, and condition
values, but expose source and target IDs, versions, rule counts, and exact fingerprints. Treat
those fingerprints as operational metadata and equality oracles, not author signatures or
freshness evidence. Composition does not fetch, authenticate, sign, distribute, or activate policy.
Shadow reports also omit reason and warning text, but expose decision IDs/timestamps and candidate
errors plus per-policy evaluation durations. A successful baseline remains authoritative when the
candidate changes or raises a domain error; candidate health must therefore be monitored
independently of the authorization result.
Shadow evaluation is synchronous and may add latency or resource use. The package does not sample,
queue, or persist telemetry. `PolicyRuntime` can atomically promote or roll back already supplied
artifacts inside one process; it does not authorize that change or distribute it across hosts.
Caller-supplied audit sinks are trusted application code invoked synchronously before authorization;
their failures prevent tool execution, but their transport and downstream storage are outside this
package's boundary.
`CompositeAuditSink` is ordered but not transactional: a later child failure cannot undo an earlier
delivery. It performs no retry, deduplication, or recovery. Put the authoritative durable sink first
and use `decision_id` for downstream idempotency when the application retries uncertain delivery.

`HmacAuditChainSink` adds shared-secret integrity and ordering evidence to the metadata-only local
stream. It does not encrypt records or authenticate an individual author. Anyone with the key can
rewrite the chain. A separately protected `head_mac` is required to detect rollback to a valid
earlier prefix or replacement with an older copy; deletion and availability require backups and
monitoring. Use one writer process per file. The sink serializes its own threads and rejects an
observed external change, but does not acquire a cross-process lock and another writer can race
between its file check and append. A crash or short write can leave an incomplete final entry,
which fails verification. A complete entry written before an uncertain `fsync` may later pass HMAC
verification while its durability remains unknown; recovery must not treat it as durably committed.
Verification never repairs either state.
Operators own key generation/storage/rotation, filesystem permissions, writer exclusion, external
checkpoints, retention, backup, and recovery. An audit entry records authorization, not callback
execution or success.

`ToolGate` rejects a `ToolCallApproval` when its fingerprint does not match the normalized call ID,
tool, arguments, capabilities, and actor. This is mutation detection, not authentication: approval
objects are ordinary application values, and parsing one with `from_dict` proves only that its JSON
shape is valid. Keep approval records in trusted server-side storage, never derive them from model
output, and enforce replay protection in the application.

`ToolGate.bind(...)` freezes a tool name and canonical capability tuple so invocation payloads
cannot downgrade those labels per call. The application still owns the registry used to select the
binding. Treat MCP and other remote tool annotations as untrusted hints unless their source and
meaning are independently trusted.

`OpenAIAgentsToolPolicy.protect(...)` covers only the SDK's top-level Python `FunctionTool`
input-guardrail path. It rejects namespaces and `Agent.as_tool()` wrappers and does not intercept
hosted tools, built-in computer/shell/apply-patch tools, MCP-hosted tools, or handoffs. The SDK runs
the guardrail over raw JSON before Pydantic callback conversion. Samsarix therefore authorizes the
bounded raw object and blocks coercion-sensitive policy type mismatches; applications should still
use precise annotations and avoid safety semantics that exist only after callback coercion. The
adapter's trace output is limited to its identity plus allowed/blocked status, while the normal
Samsarix audit contract remains metadata-only.

The adapter records a fingerprint before it requests Samsarix review and translates an SDK approval
only when that stored exact-call evidence already exists. Its application-owned store is trusted
security state: `remember` must atomically preserve the first value for a key, and `get` must never
create or replace one. A missing record, changed fingerprint, unrelated SDK approval requirement,
or future call covered only by sticky approval fails closed. The default store is process-local,
bounded, and intentionally has no persistence or eviction-based reuse.

Prepared-call batches are an immediate authorization boundary, not durable capabilities.
`evaluate_many`/`enforce_many` pin one in-process runtime generation and validate the full batch
before batch audit delivery, but trusted actor/context facts can still change after preparation.
Prepare and dispatch without an avoidable TOCTOU gap, never mix calls prepared by different gates,
and do not reuse a previously authorized batch. Within one batch, repeated prepared objects and
repeated approval call IDs fail closed; applications still own approval consumption and replay
protection across batches. The base `ToolGate` batch API does not execute callbacks;
`ToolDispatcher` can invoke an allowed batch sequentially but cannot cancel callbacks, roll back
partial side effects, or make a custom audit sink transactional. A sink failure
after earlier batch records were accepted still prevents authorization but may leave partial audit
delivery; destinations own idempotency and reconciliation.

An optional `ContextContract` can reject policy path typos and missing or mistyped declared facts
before rule evaluation. A contract is trusted configuration, not authentication: it does not prove
that identity, capability, approval, tenant, or risk facts came from a trusted source, and it
deliberately permits unrelated input fields. Applications must derive and protect trusted facts
outside model-controlled payloads and use a full application validator when the entire request
must be closed. Decisions and most reports do not bind a contract fingerprint; policy
explanations and runtime status do.
`fingerprint_context_contract` and deployment locks make exact artifact equality enforceable, but
do not authenticate the source of those facts or artifacts.

A `DeploymentLock` binds policy and optional contract IDs, versions, and canonical content
fingerprints. Lock verification rejects mismatch before evaluation, but the lock is not a digital
signature, approval, freshness proof, transparency record, secure distribution protocol, or
rollback control. Anyone able to replace both the artifacts and lock can create a self-consistent
set. Protect them together with repository review, deployment access controls, independently
trusted release identity, and organization-required signing. Lock metadata can act as an equality
oracle and should receive the same operational access controls as policy fingerprints.

A `PolicyDeployment` places the complete policy, optional contract, and mandatory matching lock in
one bounded JSON document. This prevents mixed local file reads and the built-in writer prevents
partial or implicit replacement, but anyone able to create artifacts can make a self-consistent
deployment. Verify expected repository/OCI identity, immutable digest, signature or attestation,
and deployment authorization before loading. The package does not fetch artifacts, run signing
tools, manage trust roots, prevent mutable-tag substitution, persist desired state, or coordinate
hosts. Deployment documents contain complete policy rules, values, descriptions, and messages;
protect the file more strictly than metadata-only status, audit, or comparison reports.

A `ToolGateDeploymentEnvelope` can authenticate the complete policy deployment and trusted catalog
with HMAC-SHA-256 while binding a key ID, target audience, monotonic sequence, issuance time, and
expiry. Parsing an envelope does not verify it. Use `verify_tool_gate_deployment_envelope` for
inspection or the authenticated `ToolGate`/`ToolDispatcher` binding methods immediately before
use. The caller must provide keys through a separate trusted channel, compare the exact audience,
use a trustworthy clock, and persist the highest accepted sequence in protected durable state.
Without that state, an older still-valid envelope can be replayed. Clock skew extends the effective
issuance and expiry boundaries.

HMAC is symmetric: any verifier with the key can forge an indistinguishable envelope, so this
feature does not identify an author or approver and is not a substitute for asymmetric signatures,
Sigstore/TUF policy, threshold authorization, transparency, or an organizational release service.
The envelope is not encrypted and contains full policy and catalog content. Key rotation,
revocation, KMS access, remote transport, one-time activation, durable desired state, and
multi-host convergence remain external responsibilities.

`PolicyRuntime` constructs and verifies a complete candidate before an atomic in-process swap and
retains the last successful generation after candidate failure. Optional compare-and-swap protects
against lost updates between cooperating callers of the same runtime object. It is not durable
rollback prevention, deployment authorization, policy signing, artifact transport, leader
election, multi-process synchronization, or cross-host consensus. Generation numbers restart with
a new process and must not be treated as globally unique or monotonic security counters. Status
omits policy content and action input but exposes artifact IDs, versions, fingerprints, activation
time, and lock-verification state; protect it as operational metadata and equality-oracle material.

The policy fingerprint is deterministic mutation/equality evidence, not a digital signature. It
does not authenticate a policy author, prove review, prevent rollback, or secure policy
distribution. Because a digest can also act as an equality oracle for a guessable private policy,
applications should apply suitable access controls to audit destinations that store it.

## Relevant vulnerability classes

Reports are especially useful when they demonstrate policy bypass, incorrect deny/review
precedence, parser or resource-limit bypass, sensitive input disclosure, unsafe file behavior, or a
way for malformed input to become an allow decision.
