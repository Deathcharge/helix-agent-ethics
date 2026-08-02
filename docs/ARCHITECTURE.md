# Architecture

## Product boundary

Samsarix Agent Ethics is an embedded policy decision point. The caller supplies trusted policy
configuration and an action-context object, receives an explainable decision, and remains
responsible for enforcement immediately before the protected operation.

```text
trusted policy JSON ──> bounded parser ──> immutable Policy ──────────────┐
trusted context contract ─> path/operator check + runtime fact types ────┤
reviewed deployment lock ─> exact artifact verification ─────────────────┤
                                                                         ├─> PolicyEngine ─> Decision
untrusted action JSON ─> bounded parser ─> context object ────────────────┘                  │
                                                                               ├─> optional metadata-only audit sink
                                                                               └─> ToolGate ─> callback or typed block

trusted tool catalog + complete local registry names ─> exact match ─> immutable gate bindings
locked policy deployment + fingerprinted catalog ─> ToolGateDeployment ─> verified bindings
verified bindings + final callback objects ─> ToolDispatcher ─> authorized sequential dispatch

validated policy + optional contract/lock ─> PolicyRuntime generation N ─> live gates
validated complete candidate ─> compare-and-swap atomic activation ──────┘

policy + optional contract ─> mandatory exact lock ─> one PolicyDeployment JSON
one bounded deployment read ─> verified complete artifacts ─> PolicyRuntime

ordered trusted policy sources ─> composition validation ─> ordinary immutable Policy

approved baseline ─> authoritative Decision ───────────────────────────────> caller enforcement
                           └─ same detached input ─> candidate observation ─> minimized telemetry
```

There is no network service, identity provider, database, model provider, or dependency on
the legacy `helix-unified` repository.

## Components

- `models.py`: strict schema validation and immutable policy/decision values.
- `audit.py`: versioned metadata-only records, the caller sink contract, and local JSONL sink.
- `audit_chain.py`: bounded HMAC-SHA-256 chain entries, single-writer sink, and verifier.
- `approval.py`: immutable approval records and bounded exact-call fingerprints.
- `catalog.py`: strict application-owned tool capability catalogs and exact registry matching.
- `provenance.py`: canonical, domain-separated policy, contract, and catalog fingerprints.
- `deployment.py`: strict immutable deployment locks and exact artifact verification.
- `policy_deployment.py`: complete single-file enforcement units and internal lock verification.
- `tool_gate_deployment.py`: coherent policy-and-catalog units with exact catalog pinning.
- `authenticated_deployment.py`: whole-deployment HMAC authentication, audience, and freshness.
- `dispatch.py`: exact callback snapshots and framework-neutral sync/async dispatch.
- `validation.py`: shared bounded JSON validation for parsed and in-memory contexts.
- `contracts.py`: immutable application fact declarations, policy compatibility, and runtime type
  enforcement.
- `engine.py`: dotted-field resolution, typed condition operators, rule matching, and precedence.
- `runtime.py`: last-known-good in-process generations, atomic activation, and coherent status.
- `io.py`: bounded UTF-8 JSON parsing, safe sample generation, and the legacy audit helper.
- `schema.py` and `schemas/`: offline access to versioned Draft 2020-12 contracts.
- `testing.py`: bounded regression suites and input-free aggregate reports.
- `comparison.py`: deterministic, input-free baseline/candidate impact reports.
- `composition.py`: bounded central policy aggregation and value-minimized source provenance.
- `shadow.py`: baseline-authoritative live candidate observation and input-free rollout telemetry.
- `coverage.py`: deterministic, input-free rule and outcome coverage with CI thresholds.
- `diagnostics.py`: stable, value-minimized policy authoring findings and severity gates.
- `explanation.py`: input- and value-free rule/condition evaluation explanations.
- `gate.py`: normalized tool-call contexts, immutable registration bindings, and fail-closed
  sync/async callback enforcement.
- `openai_agents.py`: optional strict `FunctionTool` protection and native approval-flow routing
  without importing the SDK at core package import time.
- `cli.py`: non-interactive commands, rendering, stderr discipline, and exit codes.
- `__init__.py`: deliberate public Python API.

## Key decisions

### Explicit, deterministic facts

The engine evaluates caller-supplied JSON facts and never invokes an LLM. This keeps decisions
reproducible, offline, testable, and cost-free. It also means the caller must supply accurate facts.

