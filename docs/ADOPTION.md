# Adoption and compatibility evidence

This record distinguishes a verified library consumer from a public release or production
deployment. It is intentionally specific enough for maintainers to reproduce and update.

## Public runtime contract

The repository includes optional exact-version adapters for strict top-level OpenAI Agents SDK
`FunctionTool` objects, exact LangChain `BaseTool` registries, exact Pydantic AI `ToolsetTool`
registries, and exact stable MCP Python SDK server registries. Dedicated CI jobs install hashed
dependency graphs for `openai-agents==0.18.3`, `langchain==1.3.14`,
`pydantic-ai-slim==2.22.0`, and `mcp==1.28.1`, exercise real framework types, and run
no-network examples. The OpenAI contract verifies guardrail execution and fail-closed handling
before schema coercion. The LangChain contract verifies a real checkpointed interrupt/resume and
final middleware ordering. The Pydantic AI contract verifies native deferred approval/rejection,
requires Samsarix evidence beyond a native boolean, and detects registry drift. The MCP contract
connects a real in-memory client/server session and verifies exact listing, schema validation,
allow, deny, one-shot review, missing review, and registry drift. The
[OpenAI guide](OPENAI_AGENTS.md), [LangChain guide](LANGCHAIN.md), and
[Pydantic AI guide](PYDANTIC_AI.md), plus the [MCP guide](MCP.md), make this reproducible from a public checkout. These are
maintained compatibility contracts, not evidence of a third-party adopter, live model call,
production traffic, or hosted deployment.

## Implemented gap: stable MCP server-side enforcement

The MCP tools specification recommends confirmation for sensitive operations, while the protocol
schema says tool annotations are untrusted hints. The stable Python SDK exposes a public low-level
`Server.call_tool` handler and public `Tool` definitions. Samsarix exact-matches that entire real
registry to application-authored capabilities, advertises copied definitions, and retrieves fresh
request facts before final handler invocation. Review is application-owned and returns one-shot
fingerprint-bound evidence for the current call only.

SDK JSON Schema validation precedes the protected handler. Direct callbacks, FastMCP internal
routes, other protocol primitives, proxies, provider execution, and side effects in providers or
validators remain outside the boundary. Review payloads contain proposed arguments and trusted
capabilities; reviewer identity, confidentiality, expiry, timeout/cancellation, and concurrent
side-effect behavior remain application-owned. This is exact public runtime evidence, not an
adopter, gateway, or production claim.

## Implemented gap: exact-registry LangChain enforcement

LangChain documents `wrap_tool_call` as the middleware hook surrounding every tool call, with the
first middleware outermost, and LangGraph interrupts as checkpointed pause/resume primitives.
Samsarix therefore accepts only a complete set of real `BaseTool` objects whose names exactly
match a trusted `BoundToolCatalog`, and its middleware must be listed last so it authorizes the
final raw argument mapping after outer transformations. Allow and deny paths re-use the ordinary
gate; review emits one native interrupt whose response is bound to the exact tool-call ID,
normalized arguments, trusted catalog metadata, and actor. Resume re-evaluates the current policy
and trusted facts before invoking the framework handler once.

The interrupt payload necessarily persists proposed tool arguments in the application's LangGraph
checkpointer. The application therefore owns checkpointer encryption/access/retention, reviewer
authentication, CSRF protection, expiry, atomic one-time resume, and thread-ID authorization.
Direct `BaseTool.invoke`, server-side tools, middleware that executes before calling its handler,
and calls made outside the protected agent bypass this boundary. Parallel tool calls are not a
transaction and may still produce partial side effects. This is exact public runtime evidence, not
an adopter or production claim.

## Implemented gap: native Pydantic AI deferred authorization

Pydantic AI exposes `WrapperToolset.call_tool` as the public tool-execution wrapping seam and
`DeferredToolRequests`/`DeferredToolResults` as its pause-and-resume contract. Its documentation
also states that approval is not itself an authorization boundary. Samsarix therefore exact-matches
the full run-step registry, raises native `ApprovalRequired` for policy review, and requires
adapter-built fingerprint evidence in metadata before accepting a native approved resume. Current
policy and fresh application facts remain authoritative.

