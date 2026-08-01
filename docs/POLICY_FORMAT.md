# Policy format

Policies are UTF-8 JSON objects with `schema_version: 1`.

```json
{
  "schema_version": 1,
  "id": "tenant-boundary",
  "version": "1.0.0",
  "description": "Allow reads only inside the actor's tenant.",
  "default_effect": "deny",
  "rules": [
    {
      "id": "allow-same-tenant-read",
      "effect": "allow",
      "priority": 100,
      "message": "Actor and resource tenant match.",
      "conditions": [
        {"field": "action.operation", "operator": "eq", "value": "read"},
        {
          "field": "actor.tenant_id",
          "operator": "eq",
          "value": {"$ref": "resource.tenant_id"}
        }
      ]
    }
  ]
}
```

Unknown fields are rejected so spelling mistakes do not silently weaken a gate.

## Policy fields

| Field | Requirement |
| --- | --- |
| `schema_version` | integer `1` |
| `id` | stable 1-128 character identifier |
| `version` | stable 1-128 character version identifier |
| `description` | optional string, at most 1,000 characters |
| `default_effect` | `allow`, `deny`, or `review` |
| `rules` | array of at most 1,000 rules with unique IDs |

Prefer `deny` for authorization boundaries and `review` when a human queue is a valid safe fallback.
Use `allow` only when the surrounding system is intentionally permissive.

## Rule fields

| Field | Requirement |
| --- | --- |
| `id` | unique stable identifier |
| `effect` | `allow`, `deny`, `review`, `warn`, or `audit` |
| `conditions` | array of at most 32 conditions; an empty array always matches |
| `message` | optional explanation, at most 500 characters |
| `priority` | optional integer from -10,000 through 10,000; default `100` |

Priority affects the stable ordering of matched rules and messages, not outcome precedence.

## Effects and precedence

All rules run. Final precedence is:

1. any matching `deny` -> deny;
2. otherwise any matching `review` -> review;
3. otherwise any matching `allow` -> allow;
4. otherwise `default_effect`.

`warn` adds a warning. `audit` records that its rule matched in `matched_rules`. Neither grants an
action.

## Conditions

Each condition contains a dotted `field`, an `operator`, and—except for existence checks—a `value`.
Existence checks reject `value` rather than silently ignoring it. All conditions in a rule must be
true.

| Operator | Meaning |
| --- | --- |
| `eq`, `neq` | equality or inequality |
| `exists`, `not_exists` | dotted field presence |
| `in`, `not_in` | input field is/is not a member of the policy array; literal values must be arrays |
| `contains`, `not_contains` | input array contains/does not contain the policy value |
| `subset_of` | every item in the input array is present in the policy array |
| `starts_with`, `ends_with` | string prefix or suffix |
| `gt`, `gte`, `lt`, `lte` | numeric comparison across integers/floats, or string comparison; booleans rejected |

Missing ordinary input fields make a condition false. A missing `$ref` is an evaluation error,
because silently ignoring a cross-field comparison could weaken the policy.

## Cross-field references

Use exactly one `$ref` key as the value:

```json
{
  "field": "actor.tenant_id",
  "operator": "eq",
  "value": {"$ref": "resource.tenant_id"}
}
```

No interpolation or expression evaluation occurs.

## Resource limits

- policy file: 1 MiB;
- policy-test suite file: 4 MiB;
- input object: 256 KiB;
- JSON nesting: 32 levels per evaluation input, policy rule, or policy-test case;
- combined container entries: 10,000 per evaluation input, policy rule, or policy-test case;
- individual strings: 65,536 characters;
- rules: 1,000 per policy;
- conditions: 32 per rule.

These bounds are independent; a file-size limit may be reached before a list-count limit.

Duplicate JSON keys, non-UTF-8 input, `NaN`, and infinities are invalid.

## Exact policy provenance

The `id` and `version` fields are useful operator-authored labels, but the runtime does not assume
that an operator increments them after every edit. `fingerprint_policy(policy)` returns the exact
`v1:sha256:<hex>` identifier carried by decisions, policy-test reports, gates, and audit records.
The canonical form includes every serialized policy field. Object-key order is normalized while
array order is retained, so rearranging rules or conditions changes the exact-content fingerprint.

The CLI reports this value during validation:

```bash
samsarix-ethics validate policy.json --format json
```

Use the package helper as the authoritative serializer. The fingerprint detects content mismatch;
it is not a signature, author identity, approval record, or proof that a policy was distributed
securely.

## JSON Schema

The wheel contains Draft 2020-12 schemas for policies, policy-test suites, policy-comparison
reports, normalized tool-call contexts, bound approval records, and audit records. Print fresh
copies without a network request:

```bash
samsarix-ethics schema policy > policy-v1.schema.json
samsarix-ethics schema policy-test > policy-test-v1.schema.json
samsarix-ethics schema policy-comparison > policy-comparison-v1.schema.json
samsarix-ethics schema tool-context > tool-context-v1.schema.json
samsarix-ethics schema tool-approval > tool-approval-v1.schema.json
samsarix-ethics schema audit-record > audit-record-v1.schema.json
```

The runtime model remains authoritative for constraints JSON Schema cannot express conveniently,
including unique rule IDs, bounded aggregate container size, and unique case names.

## Testing a policy

Validate structure first, then maintain positive, negative, override, missing-field, and wrong-type
cases for every protected operation:

```bash
samsarix-ethics validate policy.json
samsarix-ethics test --policy policy.json policy.tests.json
```

A version 1 test suite is a JSON object with `schema_version`, an optional `name`, and 1-1,000
uniquely named `cases`. Every case requires:

- `name`: 1-200 character display name;
- `input`: the bounded JSON object to evaluate;
- `expected_outcome`: `allow`, `deny`, or `review`.

Cases may also assert the exact ordered `expected_matched_rules` array and an
`expected_warning_count`. The runner evaluates every case and reports `pass`, `fail`, or `error`;
reports intentionally exclude raw inputs. Exit `0` means every case passed, while exit `1` means at
least one expectation failed or evaluation errored. Malformed policies or suites exit `2`.

Reuse the same suite to compare an approved baseline with a candidate. Comparison ignores the
suite's expected fields and directly detects changes in actual outcome, ordered matched-rule IDs,
warning count, reason messages, or warning messages without serializing the message text:

```bash
samsarix-ethics compare --baseline approved.json --candidate proposed.json policy.tests.json
```

Exit `0` means all supplied cases had identical observable behavior; changes or evaluation errors
exit `1`. This is sampled impact evidence, not proof of equivalence for inputs absent from the
suite. See [POLICY_COMPARISON.md](POLICY_COMPARISON.md).