### Validation before evaluation

Unknown fields/operators, duplicate IDs, invalid references, malformed JSON, non-finite numbers,
non-JSON in-memory values, and bounded-resource violations are rejected before a decision. Operator
type errors stop the evaluation. An embedding application must treat errors as non-authorization.

An optional application context contract adds a second, explicit layer. Engine construction
rejects undeclared policy paths and incompatible operator/type combinations; evaluation rejects
missing required facts, declared type mismatches, and declared array-item mismatches. Contracts
accept unrelated request fields by design so opaque arguments need not be modeled. They establish
structure, not truth: the application remains responsible for authentic and current facts.
Regression, coverage, comparison, and shadow workflows can pass the same contract into their
internal engines so pre-deployment evidence does not use a weaker fact boundary than production.
Decisions and most report schemas do not embed contract provenance; explanations and runtime
status do. An optional deployment lock
binds exact policy and contract content at engine or gate construction without copying either
artifact into decisions.

Deployment locks use canonical domain-separated fingerprints plus the operator-authored IDs and
versions. Contract presence is exact, so a locked contract cannot be omitted or introduced
silently. Lock verification is an activation precondition for `PolicyEngine`, `ToolGate`, and the
locked CLI decision paths; mismatch raises a typed validation error before authorization. The lock
is deliberately a detached artifact so repository review or an external signing system can protect
the policy, contract, and lock as one deployment set.

A `PolicyDeployment` makes that set one deterministic JSON document. Its embedded lock is mandatory
and is recomputed during parsing, so the complete policy and optional contract cannot drift inside
the unit. Bounded single-read loading avoids observing separately replaced local files; atomic
writing avoids partial output and implicit overwrite. The format carries no timestamps, remote
locations, signatures, or mutable tags, so identical source artifacts produce identical content.
Origin authentication and distribution remain composable external controls such as protected Git,
immutable OCI digests, Sigstore, or an organization release system.

An optional `ToolGateDeploymentEnvelope` authenticates the complete policy-and-catalog deployment
plus a key ID, exact audience, monotonic sequence, and bounded issuance/expiry window. Verification
uses a caller-owned keyring and current trust inputs; gate and dispatcher helpers perform that
verification immediately before registry binding. The symmetric-key design preserves the
zero-runtime-dependency boundary, but every verifier can mint envelopes. Public signer identity,
trusted sequence persistence, clock integrity, remote fetching, and distributed convergence remain
control-plane responsibilities.

### Schemas plus executable examples

The JSON Schemas support editors and generic CI validators; the Python validators remain
authoritative for semantic and aggregate constraints. Policy-test suites evaluate real engine
behavior and separate unmet expectations from evaluation errors. Reports omit raw inputs just as
the audit helper does.

The same bounded suite can evaluate an approved baseline and candidate side by side. Comparison
records outcome changes separately from matched-rule, warning, and explanation metadata changes,
carries both exact policy fingerprints, and treats either-side evaluation failures as errors.
Reason/warning contents are compared but discarded; the report exposes only change labels. It
excludes inputs, decision UUIDs, and timestamps so repeated runs are deterministic. Equality is
scoped to supplied cases and observable decision metadata; it is not whole-language semantic
equivalence.

Coverage evaluates the same bounded cases against one policy, unions successful decisions'
matched-rule IDs, and preserves policy declaration order in covered/uncovered lists. Overridden and
warning rules still count when matched; errored cases get no partial credit and fail the threshold.
Outcome counts make default-only behavior visible, but rule coverage is not path, condition, or
input-space coverage.

Diagnostics operate only on the validated immutable policy. They recognize fixed permissive,
contradictory, duplicate, and missing-explanation shapes; no condition value is copied into a
finding. Same-field literal equality/membership reasoning matches engine JSON equality, including
the distinction between booleans and numbers, while dynamic references are not guessed.

Explanations share the engine's exact validation and short-circuit evaluator. They retain
declaration-ordered rule metadata and condition match/miss/skip status, then apply the same
deny/review/allow/default precedence. They exclude input, policy literals, `$ref` targets, and
messages. This keeps one semantic implementation while providing operator diagnostics, but the
remaining status metadata is still an authorization oracle and belongs behind operator access.

