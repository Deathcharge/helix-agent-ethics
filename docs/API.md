# API reference

All supported public names are exported from `samsarix_ethics`.

## Loading and evaluating

### `load_policy(path) -> Policy`

Reads a UTF-8 JSON policy with size and structural limits, rejects duplicate keys and invalid
values, and returns an immutable `Policy`. Raises `PolicyValidationError` for caller-correctable
policy failures.

### `load_context(path, *, stdin=None) -> dict[str, Any]`

Loads a bounded JSON object from a file, or from a binary stream when `path` is `None` or `"-"`.
Raises `InputValidationError`.

### `validate_context(value, *, label="evaluation input") -> Mapping[str, Any]`

Validates an in-memory object against the same depth, item-count, string-length, JSON-type, and
finite-number contract used for parsed input. Embedding applications can use it at their own input
boundary. `PolicyEngine.evaluate` calls it automatically.

### `load_context_contract(path) -> ContextContract`

Loads a bounded UTF-8 JSON application contract and returns an immutable `ContextContract`.
Contract files are limited to `MAX_CONTEXT_CONTRACT_BYTES` (256 KiB) and contain at most
`MAX_CONTEXT_CONTRACT_FIELDS` (1,000) declared dotted paths. Malformed contracts raise
`ContextContractValidationError`.

### `validate_policy_context_contract(policy, contract) -> None`

Rejects undeclared policy `field`/`$ref` paths and operator uses that are incompatible with declared
JSON types. `integer` and `number` are compatible; booleans remain distinct. The function returns
`None` after success and raises `ContextContractValidationError` on incompatibility.

### `validate_context_against_contract(context, contract) -> Mapping[str, Any]`

Applies normal bounded JSON validation, then enforces required declared paths, declared types, and
optional array-item types. Undeclared request fields are retained and accepted. Contract failures
raise `InputValidationError` and must be treated as non-authorization.

`ContextContract.from_dict(...)` and `.to_dict()` provide strict in-memory parsing and canonical
serialization. `ContextFieldType` contains `array`, `boolean`, `integer`, `null`, `number`,
`object`, and `string`. See [CONTEXT_CONTRACTS.md](CONTEXT_CONTRACTS.md).

### `PolicyEngine(policy, *, context_contract=None, deployment_lock=None).evaluate(context) -> Decision`

Evaluates every rule deterministically. Raises `InputValidationError` when the context is not a
bounded JSON object and `EvaluationError` if an operator cannot safely evaluate the supplied types
or a `$ref` is missing. Construction computes `policy_fingerprint` once for reuse by every
decision.

When a contract is supplied, construction validates policy compatibility and every evaluation
enforces the contract before rule matching. The immutable contract and its canonical fingerprint
are exposed as `engine.context_contract` and `engine.context_contract_fingerprint`. When a
`DeploymentLock` is supplied, construction verifies exact policy and contract identity/content
before evaluation and exposes it as `engine.deployment_lock`.

### `PolicyEngine(policy).evaluate_many(contexts) -> tuple[Decision, ...]`

Evaluates up to `MAX_BATCH_ITEMS` (1,000) contexts in input order. The first malformed context
raises `InputValidationError` with its zero-based batch index; policy evaluation errors still fail
closed. An empty batch returns an empty tuple.

`Decision` fields:

| Field | Meaning |
| --- | --- |
| `decision_id` | UUID generated for this evaluation |
| `evaluated_at` | UTC ISO 8601 timestamp |
| `policy_id`, `policy_version` | operator-authored policy identity labels |
| `policy_fingerprint` | exact canonical policy content used, as `v1:sha256:<hex>` |
| `outcome` | `Outcome.ALLOW`, `DENY`, or `REVIEW` |
| `allowed` | true only for `ALLOW` |
| `matched_rules` | matching rule IDs in priority/ID order |
| `warnings` | messages from matched warning rules |
| `reasons` | messages that determined the outcome |
| `evaluated_rules` | total rule count |

`Decision.to_dict()` returns a JSON-serializable dictionary and still excludes the raw input.

### `PolicyEngine(...).explain(context) -> PolicyExplanation`

