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

### `PolicyEngine(policy).evaluate(context) -> Decision`

Evaluates every rule deterministically. Raises `InputValidationError` when the context is not a
bounded JSON object and `EvaluationError` if an operator cannot safely evaluate the supplied types
or a `$ref` is missing. Construction computes `policy_fingerprint` once for reuse by every
decision.

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

### `fingerprint_policy(policy) -> str`

Returns the authoritative `v1:sha256:<hex>` fingerprint of a validated `Policy`. The canonical
payload includes every serialized policy field and a fingerprint-version domain separator. JSON
object keys are sorted; array order is retained, so rule and condition order remain part of exact
provenance. Serialization streams through the hash without building a second encoded byte buffer.
`PolicyEngine`, `ToolGate`, and `BoundToolGate` expose the same precomputed value as
`policy_fingerprint`; callers should use this helper instead of implementing their own serializer.

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

### `ToolGate(policy, *, audit_log=None, audit_sink=None)`

Provides a fail-closed boundary immediately before an in-process side effect:

- `bind(tool_name, *, capabilities=()) -> BoundToolGate` validates and freezes trusted
  registration metadata once;
- `evaluate(...) -> Decision` evaluates the normalized call and optionally appends audit metadata;
- `enforce(...) -> Decision` returns only an allow decision, otherwise raising a typed block;
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
`fingerprint(tool_call_id, arguments, *, actor=None)`, `evaluate`, `enforce`, `execute`, and
`execute_async`. The latter four accept the same actor, context, call-ID, and approval keywords as
`ToolGate`, but take only arguments (and an executor where applicable).

Use a trusted application registry to select a binding. This prevents model or protocol payloads
from downgrading capability labels, but it does not establish that remote tool metadata is honest.

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

### `get_policy_schema()`, `get_policy_test_schema()`, `get_policy_comparison_schema()`, `get_policy_coverage_schema()`, `get_policy_lint_schema()`, `get_tool_context_schema()`, `get_tool_approval_schema()`, and `get_audit_record_schema()`

Return fresh dictionaries containing the bundled Draft 2020-12 schemas for policies, regression
suites, comparison, coverage, and lint reports, the normalized tool-call context, bound approval
records, and metadata-only audit records. These calls perform no network access and callers may
mutate the returned value without changing future calls.

### `load_policy_test_suite(path) -> PolicyTestSuite`

Loads a UTF-8 JSON suite with a 4 MiB byte limit and the shared JSON structural limits. Suites
contain 1-1,000 uniquely named cases. Raises `PolicyTestValidationError` for malformed suites.

### `run_policy_tests(policy, suite) -> PolicyTestReport`

Evaluates every case and records `PolicyTestStatus.PASS`, `FAIL`, or `ERROR`. A report includes
operator-authored policy identity, its exact policy fingerprint, counts, expected and actual
outcomes, matched rule IDs, assertion messages, and evaluation errors. It deliberately excludes
every raw case input. `successful` is true only when all cases pass.

`PolicyTestCase`, `PolicyTestSuite`, `PolicyTestResult`, and `PolicyTestReport` are frozen public
models with JSON-serializable `to_dict()` methods.

## Policy authoring diagnostics

### `lint_policy(policy, *, fail_on=PolicyLintSeverity.SECURITY_WARNING) -> PolicyLintReport`

Returns stable, value-minimized findings for a validated policy. `fail_on` accepts a
`PolicyLintSeverity` or `None`; `passed` is false when a finding at or above the selected severity
exists. `None` reports without blocking. The report includes `POLICY_LINT_VERSION` (currently `1`),
policy identity/fingerprint, severity counts, blocking count, and frozen `PolicyLintFinding`
objects with a `PolicyLintCode`, rule ID, and zero-based condition indices.

The analyzer reports default/unconditional allow, provably contradictory same-field conditions,
semantically duplicate conditions, and missing authored messages. It does not serialize condition
values or rule messages, infer an application schema, or guess about dynamic `$ref` equality.

The CLI equivalent is `samsarix-ethics lint POLICY --fail-on SEVERITY`. It exits `0` when the
selected gate passes, `1` for blocking findings, and `2` for invalid input or invocation. See
[POLICY_LINTING.md](POLICY_LINTING.md) for stable code definitions and limitations.

## Policy rule coverage

### `measure_policy_coverage(policy, suite, *, threshold=0) -> PolicyCoverageReport`

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

## Policy impact comparison

### `compare_policies(baseline, candidate, suite) -> PolicyComparisonReport`

Evaluates every bounded `PolicyTestSuite` case independently against two policies and returns a
deterministic, input-free report. The suite's expected fields are not used for comparison; the
function directly compares each policy's actual outcome, ordered matched-rule IDs, warning count,
reason messages, and warning messages. Message contents are compared internally but not retained in
the report. Either-side evaluation failures become per-case `error` results rather than being
mistaken for unchanged behavior.

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

`PolicyValidationError`, `PolicyTestValidationError`, `InputValidationError`, `EvaluationError`,
`AuditLogError`, and the tool-call enforcement errors derive from `SamsarixEthicsError`. The base
class and specialized errors are exported from `samsarix_ethics` and defined in
`samsarix_ethics.errors`.

## Compatibility

The supported package API begins at `0.1.0`. The former repository code did not expose an
installable, internally consistent API; its missing imports and placeholder compliance types are
not compatibility targets. Breaking changes before `1.0.0` will be called out in `CHANGELOG.md`.