Composition operates on 1-32 validated policies and produces one ordinary policy so the existing
engine, gate, test, coverage, comparison, lint, and audit contracts remain canonical. It preserves
source/rule order, requires unique source and rule IDs, and requires one shared default effect.
The report binds each source and the output to exact fingerprints but excludes paths,
descriptions, rules, messages, conditions, and values. Composition is a trusted build step, not a
runtime loader, remote policy store, signature verifier, or activation protocol.

Shadow evaluation validates and detaches one context, evaluates the approved baseline first, and
runs the candidate only after that baseline succeeds. Baseline errors propagate fail closed.
Candidate domain errors become explicit observational telemetry; unexpected exceptions remain
visible. Offline comparison and live shadowing share one definition of observable change so their
outcome, matched-rule, warning-count, and message-change semantics cannot drift. Shadow reports add
decision IDs and timestamps for live correlation while excluding input and message text. They bind
both policies to exact fingerprints and measure each engine call with a monotonic nanosecond
duration. The synchronous candidate work can add latency and resource use; sampling, queues,
and monitoring are caller-owned control-plane work. A candidate may be promoted through the
in-process atomic runtime after external approval, but remote distribution remains caller-owned.

### Atomic activation keeps the last known good generation

`PolicyRuntime` constructs a complete candidate `PolicyEngine` before acquiring its live-state
lock. Policy/contract compatibility and deployment-lock verification therefore fail before the
current generation can change. Under the lock, optional compare-and-swap checks the expected
generation and one assignment replaces the engine plus its immutable status. A stale deployer gets
`PolicyActivationError`; it never silently overwrites a newer activation.

Evaluation captures an engine reference under the lock and releases it before validation and rule
work. In-flight calls complete on one generation; later calls see the new one. Batches capture once
for whole-batch consistency. Runtime-backed gates reuse that behavior and keep audit sinks and
trusted tool bindings stable across activation. Generation status exposes exact policy/contract
provenance without rules, paths, values, messages, or input.

This lock coordinates threads in one process only. It does not persist desired state, elect a
leader, authenticate a deployer, distribute artifacts, or coordinate hosts. Restart recovery and
multi-process rollout need an external control plane that reconstructs the runtime from protected
last-known-good artifacts.

### Deny and review override allow

The outcome order is `deny > review > allow > default_effect`. This makes guardrail rules
independent of future grants. `warn` and `audit` are descriptive matches, not grants.

### No embedded expression language

The policy language is intentionally smaller than OPA or Cedar. It excludes regex, templates,
dynamic functions, imports, and network lookups to limit injection, denial-of-service, and policy
analysis risk. Cross-field comparison uses the explicit `{"$ref": "path.to.field"}` form.

### Privacy-minimized audit

Raw action context can contain credentials or personal data, so the versioned `AuditRecord` stores
only decision metadata. Each decision and record identifies the complete validated policy content
with a domain-separated, versioned SHA-256 fingerprint; operator-authored policy ID and version
remain human-readable labels. JSON object keys are canonicalized and array order is preserved. The
built-in JSONL sink is local best effort (`append` plus `fsync`). A caller-owned sink receives the
same frozen record, runs once before authorization, and owns transport, retries, idempotency, and
durable retention.

`HmacAuditChainSink` is the optional local integrity layer. It authenticates each record, stream ID,
one-based sequence, and prior MAC using domain-separated HMAC-SHA-256. A verifier recomputes the
complete chain with bounded, duplicate-safe parsing. A separately protected expected head is needed
to detect rollback to an earlier valid prefix. The sink serializes its own threads and rejects an
observed external file change, but does not provide a cross-process lock, remove the check/append
race, identify an individual signer, or protect against an attacker who has the shared key.

### Enforcement remains local and immediate

`ToolGate` closes the common integration gap between receiving a decision and invoking an
in-process tool. It evaluates a detached context, writes the optional audit record, and calls a
callback with the evaluated detached arguments only for `allow`. Deny and review outcomes are
distinct typed exceptions.

For multi-call turns, a gate can recursively freeze normalized contexts as gate-specific
`PreparedToolCall` objects. Batch evaluation first collects every item, rejects foreign gates and
invalid size/type boundaries, then calls the engine/runtime batch primitive once. Contract errors
therefore occur before batch audit delivery, and a runtime captures one generation for all items.
`enforce_many` audits the complete successful evaluation set in order and returns only when every
outcome is allow. Its first typed block retains all metadata-only decisions and the blocked index,
so an adapter does not need to repeat evaluation to build a multi-call review surface. It does not
execute callbacks or make their side effects transactional; framework scheduling remains outside
the base gate boundary. The optional dispatcher below supplies only sequential in-process
scheduling.