Uses the same bounded validation, context contract, deployment lock, short-circuit condition
evaluation, error behavior, precedence, and default as `evaluate`. The deterministic report binds
the policy fingerprint and optional context-contract fingerprint and records rule/condition status
without input, condition values, `$ref` targets, descriptions, messages, UUIDs, or timestamps.

`PolicyExplanation.rules` contains declaration-ordered frozen `RuleExplanation` values. Each has
frozen `ConditionExplanation` entries with `MATCHED`, `NOT_MATCHED`, or `NOT_EVALUATED` status.
Matched rule IDs retain normal priority/ID order; `decisive_rule_ids` identifies matches whose
allow/deny/review effect supplied the outcome. `default_applied` is true when no decisive rule
matched. See [POLICY_EXPLANATIONS.md](POLICY_EXPLANATIONS.md).

### `fingerprint_policy(policy) -> str`

Returns the authoritative `v1:sha256:<hex>` fingerprint of a validated `Policy`. The canonical
payload includes every serialized policy field and a fingerprint-version domain separator. JSON
object keys are sorted; array order is retained, so rule and condition order remain part of exact
provenance. Serialization streams through the hash without building a second encoded byte buffer.
`PolicyEngine`, `ToolGate`, and `BoundToolGate` expose the same precomputed value as
`policy_fingerprint`; callers should use this helper instead of implementing their own serializer.

### `fingerprint_context_contract(contract) -> str`

Returns the authoritative `v1:sha256:<hex>` fingerprint for a validated `ContextContract`.
Canonical JSON uses sorted object keys, retains field semantics after strict model normalization,
and includes a context-contract-specific fingerprint-version domain separator. The textual format
matches policy fingerprints, but the distinct canonical domain prevents cross-artifact reuse.

## Exact deployment locks

### `create_deployment_lock(policy, context_contract=None) -> DeploymentLock`

Creates a frozen version 1 artifact containing policy ID, version, and canonical fingerprint plus
the same metadata for an optional context contract. `DeploymentLock.to_dict()` returns the strict
JSON shape; `DeploymentLock.from_dict(value)` validates that shape without claiming the referenced
artifacts match.

### `verify_deployment_lock(lock, policy, context_contract=None) -> None`

Recomputes canonical metadata and rejects any ID, version, fingerprint, or contract-presence
mismatch with `DeploymentLockValidationError`. Comparisons use constant-time digest comparison.
`PolicyEngine` and `ToolGate` accept the same optional lock and verify it at construction.

### `load_deployment_lock(path) -> DeploymentLock`

Loads a strict UTF-8 JSON lock with the 64 KiB `MAX_DEPLOYMENT_LOCK_BYTES` limit and shared JSON
structural limits. File and model errors are reported as `DeploymentLockValidationError`. See
[DEPLOYMENT_LOCKS.md](DEPLOYMENT_LOCKS.md) for the rollout and trust model.

## Single-file policy deployments

### `create_policy_deployment(policy, context_contract=None) -> PolicyDeployment`

Creates an immutable version 1 deployment containing the complete policy, optional complete
contract, and a newly derived mandatory `DeploymentLock`. Incorrect Python argument types raise
`TypeError`. `PolicyDeployment.to_dict()` returns a fresh complete JSON document;
`PolicyDeployment.from_dict(value)` strictly parses all nested models and raises
`PolicyDeploymentValidationError` unless the embedded lock exactly matches them.

### `load_policy_deployment(path) -> PolicyDeployment`

Reads one UTF-8 JSON object under the 4 MiB `MAX_POLICY_DEPLOYMENT_BYTES` limit, shared structural
limits, and duplicate-key rejection, then parses and verifies it. A single read prevents mixed
policy/contract/lock snapshots during local rollout. File, nested-model, and lock failures are
reported as `PolicyDeploymentValidationError`.

### `write_policy_deployment(path, deployment, *, force=False) -> Path`

Serializes the complete deployment deterministically, flushes a temporary file, and atomically
installs it. It refuses an existing or concurrently won target unless `force=True`; forced output
uses atomic replacement. The parent directory must already exist.

`samsarix-ethics deployment create/verify` exposes the same workflow with value-minimized text or
JSON metadata, while `check` and `explain` can consume the deployment directly with
`--deployment`. Those evaluation commands reject separate contract or lock arguments in
deployment mode. The CLI reports only exact artifact metadata and lock status, not policy content.
The deployment proves internal equality, not authorship, freshness, transport security, or
approval. See
[POLICY_DEPLOYMENTS.md](POLICY_DEPLOYMENTS.md).

