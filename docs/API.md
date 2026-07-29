# API reference

All supported public names are exported from `helix_ethics`.

## Loading and evaluating

### `load_policy(path) -> Policy`

Reads a UTF-8 JSON policy with size and structural limits, rejects duplicate keys and invalid
values, and returns an immutable `Policy`. Raises `PolicyValidationError` for caller-correctable
policy failures.

### `load_context(path, *, stdin=None) -> dict[str, Any]`

Loads a bounded JSON object from a file, or from a binary stream when `path` is `None` or `"-"`.
Raises `InputValidationError`.

### `PolicyEngine(policy).evaluate(context) -> Decision`

Evaluates every rule deterministically. Raises `InputValidationError` for a non-object context and
`EvaluationError` if an operator cannot safely evaluate the supplied types or a `$ref` is missing.

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

## Models

- `Policy.from_dict(value)` and `Policy.to_dict()`
- `PolicyRule.from_dict(value, index=...)` and `PolicyRule.to_dict()`
- `PolicyCondition.from_dict(value, location=...)` and `PolicyCondition.to_dict()`
- `Effect`: `allow`, `deny`, `review`, `warn`, `audit`
- `Outcome`: `allow`, `deny`, `review`

Models are frozen dataclasses. Construct policies through `from_dict` or `load_policy` so validation
always runs.

## Audit helper

### `append_audit_record(path, decision) -> None`

Appends one compact JSONL record and calls `fsync`. The destination's parent must already exist.
The record includes decision and policy identity, outcome, matched rule IDs, and warning count. It
does not include evaluation input, rule messages, or secrets. Raises `AuditLogError` on failure.

## Error hierarchy

`PolicyValidationError`, `InputValidationError`, `EvaluationError`, and `AuditLogError` derive from
`HelixEthicsError`. The base class is defined in `helix_ethics.errors`; specialized errors are also
exported from `helix_ethics`.

## Compatibility

The supported package API begins at `0.1.0`. The former repository code did not expose an
installable, internally consistent API; its missing imports and placeholder compliance types are
not compatibility targets. Breaking changes before `1.0.0` will be called out in `CHANGELOG.md`.