`ToolDispatcher` is the optional local scheduling seam for runtimes that want authorization and
callback selection owned by one object. It exact-matches a complete callback mapping to the
catalog, copies the mapping, and retains each final callback object. Single calls authorize before
selection; batches authorize every call before invoking callbacks sequentially. This prevents a
later dictionary or registry replacement from changing the selected reference, but it is not code
identity or semantic attestation. A mutable callable, closure, module global, monkey patch, or
callback that delegates into another registry can still change behavior. Batch execution is not a
transaction and does not provide rollback after a later callback error.
Applications with durable approval workflows store an exact-call fingerprint with pending-call
state. On resume, `ToolGate` verifies a structured approval against the normalized call before
policy evaluation, audit delivery, or callback execution, then re-evaluates fresh trusted facts.
The fingerprint binds the framework call ID, context-contract version, tool name, arguments,
canonical capabilities, and actor. It intentionally excludes general runtime context so current
authorization and risk facts can be re-read.

The optional OpenAI Agents adapter copies one strict top-level `FunctionTool`, combines existing
approval logic, preserves prior input guardrails, and appends Samsarix as the final input guardrail.
Its preflight explanation routes only `review` into the SDK interruption workflow; final
`BoundToolGate.enforce` remains authoritative after approval and emits the audit record. A bounded
thread-safe default or application-owned first-write store retains the pre-interruption exact-call
fingerprint, so same-ID mutation, reconstructed missing state, sticky approval, or unrelated SDK
approval logic cannot mint Samsarix approval evidence. The SDK
passes raw JSON to guardrails before Pydantic callback conversion, so the adapter applies the core
bounded duplicate-safe parser and policy types to raw values. It deliberately rejects namespaces
and agent-as-tool wrappers and cannot intercept hosted, built-in, MCP-hosted, or handoff paths.

## Trust boundaries

- **Policy authors/operators** are trusted to define correct rules and secure policy files.
- **Policy fingerprint** proves exact content equality under the documented v1 serializer; it does
  not prove who authored, approved, distributed, or securely stored that policy.
- **Evaluation input** may be attacker-controlled and is bounded and type-checked.
- **Context contract** is trusted application configuration. It restricts policy-visible path and
  type expectations but neither authenticates facts nor closes the entire input object.
- **Deployment lock** proves the supplied artifacts equal its canonical fingerprints. It does not
  authenticate who created or approved them, make distribution secure, establish freshness, or
  prevent rollback; the deployment system must protect and authenticate the complete artifact set.
- **Embedding application** owns authentication, authorization, fact integrity, enforcement,
  approval expiry and atomic one-time consumption, concurrency, and the protected side effect.
- **Shadow-rollout operator** owns exact baseline/candidate selection, sampling, telemetry
  durability, latency/error budgets, promotion criteria, and rollback. Only the baseline decision
  is authoritative until an independently reviewed deployment changes that role.
- **Tool capability labels** are trusted application facts; model output must not assign its own
  permissions or approval state.
- **Bound approval records** prove only that application-supplied approval evidence matches the
  exact proposed call. The application authenticates the reviewer and protects durable approval
  state against forgery and replay.
- **Bound tool metadata** is application-owned registration state. A `BoundToolGate` freezes the
  name and capabilities used at enforcement; remote protocol annotations remain untrusted hints.
- **Tool catalog operator** owns catalog authorship, review, authenticated distribution, freshness,
  and the complete trusted registry snapshot. Exact matching prevents name-set drift but does not
  prove capability correctness. `ToolDispatcher` additionally freezes callback object selection,
  not code identity, internal state, delegation, or semantics.
- **Filesystem/audit operator** owns access control, transport, idempotency, key custody/rotation,
  external head checkpoints, cross-process writer exclusion, retention, backups, and availability
  for audit destinations.
- **Deployment target operator** owns the authenticated-envelope keyring, expected audience,
  trustworthy clock, highest accepted sequence, key revocation, artifact transport, and immediate
  binding after verification. HMAC proves possession of a shared key, not individual authorship.

## Distribution

The smallest distribution is a Python wheel and source distribution with console entry point.
Publishing is owner-gated. A hosted service would add authentication, tenancy, availability,
privacy, and cost risks without improving the repository's core evidence-backed use case.