## Atomic live policy runtime

### `PolicyRuntime(policy, *, context_contract=None, deployment_lock=None)`

Constructs generation `1` from one complete enforcement configuration. Construction has the same
policy/contract compatibility and exact deployment-lock checks as `PolicyEngine`. `evaluate`,
`explain`, and the `policy`, fingerprint, contract, and lock properties mirror the engine API.
`evaluate_many` captures one generation for the whole bounded batch.

`PolicyRuntime.from_deployment(deployment)` constructs generation `1` from a verified
`PolicyDeployment`; `activate_deployment(deployment, expected_generation=None)` activates one
through the same compare-and-swap, last-known-good path.

Every call captures one immutable engine under a short lock and evaluates after releasing it. An
in-flight call therefore finishes on its original generation while later calls can use a newly
activated generation.

### `PolicyRuntime.activate(policy, *, context_contract=None, deployment_lock=None, expected_generation=None) -> PolicyRuntimeStatus`

Builds and validates the complete candidate before acquiring the live-state lock, then swaps the
policy, contract, lock, and fingerprints together. Candidate validation/lock errors leave the last
successful generation untouched. A supplied positive `expected_generation` is compared under the
same lock; a stale value raises `PolicyActivationError` without activation. Every successful
activation increments the process-local generation, including rollback to retained prior
artifacts.

### `PolicyRuntime.status -> PolicyRuntimeStatus`

Returns one coherent frozen snapshot with `POLICY_RUNTIME_STATUS_VERSION` (currently `1`),
generation, UTC activation time, exact policy identity/fingerprint, optional exact contract
identity/fingerprint, and `deployment_lock_verified`. `to_dict()` returns the bundled schema shape
without policy content, action input, decisions, or errors. See
[POLICY_RUNTIME.md](POLICY_RUNTIME.md) for concurrency, rollback, and control-plane boundaries.

### `write_policy(path, policy, *, force=False) -> Path`

Atomically writes a validated `Policy` as UTF-8 JSON and returns the resolved output path. It
refuses to overwrite an existing path unless `force=True` and requires the parent directory to
exist. Raises `PolicyValidationError` for caller-correctable filesystem failures.

## Layered policy composition

### `compose_policies(policies, *, policy_id, policy_version, description="") -> PolicyComposition`

Combines 1-`MAX_COMPOSED_POLICIES` (32) validated policies in supplied order. Source IDs and all
rule IDs must be unique, all sources must share one `default_effect`, and the result must remain
within the normal 1,000-rule, 1 MiB serialized, and structural policy limits. Violations raise
`PolicyCompositionError`; incorrect Python argument types raise `TypeError`.

`PolicyComposition.policy` is an ordinary immutable `Policy`, so it can immediately enter
`PolicyEngine`, `ToolGate`, lint, regression, coverage, and comparison workflows.
`PolicyComposition.sources` is an ordered tuple of frozen `PolicyCompositionSource` records.
`policy_fingerprint` exposes the target's canonical fingerprint. `to_dict()` returns a versioned
report with approved metadata including the target default effect, target/source IDs, versions,
fingerprints, and rule counts. It omits paths, descriptions, rules, conditions, messages, and
condition values.

The CLI equivalent is `samsarix-ethics compose --id ... --version ... --policy SOURCE ...
--output TARGET`. Output replacement requires `--force`. See
[POLICY_COMPOSITION.md](POLICY_COMPOSITION.md) for the complete contract and support-agent example.

## Shadow policy rollout

### `PolicyShadowEvaluator(baseline, candidate, *, context_contract=None).evaluate(context) -> PolicyShadowEvaluation`

Validates and detaches one bounded JSON context, evaluates the baseline first, and evaluates the
candidate only after the baseline succeeds. Baseline input/evaluation errors propagate fail closed.
A candidate `SamsarixEthicsError` becomes `status = PolicyShadowStatus.ERROR` telemetry without
replacing the baseline decision; unexpected exceptions propagate.
When supplied, one shared context contract validates both policies at construction and both engine
evaluations. Baseline contract input errors propagate fail closed before candidate evaluation;
candidate policy evaluation errors retain the existing observational telemetry behavior.

