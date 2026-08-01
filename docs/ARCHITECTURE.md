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
- `approval.py`: immutable approval records and bounded exact-call fingerprints.
- `provenance.py`: canonical, domain-separated policy and context-contract fingerprints.
- `deployment.py`: strict immutable deployment locks and exact artifact verification.
- `policy_deployment.py`: complete single-file enforcement units and internal lock verification.
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
built-in JSONL sink is local best effort (`append` plus `fsync`), not an immutable or cross-process
ordered ledger. A caller-owned sink receives the same frozen record, runs once before authorization,
and owns transport, retries, idempotency, and durable retention.

### Enforcement remains local and immediate

`ToolGate` closes the common integration gap between receiving a decision and invoking an
in-process tool. It evaluates a detached context, writes the optional audit record, and calls a
callback with the evaluated detached arguments only for `allow`. Deny and review outcomes are
distinct typed exceptions.
Applications with durable approval workflows store an exact-call fingerprint with pending-call
state. On resume, `ToolGate` verifies a structured approval against the normalized call before
policy evaluation, audit delivery, or callback execution, then re-evaluates fresh trusted facts.
The fingerprint binds the framework call ID, context-contract version, tool name, arguments,
canonical capabilities, and actor. It intentionally excludes general runtime context so current
authorization and risk facts can be re-read.

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
- **Filesystem/audit operator** owns access control, transport, idempotency, rotation, retention,
  backups, and tamper detection for audit destinations.

## Distribution

The smallest distribution is a Python wheel and source distribution with console entry point.
Publishing is owner-gated. A hosted service would add authentication, tenancy, availability,
privacy, and cost risks without improving the repository's core evidence-backed use case.
