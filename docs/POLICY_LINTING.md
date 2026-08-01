# Policy authoring diagnostics

Schema validation proves a policy is well formed. Linting asks whether a valid policy contains a
small set of authoring patterns that are certainly dangerous, impossible, redundant, or hard to
explain.

The design follows established policy tooling without copying a broader language. OPA recommends
strict compiler checks and a linter for policy mistakes and maintainability. [IAM Access Analyzer
policy validation](https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-policy-validation.html)
separates security warnings, general warnings, and suggestions so teams can choose their CI
boundary. Cedar also explains why policy checks must use known schema/semantics rather than guess
what a well-formed identifier means.

Samsarix therefore reports only five deterministic findings over its own validated model:

| Code | Severity | Finding |
| --- | --- | --- |
| `SAE001` | `security-warning` | policy `default_effect` is `allow` |
| `SAE002` | `security-warning` | an allow rule has no conditions and matches every valid input |
| `SAE101` | `warning` | an AND-condition set is provably impossible |
| `SAE201` | `suggestion` | a rule repeats a semantically identical condition |
| `SAE202` | `suggestion` | an allow, deny, review, or warning rule has no authored message |

## Lint the included policies

```bash
samsarix-ethics lint examples/policies/safe-agent-actions.json --fail-on suggestion
samsarix-ethics lint examples/policies/tool-call-baseline.json --fail-on suggestion
```

Both commands exit `0` with no findings. The repository CI applies this strict setting to every
bundled policy.

`--fail-on` accepts:

- `security-warning` (default): fail only for overly permissive behavior;
- `warning`: also fail for a provably unreachable rule;
- `suggestion`: fail for every finding;
- `none`: report findings without failing.

Exit `1` means one or more findings met the selected severity boundary. Invalid policy, option, or
invocation exits `2`. JSON output and the bundled schema support review automation:

```bash
samsarix-ethics lint policy.json --fail-on warning --format json > policy-lint.json
samsarix-ethics schema policy-lint > policy-lint-v1.schema.json
```

## Certainty and privacy boundary

Conditions in one rule are joined by AND. The unreachable-rule check is limited to facts that can
be proven from that model: `not_exists` combined with a condition that requires the same field, an
empty literal `in` set, or incompatible literal `eq`/`neq`/`in`/`not_in` constraints. Comparisons
whose value comes from `$ref` are skipped unless another contradiction is independently certain.
The analyzer does not infer domains, identity schemas, business intent, numeric ranges, or
relationships between different fields.

Finding locations use zero-based condition indices. Reports include policy/rule identifiers and
the exact policy fingerprint, but never serialize condition values, descriptions, or rule messages.
The fixed diagnostic message explains the class of problem without echoing secrets. Identifiers and
file paths remain operational metadata, so do not put sensitive data in them.

Lint success is not policy correctness. Continue to run regression assertions, a rule-coverage
threshold, candidate impact comparison, and application-owned review. A default deny can still be
wrong; a fully messaged and reachable allow rule can still grant too much access.