`PolicyShadowEvaluation.authoritative_decision` is the complete baseline `Decision` that the
application may enforce. `candidate_decision` is a complete observational `Decision` after success
or `None` after a candidate-domain error. `status` is `UNCHANGED`, `CHANGED`, or `ERROR`; `changes`
contains `PolicyShadowChange` labels for outcome, matched rules, warning count, reason messages,
and warning messages. `authorization_changed` is true exactly when the outcome changed.

`candidate` is the frozen input-free `PolicyShadowSnapshot`. It always retains candidate policy
ID, version, and exact fingerprint. A successful snapshot also carries decision ID, evaluation
time, outcome, matched-rule IDs, warning count, and evaluated-rule count. An error snapshot carries
the bounded engine error while unavailable decision fields are null. Both snapshot forms include
the monotonic engine-only `evaluation_duration_ns`; candidate errors retain time spent before the
failure.

`to_dict()` returns the `POLICY_SHADOW_VERSION` (currently `1`) report with a successful baseline
snapshot and either a successful candidate snapshot or a candidate-error snapshot. It excludes the
complete input and all reason/warning text; those message values are compared only in memory. The
synchronous second evaluation may add latency and resource use. Sampling, telemetry delivery,
promotion, and rollback remain caller responsibilities. See
[POLICY_SHADOWING.md](POLICY_SHADOWING.md).

## Tool-call enforcement

### `fingerprint_tool_call(tool_call_id, tool_name, arguments, *, capabilities=(), actor=None)`

Returns a `v1:sha256:<hex>` fingerprint over the normalized framework call ID, tool-context
version, tool name, validated arguments, canonical capability list, and actor. Canonical input is
streamed through the hash and limited to `MAX_TOOL_CALL_FINGERPRINT_BYTES` (1 MiB). Invalid or
oversized calls raise `InputValidationError`. Runtime context is deliberately excluded so fresh
authentication, risk, and environment facts can be re-read before execution.

### `ToolCallApproval(tool_call_id, approved, tool_call_fingerprint)`

A frozen versioned record that binds an approve/deny result to one framework call ID and one tool
fingerprint. `from_dict(value)` strictly parses the bundled JSON shape and `to_dict()` returns a
detached value. Parsing validates structure only; applications must authenticate the reviewer and
load the fingerprint from protected server-side pending-call state.

### `build_tool_context(tool_name, arguments, *, capabilities=(), actor=None, context=None, tool_call_id=None, approval=None)`

Builds a detached, bounded JSON context using the versioned shape documented in
[TOOL_CALLS.md](TOOL_CALLS.md). Tool and capability identifiers are 1-128 characters; each call
may declare up to `MAX_TOOL_CAPABILITIES` (64) unique capabilities. The returned context uses
`tool_context_version = TOOL_CONTEXT_VERSION` (currently `1`), uses
`action.kind = "tool_call"`, and never retains the caller's mutable dictionaries. When an approval
is supplied, the current framework `tool_call_id` is required. The builder recomputes the
fingerprint with constant-time comparisons of both ID and digest before adding the structured
approval to `context`. A `tool_call_id` without approval is rejected rather than silently ignored.
The `context.approval` field is reserved and cannot be injected through ordinary context metadata.

### `ToolGate(policy_or_runtime, *, context_contract=None, deployment_lock=None, audit_log=None, audit_sink=None)`

Provides a fail-closed boundary immediately before an in-process side effect:

When `context_contract` is supplied, gate construction validates the policy and every normalized
tool-call context is checked before evaluation. When `deployment_lock` is supplied, exact artifact
verification occurs during construction. `ToolGate` and `BoundToolGate` expose
`context_contract`, `context_contract_fingerprint`, and `deployment_lock`.

Passing a `PolicyRuntime` makes the gate and all existing bindings follow successful atomic
activations. Contract and lock arguments must then be configured on the runtime rather than passed
again. `runtime_status` returns coherent live-generation metadata for a runtime-backed gate and
`None` for a static gate.

`ToolGate.explain(...)` normalizes the same call fields and returns a `PolicyExplanation` without
authorizing, executing, or emitting an authorization audit record. `BoundToolGate.explain(...)`
uses its immutable registered tool name and capabilities.