Pydantic schema and custom argument validation precedes the wrapper, so the boundary protects
validated arguments and requires side-effect-free validators. Other toolsets, direct calls, and
provider-side tools bypass the wrapper. Conversation and deferred state may retain proposed
arguments, while reviewer authentication, decision expiry, one-time consumption, and durable
storage remain application-owned. This is exact public runtime evidence, not adopter or production
evidence.

## Samsarix Agent Framework

Samsarix Agent Framework is the first consumer-owned integration. Its optional
`PolicyToolRegistry` is a drop-in framework tool registry that:

- requires at least one application-owned capability label for every registered tool;
- obtains fresh trusted actor and approval facts immediately before every invocation;
- calls Agent Ethics' `ToolGate` at that boundary;
- never invokes the tool on `deny`, `review`, malformed facts, provider failure, or audit failure;
- preserves the authorizing `Decision` for direct callers and normalizes failures into the
  framework's `ToolError` contract; and
- keeps Agent Ethics absent from the framework's default dependency-free install.

| Evidence | Value |
| --- | --- |
| Consumer owner | Samsarix LLC |
| Consumer repository | `Deathcharge/samsarix-agent-framework` (private as of 2026-08-01) |
| Consumer pull request | `#4`, merged 2026-08-01 |
| Consumer merge commit | `02fe13ae102359958b8a02d125a41abaa814d472` |
| Consumer contract head | `1e44b70be52bf19ae625f2eaba4a845a8afc6c8e` |
| Agent Ethics source pin | `eb69207b14ddd79bdfe774ec5b166c8ca8ce940e` (`0.1.0`) |
| Contract fixture | 10 policy-registry tests inside the consumer's 106-test suite |
| Hosted compatibility | Python 3.11-3.14 integration tests; Python 3.10 core-only test |
| Package evidence | separate base-wheel and `[ethics]` installed-wheel smoke tests |
| Support level | experimental until both repositories publish versioned releases |

The pull request and CI are visible to repository-authorized maintainers. Because the consumer is
private, this is owner-verifiable adoption evidence rather than a publicly reproducible third-party
case study. No production traffic, external customer, availability claim, or product-market fit is
inferred.

The compatibility window is the exact Agent Ethics commit above. Moving to another commit or
release requires the consumer contract suite and installed-wheel smoke tests to pass again. The
rollback path is to revert the consumer merge or restore its core `ToolRegistry`; removing the
policy gate is a security behavior change and requires an equivalent application authorization
boundary.

## Implemented gap: application-owned audit sinks

Post-adoption research favors a small audit-delivery seam over owning approval workflows, OAuth, or
policy distribution:

- [OpenAI Agents SDK tool guardrails](https://openai.github.io/openai-agents-python/guardrails/)
  already wrap function tools immediately before execution and re-run time-sensitive checks after
  approval.
- [Pydantic AI deferred tools](https://pydantic.dev/docs/ai/tools-toolsets/deferred-tools/) already
  model in-process and external approval/pause flows, and explicitly warn that approval is not
  application authorization.
- [MCP authorization guidance](https://modelcontextprotocol.io/docs/tutorials/security/authorization)
  assigns token validation and per-tool scopes to established identity/resource-server controls.
- [OPA decision logs](https://www.openpolicyagent.org/docs/management-decision-logs) support remote
  services and custom plugins because production consumers need to route decisions into their own
  operational systems.

Agent Ethics therefore keeps making local deterministic decisions and exposes one bounded,
metadata-only `AuditRecord` to a caller-supplied sink. The implementation preserves the current
JSONL path API and defines an immutable, versioned public record contract. After computing a
decision, `ToolGate` calls exactly one configured sink exactly once, before returning that decision
as authorization or invoking the tool callback. Only a normal `None` return counts as a successful
write; a non-`None` return or raised exception becomes `AuditLogError` and prevents execution.

The library does not retry a sink. Re-evaluating a call creates another decision and audit record;
a sink that retries after an uncertain external commit may also deliver the same `decision_id`
more than once. Idempotency, HTTP delivery, queues, retries, credentials, retention, and
tamper-evident storage therefore stay with the embedding application until a concrete adopter
validates a narrower requirement. The built-in JSONL path remains the local sink and retains its
current fail-closed behavior.

## Implemented gap: trace-correlated decisions

Production policy engines expose decision identifiers and trace correlation, while agent runtimes
increasingly emit tool and guardrail spans. OPA's
[decision logs](https://www.openpolicyagent.org/docs/management-decision-logs) include decision,
trace, and span IDs, and its [monitoring guide](https://www.openpolicyagent.org/docs/monitoring)
adds `opa.decision_id` to evaluation spans. OpenTelemetry recommends API-only dependencies for
instrumentation libraries and application-owned SDK/exporter configuration.

Agent Ethics now converts its existing metadata-only `AuditRecord` into one versioned
`samsarix.policy.decision` event on the caller's current recording span. The event adds no action
input, tool arguments/results, actor/context facts, policy literals/messages, or approval data.
An exact OpenTelemetry 1.44.0 API/SDK contract uses a real in-memory exporter, and a no-network
example verifies correlation. `CompositeAuditSink` permits an authoritative durable sink followed
by the trace event, with bounded ordered delivery and explicit non-transactional partial failure.

This is operational correlation, not a trace backend or audit ledger. Sampling or an absent SDK
makes a span non-recording; later exporter/collector failures occur after local event acceptance.
The application owns propagation, sampling, exporters, credentials, redaction of other spans,
retention, backend access, and recovery.

## Implemented gap: approval-bound resume

The same framework research exposed a narrower authorization gap: a plain approved boolean can be
replayed with changed arguments after a reviewer sees the original request. Agent Ethics now
provides a versioned `ToolCallApproval` and `fingerprint_tool_call`. `ToolGate` compares the stored
fingerprint with the current normalized call before policy evaluation, audit delivery, or callback
execution. The binding covers the framework call ID, tool-context version, tool name, arguments,
canonical capability labels, and actor.

The library deliberately does not own reviewer identity, an approval database, expiry, or replay
state. Those controls require application authentication and atomic durable storage. Parsing an
approval validates its shape only, and runtime context remains outside the fingerprint so fresh
authorization and risk facts can be evaluated immediately before execution. The next consumer
compatibility increment is to adopt this contract in Samsarix Agent Framework and rerun its
consumer-owned integration matrix against the exact Agent Ethics merge commit.

## Implemented gap: trusted registration profiles

Frameworks expose a tool name and handler at registration, making that boundary the natural place
to attach application-owned risk metadata. `ToolGate.bind(...)` now returns a frozen
`BoundToolGate` whose name and canonical capability tuple cannot be changed per call. It shares the
same audit sink and policy as its parent and supports fingerprints, structured approvals, sync
execution, and async execution.

This is framework-neutral and does not trust MCP annotations or model-generated labels. Existing
registries can either select a prebuilt binding by tool name or continue using the lower-level
`ToolGate` API when their own registration object already guarantees trusted metadata.

## Implemented gap: exact trusted tool catalogs

Independent bindings prevent per-call downgrades but do not prove that the complete runtime
registry was classified. `ToolCatalog` adds a strict standalone JSON v1 artifact for 1-256 trusted
local names and canonical capability sets. `ToolGate.bind_catalog(...)` requires the caller's
complete trusted registry-name snapshot to match exactly before returning an immutable
`BoundToolCatalog`; a missing, extra, duplicate, or malformed name fails setup.

The catalog has a domain-separated exact-content fingerprint, bounded loader, bundled schema, CLI
identity report, and checked coding-agent example. Samsarix Core callers pass
`(spec.name for spec in registry.list())`; Samsarix Agent Framework callers pass
`registry.list_tools().keys()`. MCP tools are cataloged under application-approved local aliases,
never by trusting remote behavioral annotations. The catalog proves content equality, not
authorship, freshness, callable identity, or correctness of the assigned labels.

## Implemented gap: coherent gate deployment

`ToolGateDeployment` packages one verified policy deployment with one exact catalog and its
canonical fingerprint. Bounded duplicate-safe loading and atomic output prevent mixed local reads;
`ToolGate.bind_deployment(...)` returns no binding until the complete application registry matches.
The artifact is intentionally separate from policy-deployment v1 and does not authenticate its
producer, registry callables, catalog labels, freshness, or promotion authority.

## Implemented gap: all-calls-before-dispatch authorization

Current agent runtimes may propose more than one tool call in a turn and schedule them concurrently.
Authorizing calls only as individual callbacks begin can allow a safe call to start before a later
call in the same proposal is found to need review. `BoundToolGate.prepare(...)` now produces a
gate-specific immutable normalized call, and `ToolGate.evaluate_many`/`enforce_many` collect the
complete bounded batch before evaluating it.

The runtime batch primitive pins one active policy generation. Contract-invalid late items produce
no batch audit delivery; successful decisions are audited in input order; and `enforce_many` returns
only if every item allows. A typed block exposes every metadata-only decision plus the first blocked
index from that same evaluation, which is enough to populate an ordered multi-call review surface
without duplicate decisions or audits. This is a pre-dispatch authorization contract, not a
transaction or task scheduler. Adapters must dispatch immediately from each prepared call's detached
arguments and own concurrency, cancellation, callback failure, and partial side effects.

The checked coding-agent deployment makes the integration reproducible without adding a framework
dependency. Its trusted binding taxonomy treats unknown tools and under-labeled elevated tools as
review, denies workspace escape and unapproved destruction, and never converts MCP annotations from
an untrusted server directly into capabilities.

## Implemented gap: exact policy provenance

Policy ID and version are operator-authored labels. Without a content-derived identifier, an edit
that accidentally reuses both labels can make distinct evaluations indistinguishable in a decision
store. OPA's decision-log contract similarly associates evaluations with deployed bundle revisions,
which confirms that policy artifact provenance belongs next to the decision rather than only in a
separate deployment system.

Agent Ethics now computes one domain-separated `v1:sha256` digest from the complete canonical
validated policy when `PolicyEngine` is constructed. The engine reuses it in every decision;
`ToolGate`, `BoundToolGate`, policy-test reports, CLI validation, and audit record v1 expose the same
value. A pinned vector protects the serialization contract. The digest is mutation/equality
evidence only: the embedding application still owns policy signing, review, distribution,
freshness, and rollback prevention.

## Implemented gap: pre-deployment policy impact

Exact fingerprints identify that a policy changed but do not explain what the change does. The
bounded regression suite now doubles as a candidate-impact corpus through `compare_policies` and
the `compare` CLI. Each case runs against the approved baseline and candidate; the report separates
authorization changes from matched-rule/warning metadata changes and treats either-side failures as
errors. Inputs, decision UUIDs, timestamps, reasons, and warning text remain absent.

This gives consumer maintainers a deterministic artifact to review before updating an exact source
pin. It does not modify the private Agent Framework integration or claim exhaustive equivalence:
the consumer must still update its own pin and rerun its compatibility matrix in a separately
scoped repository change.

## Implemented gap: policy rule coverage

A passing suite can still leave newly added or rarely used branches unexercised. Following OPA's
coverage gate and OpenFGA's recommendation to test every application relation, Agent Ethics now
unions the matched rule IDs from successful bounded cases and reports declaration-ordered covered
and uncovered rules, all three outcome counts, and input-free errors. An explicit integer threshold
turns the report into a CI gate; errors always fail it.

This is deliberately rule-match coverage rather than a stronger safety claim. One case may satisfy
an entire rule without testing each condition boundary, and overridden rules count as covered when
they match. The consumer must retain its compatibility assertions and negative/boundary cases; any
consumer adoption of this new contract remains a separately scoped source-pin update.

## Implemented gap: deterministic authoring diagnostics

Coverage cannot explain why a rule is unexercised, and schema validation intentionally accepts
semantically unusual but well-formed policies. Following OPA strict/lint guidance and IAM Access
Analyzer's severity categories, Agent Ethics now reports five stable policy-authoring findings:
permissive defaults, unconditional allows, provably impossible same-field conditions, duplicate
conditions, and missing authored explanations. CI can fail at security-warning, warning, or
suggestion severity.

The analyzer never copies condition values, descriptions, or rule messages into findings and does
not infer a consumer domain schema. Dynamic references are skipped unless a contradiction is
independently certain. This makes the report safe to adopt as an additional consumer gate, but it
cannot replace consumer-owned authorization tests, review, or least-privilege analysis.

## Implemented gap: application fact contracts

Generic JSON safety and valid policy syntax cannot catch `action.operaton` or prove that a numeric
operator reads a number. Cedar and AWS Verified Permissions address that class of production error
with application schemas and strict policy validation. Agent Ethics now provides a smaller
zero-dependency `ContextContract` that matches its own dotted-fact policy model.

The contract declares up to 1,000 paths as required or optional JSON-native types. Policy
deployment validation rejects undeclared condition and `$ref` paths plus incompatible
operator/type combinations. `PolicyEngine` and `ToolGate` can then reject missing or mistyped
declared facts before rule evaluation. The bundled tool-call contract validates the existing
twelve-rule baseline and runs through the real gate.

Regression tests, coverage, baseline/candidate comparison, and live shadow evaluation accept the
same contract, preventing lifecycle evidence from silently using only generic JSON validation.
One shared contract applies to both sides of a rollout; additive migrations should introduce new
optional facts before policies reference them.

This does not implement Cedar principals/resources/actions, close undeclared request fields, prove
fact authenticity, or replace a consumer's full application schema. Contract adoption and source
pin updates in downstream repositories remain separately reviewed changes. Version 1 decision and
report formats do not carry contract fingerprints. A versioned deployment lock now binds exact
policy and contract content during validation and engine/gate construction; the deployment system
must preserve and authenticate that reviewed artifact set.

## Implemented gap: exact deployment selection

Operator-authored policy and contract versions are useful release labels, but they do not prevent
version reuse or unnoticed content replacement. OPA bundle activation similarly distinguishes a
declared revision from integrity verification, and strict schema-backed authorization services
reject invalid policy updates rather than activating them.

Agent Ethics now provides canonical domain-separated context-contract fingerprints and a strict
`DeploymentLock` artifact. The CLI creates and verifies locks, exposes their Draft 2020-12 schema,
and can require the lock for `validate` and `check`. `PolicyEngine` and `ToolGate` verify the same
lock before evaluation. The checked-in tool-call example binds a real twelve-rule policy and its
application fact contract, and a test makes either artifact's drift fail CI.

This is exact-content selection, not a control plane. Locks do not sign, distribute, activate,
refresh, or roll back artifacts and do not identify an approver. Repository review, build
provenance, deployment credentials, and any required signing system remain caller-owned.

## Implemented gap: atomic in-process activation

Exact selection still left long-running agents to rebuild or manually swap gates when an approved
policy changed. That creates a risk of separately updating a policy and contract, replacing a
working policy with a failed candidate, or losing concurrent deployment updates.

- [OPA bundles](https://www.openpolicyagent.org/docs/management-bundles) load policy without a
  process restart and retain the existing bundle when verification fails.
- [OPA status](https://www.openpolicyagent.org/docs/management-status) exposes the last successful
  active revision and activation time separately from activation errors.
- [AWS Verified Permissions strict validation](https://docs.aws.amazon.com/cli/latest/reference/verifiedpermissions/update-policy-store.html)
  rejects new or updated policies that fail schema-backed validation.

Agent Ethics now provides `PolicyRuntime`: it constructs the entire candidate engine before
touching live state, atomically swaps the policy/contract/lock set, retains the last successful
generation on failure, and optionally rejects stale compare-and-swap attempts. Each evaluation
captures one generation, while a bounded batch pins one generation for the entire batch.
Runtime-backed tool gates and existing bound tools follow successful activation without losing
their trusted registration metadata or audit sink.

The versioned status exposes process-local generation, activation time, exact artifact identity,
and lock-verification state without policy content or action input. This is not remote bundle
fetching or a distributed control plane: applications still own approval, authentication,
artifact transport, durable desired state, restart recovery, health monitoring, and multi-host
convergence.

## Implemented gap: coherent deployment transport

Atomic runtime activation begins only after the application has loaded Python objects. Delivering
policy, contract, and lock as three mutable files still permits a restart or updater to read a
mixed set between replacements. That fails safely but can create avoidable availability loss and
complicates retention and rollback.

OPA packages policy and related data into one bundle, validates the complete file set before
activation, and can persist the last activated bundle for restart. ORAS supports pushing one file
under an application-defined OCI artifact type, and Sigstore Cosign can verify a signed blob plus
its bound digest. Those established boundaries favor a transport-neutral local unit rather than a
Samsarix-specific registry or signing protocol.

Agent Ethics now provides a strict `PolicyDeployment`: one deterministic JSON document with a
complete policy, optional complete contract, and mandatory lock derived from both. One 4 MiB
bounded read rejects duplicates, structural abuse, invalid nested formats, and internal drift.
Atomic output refuses implicit or concurrently won targets. CLI create/verify, a self-contained
schema, `PolicyRuntime.from_deployment`, and `activate_deployment` make the same unit usable from CI
through restart and live promotion. A checked-in tool-call deployment must equal freshly loaded
source artifacts on every test run.

The deployment includes full policy content and is not a signature. Repository review, OCI
repository/digest verification, Sigstore identity, durable desired state, authentication,
promotion approval, replication, and multi-host convergence remain external responsibilities.

## Implemented gap: privacy-aware evaluation explanations

Matched rule IDs and authored reasons explain successful branches but do not show why other rules
missed. OPA provides structured evaluation traces and separately warns that decision-log inputs can
contain sensitive data requiring masking.

Agent Ethics now uses the production evaluator to emit a smaller `PolicyExplanation`: each rule
and condition is marked matched, not matched, or short-circuited without retaining input, policy
values, `$ref` targets, descriptions, or messages. The report identifies decisive/default outcome
provenance, exact policy content, and the optional context-contract fingerprint. CLI, engine, gate,
and bound-gate entry points share one schema and behavior.

This improves trusted operator debugging without becoming a general trace engine. Field paths,
operators, rule metadata, outcomes, and statuses remain visible and can be queried repeatedly as an
authorization oracle, so explanations are not suitable for unauthenticated production exposure.

## Implemented gap: layered policy ownership

One application policy is sufficient for a prototype but forces organization guardrails and
application permissions into the same ownership unit. Cedar authorization combines matching
policies with forbid-overrides behavior, Verified Permissions groups validated policies in an
application or tenant policy store, and OPA recommends central aggregation when policy comes from
multiple sources.

Agent Ethics now provides a bounded central composition step rather than a runtime policy store.
It concatenates 1-32 ordered validated sources only when source IDs and all rule IDs are unique and
every source shares one default effect. The output is an ordinary `Policy`, so existing gates,
regression suites, coverage, lint, comparison, fingerprints, and audit records need no alternate
runtime path. A versioned report records each source fingerprint and rule count without copying
paths, descriptions, messages, rules, conditions, or values.

The bundled support-agent case composes organization tool guardrails with application permissions
into the existing twelve-rule baseline; its fourteen-case suite reaches 100% rule coverage across
allow, deny, and review. This proves deterministic build-time layering, not remote distribution,
policy signing, tenant selection, author authentication, hot reload, or source migration.

## Implemented gap: authenticated deployment freshness

Coherent tool-gate deployments prevent mixed policy/catalog reads but do not authenticate bytes
received through storage or delivery. Current primary-source guidance separates those concerns:

- [OPA signed bundles](https://www.openpolicyagent.org/docs/management-bundles) verify configured
  key identity/scope and complete bundle content before activation, retaining the existing bundle
  when verification fails.
- [The Update Framework specification](https://theupdateframework.github.io/specification/)
  requires both monotonic version checks and expiration to detect rollback and freeze attacks.
- [Sigstore blob verification](https://docs.sigstore.dev/cosign/verifying/verify/) binds an exact
  blob to an expected certificate identity and issuer when public identity is required.

Agent Ethics now provides a narrower zero-dependency symmetric option:
`ToolGateDeploymentEnvelope` authenticates the complete deployment fingerprint and bytes together
with a key ID, exact target audience, positive sequence, and at most 30-day issuance/expiry window.
A bounded caller-owned keyring supports rotation. Verification rejects a stale caller-supplied
minimum sequence, future issuance, expiry, audience mismatch, untrusted key, or any MAC/content
change. `ToolGate` and `ToolDispatcher` authenticate again immediately before binding so a cached
verification is not silently reused as current authorization.

This is not a generic signing or distribution service. Every HMAC verifier can mint envelopes;
trusted clock, durable highest-sequence state, out-of-band key delivery/revocation, asymmetric
author identity, transport, and multi-host convergence remain application or release-system
responsibilities.
