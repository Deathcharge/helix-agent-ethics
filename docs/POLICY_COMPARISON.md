# Policy impact comparison

Policy regression tests answer whether one policy matches explicit expectations. Policy impact
comparison answers a different rollout question: **what observable behavior changes between the
approved baseline and this candidate over the cases we already maintain?**

This follows established change-safety practice. [OPA policy testing](https://www.openpolicyagent.org/docs/policy-testing)
positions tests as protection while rules evolve, and the
[Amazon Verified Permissions test bench](https://docs.aws.amazon.com/verifiedpermissions/latest/userguide/authorization-testing.html)
encourages evaluating requests while changing policies and inspecting which policy satisfied the
decision.

## Run the included comparison

```bash
samsarix-ethics compare \
  --baseline examples/policies/safe-agent-actions.json \
  --candidate examples/policies/safe-agent-actions-candidate.json \
  examples/tests/safe-agent-actions.tests.json
```

The candidate requires review for sensitive read-only work. Four cases remain unchanged and the
`sensitive read records a warning` case changes from `allow` to `review`. The command exits `1`
because at least one case changed. Identical behavior exits `0`; invalid input or invocation exits
`2`.

Use JSON in CI or review tooling:

```bash
samsarix-ethics compare \
  --baseline approved-policy.json \
  --candidate proposed-policy.json \
  authorization.tests.json \
  --format json > policy-impact.json
```

The output conforms to the bundled versioned schema:

```bash
samsarix-ethics schema policy-comparison > policy-comparison-v1.schema.json
```

## What is compared

Each existing policy-test case is evaluated independently against both policies. A result is:

- `unchanged` when outcome, ordered matched-rule IDs, warning count, reason messages, and warning
  messages are equal;
- `changed` when at least one of those observables differs; or
- `error` when either evaluation fails closed.

An outcome change is counted as an `authorization_change`. Changed matched rules, warning counts,
reason messages, or warning messages with the same outcome are `metadata_only_changes`. Message
text is compared internally but omitted from the serialized report; only the applicable
`reason_messages` or `warning_messages` change label is emitted. Errors are neither unchanged nor
changed; they keep `identical` false and make the CLI exit `1`.

The complete report includes baseline and candidate IDs, versions, exact policy fingerprints,
aggregate counts, and per-case snapshots. It is deterministic: decision UUIDs and timestamps are
not included.

## Privacy boundary

Comparison reports deliberately omit every case input, reason text, and warning text. Case names,
rule IDs, policy identifiers, error messages, and exact policy fingerprints remain visible. Treat
those as operational metadata and avoid putting secrets or personal data in identifiers or case
names.

Policy fingerprints prove canonical content equality, not author identity or approval. Store the
approved baseline and enforce your own code review, signing, deployment, and rollback controls.

## Coverage boundary

A report proves behavior only for the supplied suite. `identical: true` does not establish semantic
equivalence for every possible input. Maintain positive, negative, boundary, missing-field,
wrong-type, override, and warning cases that reflect real application operations. Add a case before
approving a change whenever the suite did not exercise the affected rule or fact shape.