- `bind(tool_name, *, capabilities=()) -> BoundToolGate` validates and freezes trusted
  registration metadata once;
- `prepare(...) -> PreparedToolCall` validates, detaches, and recursively freezes one call for
  immediate single-generation batch authorization;
- `evaluate(...) -> Decision` evaluates the normalized call and optionally appends audit metadata;
- `evaluate_many(calls) -> tuple[Decision, ...]` validates a bounded gate-specific prepared batch,
  pins one runtime generation, then emits audit records in input order;
- `enforce(...) -> Decision` returns only an allow decision, otherwise raising a typed block;
- `enforce_many(calls) -> tuple[Decision, ...]` returns only when every prepared call is allowed,
  otherwise raising the first input-ordered typed block after the full batch was evaluated/audited;
- `execute(..., executor, ...) -> ToolExecutionResult[T]` invokes a callback with the detached,
  evaluated argument dictionary only after allow; it rejects coroutine functions and async
  callable objects, which must use `execute_async`;
- `await execute_async(..., executor, ...) -> ToolExecutionResult[T]` does the same for an async
  callback.

Each method accepts the optional `tool_call_id=...` and `approval=ToolCallApproval(...)` keywords;
they must be supplied together. An ID or fingerprint mismatch raises `InputValidationError` before
a decision, audit record, or callback exists. The gate does not authenticate, expire, or consume
approvals; applications own those stateful responsibilities.

`ToolExecutionResult` contains the authorizing `decision` and callback `value`. A deny raises
`ToolCallDeniedError`; review raises `ToolCallReviewRequiredError`. Both derive from
`ToolCallBlockedError`, retain the metadata-only `decision`, and omit tool arguments from their
messages. If configured audit persistence fails, `AuditLogError` propagates before execution.
`audit_log` and `audit_sink` are mutually exclusive. A custom sink must be a synchronous callable
that accepts one `AuditRecord` and returns `None`; any other return or raised exception prevents the
decision from authorizing a callback. The package invokes the sink exactly once and never retries.

### `BoundToolGate`

The frozen object returned by `ToolGate.bind(...)`. Its `tool_name` and canonical immutable
`capabilities` tuple cannot be supplied or changed per invocation. It exposes `gate` and `policy`
properties, the gate's `policy_fingerprint`, plus
`runtime_status`,
`fingerprint(tool_call_id, arguments, *, actor=None)`, `prepare`, `evaluate`, `enforce`, `explain`,
`execute`, and `execute_async`. The latter six accept the same actor, context, call-ID, and approval keywords as
`ToolGate`, but take only arguments (and an executor where applicable).

Use a trusted application registry to select a binding. This prevents model or protocol payloads
from downgrading capability labels, but it does not establish that remote tool metadata is honest.

### `PreparedToolCall`

The frozen gate-specific object returned by `ToolGate.prepare(...)` or
`BoundToolGate.prepare(...)`. `tool_name` and `capabilities` expose immutable normalized metadata;
`arguments` returns a fresh detached dictionary on every access. Its constructor is intentionally
unavailable. A prepared call retains normalized actor/context/approval facts internally for
immediate `evaluate_many` or `enforce_many` use; it is not a durable authorization token and must
not be reused after those facts can become stale. A batch rejects repeated object identities and
repeated approval `tool_call_id` values; applications still enforce replay protection across
batches. `MAX_TOOL_BATCH_ITEMS` is 1,000.

## Models

- `Policy.from_dict(value)` and `Policy.to_dict()`
- `PolicyRule.from_dict(value, index=...)` and `PolicyRule.to_dict()`
- `PolicyCondition.from_dict(value, location=...)` and `PolicyCondition.to_dict()`
- `Effect`: `allow`, `deny`, `review`, `warn`, `audit`
- `Outcome`: `allow`, `deny`, `review`
- `ToolCallApproval.from_dict(value)` and `ToolCallApproval.to_dict()`

Models are frozen dataclasses. Policy condition arrays and objects are recursively frozen, and
`to_dict()` returns fresh JSON containers, so retaining or serializing a source document cannot
mutate a live policy. Construct policies through `from_dict` or `load_policy` so validation always
runs.

