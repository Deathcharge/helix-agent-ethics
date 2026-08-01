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
or a `$ref` is missing.

### `PolicyEngine(policy).evaluate_many(contexts) -> tuple[Decision, ...]`

Evaluates up to `MAX_BATCH_ITEMS` (1,000) contexts in input order. The first malformed context
raises `InputValidationError` with its zero-based batch index; policy evaluation errors still fail
closed. An empty batch returns an empty tuple.

`Decision` fields:

| Field | Meaning |
| --- | --- |
| `decision_id` | UUID generated for this evaluation |
| `evaluated_at` | UTC ISO 8601 timestamp |
| `policy_id`, `policy_version` | exact policy identity used |
| `outcome` | `Outcome.ALLOW`, `DENY`, or `REVIEW` |
| `allowed` | true only for `ALLOW` |
| `matched_rules` | matching rule IDs in priority/ID order |
| `warnings` | messages from matched warning rules |
| `reasons` | messages that determined the outcome |
| `evaluated_rules` | total rule count |

`Decision.to_dict()` returns a JSON-serializable dictionary and still excludes the raw input.

## Tool-call enforcement

### `build_tool_context(tool_name, arguments, *, capabilities=(), actor=None, context=None)`

Builds a detached, bounded JSON context using the versioned shape documented in
[TOOL_CALLS.md](TOOL_CALLS.md). Tool and capability identifiers are 1-128 characters; each call
may declare up to `MAX_TOOL_CAPABILITIES` (64) unique capabilities. The returned context uses
`tool_context_version = TOOL_CONTEXT_VERSION` (currently `1`), uses
`action.kind = "tool_call"`, and never retains the caller's mutable dictionaries.

### `ToolGate(policy, *, audit_log=None, audit_sink=None)`

Provides a fail-closed boundary immediately before an in-process side effect:

- `evaluate(...) -> Decision` evaluates the normalized call and optionally appends audit metadata;
- `enforce(...) -> Decision` returns only an allow decision, otherwise raising a typed block;
- `execute(..., executor, ...) -> ToolExecutionResult[T]` invokes a callback with the detached,
  evaluated argument dictionary only after allow; it rejects coroutine functions and async
  callable objects, which must use `execute_async`;
- `await execute_async(..., executor, ...) -> ToolExecutionResult[T]` does the same for an async
  callback.

`ToolExecutionResult` contains the authorizing `decision` and callback `value`. A deny raises
`ToolCallDeniedError`; review raises `ToolCallReviewRequiredError`. Both derive from
`ToolCallBlockedError`, retain the metadata-only `decision`, and omit tool arguments from their
messages. If configured audit persistence fails, `AuditLogError` propagates before execution.
`audit_log` and `audit_sink` are mutually exclusive. A custom sink must be a synchronous callable
that accepts one `AuditRecord` and returns `None`; any other return or raised exception prevents the
decision from authorizing a callback. The package invokes the sink exactly once and never retries.

## Models

- `Policy.from_dict(value)` and `Policy.to_dict()`
- `PolicyRule.from_dict(value, index=...)` and `PolicyRule.to_dict()`
- `PolicyCondition.from_dict(value, location=...)` and `PolicyCondition.to_dict()`
- `Effect`: `allow`, `deny`, `review`, `warn`, `audit`
- `Outcome`: `allow`, `deny`, `review`

Models are frozen dataclasses. Policy condition arrays and objects are recursively frozen, and
`to_dict()` returns fresh JSON containers, so retaining or serializing a source document cannot
mutate a live policy. Construct policies through `from_dict` or `load_policy` so validation always
runs.

## Schemas and policy regression tests

### `get_policy_schema()`, `get_policy_test_schema()`, `get_tool_context_schema()`, and `get_audit_record_schema()`

Return fresh dictionaries containing the bundled Draft 2020-12 schemas for policies, regression
suites, the normalized tool-call context, and metadata-only audit records. These calls perform no
network access and callers may mutate the returned value without changing future calls.

### `load_policy_test_suite(path) -> PolicyTestSuite`

Loads a UTF-8 JSON suite with a 4 MiB byte limit and the shared JSON structural limits. Suites
contain 1-1,000 uniquely named cases. Raises `PolicyTestValidationError` for malformed suites.

### `run_policy_tests(policy, suite) -> PolicyTestReport`

Evaluates every case and records `PolicyTestStatus.PASS`, `FAIL`, or `ERROR`. A report includes
policy identity, counts, expected and actual outcomes, matched rule IDs, assertion messages, and
evaluation errors. It deliberately excludes every raw case input. `successful` is true only when
all cases pass.

`PolicyTestCase`, `PolicyTestSuite`, `PolicyTestResult`, and `PolicyTestReport` are frozen public
models with JSON-serializable `to_dict()` methods.

## Audit records and sinks

### `AuditRecord.from_decision(decision) -> AuditRecord`

Creates a frozen `audit_record_version = AUDIT_RECORD_VERSION` record (currently version `1`) with
decision/policy identity, evaluation time, outcome, matched rule IDs, and warning count. Raw input,
reasons, and warning text are absent. `to_dict()` returns a detached JSON-compatible dictionary.

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
