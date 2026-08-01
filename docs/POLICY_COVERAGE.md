# Policy rule coverage

Passing regression tests prove that supplied expectations are satisfied. Rule coverage answers a
second authoring question: **which rules did those cases actually exercise?** A suite can pass while
never matching a newly added deny, review, allow, or warning rule.

This follows established policy-testing practice. [OPA policy testing](https://www.openpolicyagent.org/docs/policy-testing)
reports evaluated and unevaluated policy lines and supports a coverage threshold. The
[OpenFGA model testing guide](https://openfga.dev/docs/modeling/testing) recommends cases that
exercise every relation an application uses. Samsarix reports rule matches because JSON policies
do not have meaningful source-line locations.

## Run the included coverage gate

```bash
samsarix-ethics coverage \
  --policy examples/policies/tool-call-baseline.json \
  examples/tests/tool-call-baseline.tests.json \
  --threshold 100
```

The tool-call suite covers all twelve policy rules and observes allow, deny, and review outcomes.
The command exits `0`. If coverage is below the requested integer percentage, or any case cannot be
evaluated, it exits `1`. Invalid policy, suite, threshold, or invocation exits `2`.

Without `--threshold`, the threshold is `0`: the command reports uncovered rules and fails only on
evaluation errors. Use an explicit threshold in CI so the intended gate is visible in review.
Coverage does not check the suite's `expected_*` assertions; run `samsarix-ethics test` as a
separate correctness gate, as the included CI workflow does.

For automation, select JSON and validate it with the bundled versioned schema:

```bash
samsarix-ethics coverage \
  --policy policy.json \
  policy.tests.json \
  --threshold 90 \
  --format json > policy-coverage.json
samsarix-ethics schema policy-coverage > policy-coverage-v1.schema.json
```

## Coverage semantics

A rule is covered when it appears in at least one successful decision's ordered `matched_rules`.
This includes warning rules and authorization rules whose effect is later overridden by deny or
review precedence. A case that uses `default_effect` still contributes to the allow, deny, or review
outcome counts but covers no rule merely by reaching the default.

Evaluation errors receive no partial credit. They are listed by case name with the bounded engine
error, keep `threshold_met` and `complete` false, and make the CLI exit `1`. The threshold comparison
uses exact covered/total counts rather than the two-decimal display value. A policy with zero rules
has vacuous 100% rule coverage; use outcome counts and regression assertions to test its default.

The report preserves declaration order for covered and uncovered rule IDs and includes the exact
policy fingerprint, case totals, outcome counts, threshold, and aggregate status. Decision UUIDs
and timestamps are excluded, so repeated runs over the same policy and suite are deterministic.

## Privacy and evidence boundary

Coverage reports omit every fixture input, reason, and warning message. They expose suite and case
names, policy and rule identifiers, the exact policy fingerprint, and evaluation errors. Do not put
secrets or personal data in operator-authored labels, and protect reports as operational metadata.

One matching input does not fully test a rule. Rule coverage does not prove that each condition,
type boundary, missing-field path, precedence interaction, or adversarial input was exercised. Pair
coverage with explicit positive, negative, boundary, override, warning, wrong-type, and missing-field
assertions, then use [policy impact comparison](POLICY_COMPARISON.md) before candidate rollout.