## Schemas and policy regression tests

### `get_policy_schema()`, `get_context_contract_schema()`, and other schema accessors

Return fresh dictionaries containing the bundled Draft 2020-12 schemas for policies, application
context contracts, deployment locks, policy deployments, regression suites, comparison,
composition, coverage, explanation, lint, runtime-status, and shadow reports, the normalized
tool-call context, bound approval records, and metadata-only audit records. The other accessors are
`get_policy_test_schema`, `get_policy_comparison_schema`, `get_policy_composition_schema`,
`get_policy_coverage_schema`, `get_policy_explanation_schema`, `get_policy_lint_schema`,
`get_policy_runtime_status_schema`, `get_policy_shadow_schema`, `get_deployment_lock_schema`,
`get_policy_deployment_schema`, `get_tool_context_schema`, `get_tool_approval_schema`, and
`get_audit_record_schema`. These calls perform no network access and callers may mutate a returned
value without changing future calls.

### `load_policy_test_suite(path) -> PolicyTestSuite`

Loads a UTF-8 JSON suite with a 4 MiB byte limit and the shared JSON structural limits. Suites
contain 1-1,000 uniquely named cases. Raises `PolicyTestValidationError` for malformed suites.

### `run_policy_tests(policy, suite, *, context_contract=None) -> PolicyTestReport`

Evaluates every case and records `PolicyTestStatus.PASS`, `FAIL`, or `ERROR`. A report includes
operator-authored policy identity, its exact policy fingerprint, counts, expected and actual
outcomes, matched rule IDs, assertion messages, and evaluation errors. It deliberately excludes
every raw case input. `successful` is true only when all cases pass.

`PolicyTestCase`, `PolicyTestSuite`, `PolicyTestResult`, and `PolicyTestReport` are frozen public
models with JSON-serializable `to_dict()` methods.
An optional context contract is validated when the engine is constructed and applied to every
case. Per-case contract input failures are input-free `ERROR` results.

## Policy authoring diagnostics

### `lint_policy(policy, *, fail_on=PolicyLintSeverity.SECURITY_WARNING) -> PolicyLintReport`

Returns stable, value-minimized findings for a validated policy. `fail_on` accepts a
`PolicyLintSeverity` or `None`; `passed` is false when a finding at or above the selected severity
exists. `None` reports without blocking. The report includes `POLICY_LINT_VERSION` (currently `1`),
policy identity/fingerprint, severity counts, blocking count, and frozen `PolicyLintFinding`
objects with a `PolicyLintCode`, rule ID, and zero-based condition indices.

The analyzer reports default/unconditional allow, provably contradictory same-field conditions,
semantically duplicate conditions, and missing authored messages. It does not serialize condition
values or rule messages, infer an application schema, or guess about dynamic `$ref` equality. Use
an explicit `ContextContract` for supported path/type validation; the linter itself remains
contract-independent.

The CLI equivalent is `samsarix-ethics lint POLICY --fail-on SEVERITY`. It exits `0` when the
selected gate passes, `1` for blocking findings, and `2` for invalid input or invocation. See
[POLICY_LINTING.md](POLICY_LINTING.md) for stable code definitions and limitations.

## Policy rule coverage

### `measure_policy_coverage(policy, suite, *, threshold=0, context_contract=None) -> PolicyCoverageReport`

Evaluates each bounded suite input against one policy and records which rule IDs matched. The
integer threshold must be from `0` to `100`. `threshold_met` is true only when exact covered/total
counts meet that threshold and every case evaluated successfully. `complete` requires every rule
to be covered and no errors. The suite's `expected_*` assertions are not checked; use
`run_policy_tests` for correctness. With zero policy rules, rule coverage is vacuously 100%.

The frozen report includes `POLICY_COVERAGE_VERSION` (currently `1`), suite and policy identity,
the exact policy fingerprint, declaration-ordered covered/uncovered IDs, rule counts, a two-decimal
display percentage, allow/deny/review case counts, and input-free `PolicyCoverageError` objects.
Overridden authorization rules and warning rules count as covered when they match. Default outcomes
count as evaluated cases but do not cover a rule.

The CLI equivalent is `samsarix-ethics coverage --policy ... SUITE --threshold N`. It exits `0`
when the threshold is met, `1` when it is missed or evaluation errors occur, and `2` for invalid
input or invocation. Coverage is branch evidence over supplied cases, not proof that all condition
boundaries or possible inputs were exercised. See [POLICY_COVERAGE.md](POLICY_COVERAGE.md).
An optional shared context contract applies the same production fact checks to every coverage case;
contract input errors fail the threshold and remain input-free.

## Policy impact comparison

### `compare_policies(baseline, candidate, suite, *, context_contract=None) -> PolicyComparisonReport`

Evaluates every bounded `PolicyTestSuite` case independently against two policies and returns a
deterministic, input-free report. The suite's expected fields are not used for comparison; the
function directly compares each policy's actual outcome, ordered matched-rule IDs, warning count,
reason messages, and warning messages. Message contents are compared internally but not retained in
the report. Either-side evaluation failures become per-case `error` results rather than being
mistaken for unchanged behavior.
When supplied, one shared contract must accept both policies at construction and is enforced for
both evaluations of every case. Contract input failures are per-case errors.

The report uses `comparison_version = POLICY_COMPARISON_VERSION` (currently `1`) and includes both
policies' ID, version, and exact fingerprint. Aggregate properties are:

| Property | Meaning |
| --- | --- |
| `unchanged` | cases with equal outcome, matched rules, warning count, reasons, and warnings |
| `changed` | cases where one or more observable fields differ |
| `authorization_changes` | changed cases whose outcome differs |
| `metadata_only_changes` | equal-outcome cases with different rule, warning, or message metadata |
| `errors` | cases where either policy failed closed |
| `identical` | true only when `changed == 0` and `errors == 0` |

Each `PolicyComparisonResult` has a `PolicyComparisonStatus`, an ordered tuple of
`PolicyComparisonChange` values, and input-free baseline/candidate `PolicyComparisonSnapshot`
objects. `to_dict()` returns detached JSON values. It excludes fixture inputs, decision UUIDs,
timestamps, reason text, and warning text.

The CLI equivalent is `samsarix-ethics compare --baseline ... --candidate ... SUITE`. It exits `0`
only for identical observed behavior, `1` for changes or errors, and `2` for invalid invocation or
input. See [POLICY_COMPARISON.md](POLICY_COMPARISON.md) for rollout guidance and coverage limits.

## Audit records and sinks

### `AuditRecord.from_decision(decision) -> AuditRecord`

Creates a frozen `audit_record_version = AUDIT_RECORD_VERSION` record (currently version `1`) with
decision/policy identity, the exact policy fingerprint, evaluation time, outcome, matched rule IDs,
and warning count. Raw input, reasons, and warning text are absent. `to_dict()` returns a detached
JSON-compatible dictionary.

### `AuditSink`

A structural typing protocol for a synchronous callable with the signature
`sink(record: AuditRecord) -> None`. Normal `None` return means delivery succeeded. `ToolGate`
converts an ordinary sink exception to `AuditLogError` using only its type name; it does not retry.
An application that retries an uncertain external commit must deduplicate by `decision_id` if its
destination requires exactly-once storage.

### `JsonlAuditSink(path)`

The built-in local sink appends one compact record and calls `fsync`. Its destination parent must
already exist. It is also what `ToolGate(..., audit_log=path)` uses.

### `append_audit_record(path, decision) -> None`

Appends one compact JSONL record and calls `fsync`. The destination's parent must already exist.
This compatibility helper converts the decision to `AuditRecord` and invokes `JsonlAuditSink`.
Raises `AuditLogError` on failure.

## Error hierarchy

`PolicyValidationError`, `PolicyDeploymentValidationError`, `PolicyActivationError`,
`PolicyCompositionError`, `PolicyTestValidationError`, `InputValidationError`, `EvaluationError`,
`AuditLogError`, and the tool-call enforcement errors derive from `SamsarixEthicsError`. The base
class and specialized errors are exported from `samsarix_ethics` and defined in
`samsarix_ethics.errors`.

## Compatibility

The supported package API begins at `0.1.0`. The former repository code did not expose an
installable, internally consistent API; its missing imports and placeholder compliance types are
not compatibility targets. Breaking changes before `1.0.0` will be called out in `CHANGELOG.md`.
