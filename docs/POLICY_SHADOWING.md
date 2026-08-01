# Shadow policy rollout

Offline comparison answers what a candidate changes over a maintained test suite. Shadow
evaluation answers what that candidate *would have done for a live action* while the approved
baseline remains authoritative.

This is an established authorization rollout pattern. OpenFGA recommends issuing shadow checks
against current and upcoming immutable models before gradually rolling out the new model, while
OPA decision logs correlate decisions with policy revisions and warn that decision inputs can be
sensitive. Samsarix applies those ideas locally without a network control plane:

- [OpenFGA immutable authorization models](https://openfga.dev/docs/getting-started/immutable-models)
- [OPA decision logs](https://www.openpolicyagent.org/docs/management-decision-logs)
- [OPA bundle revisions and activation](https://www.openpolicyagent.org/docs/management-bundles)

## Run the included rollout example

The approved policy allows a read of restricted data and emits a warning. The candidate requires
review for the same action:

```bash
samsarix-ethics shadow \
  --baseline examples/policies/safe-agent-actions.json \
  --candidate examples/policies/safe-agent-actions-candidate.json \
  --input examples/actions/read-restricted-resource.json
```

The JSON report has `status: "changed"`, an authoritative `allow`, a candidate `review`, and an
`outcome` change. The process exits `0` because only the baseline controls authorization. A
baseline deny exits `3`; baseline review exits `4`; invalid input or a baseline evaluation error
exits `2`.

Candidate evaluation errors are different: the report has `status: "error"`, preserves the exact
candidate identity and fingerprint, and still exits according to the successful baseline. A
consumer must monitor the report status separately from the authorization exit code.

Export the strict Draft 2020-12 telemetry contract with:

```bash
samsarix-ethics schema policy-shadow > policy-shadow-v1.schema.json
```

## Python enforcement pattern

```python
from samsarix_ethics import PolicyShadowEvaluator, load_policy

shadow = PolicyShadowEvaluator(
    load_policy("approved.json"),
    load_policy("candidate.json"),
)
evaluation = shadow.evaluate(action_context)

# Send evaluation.to_dict() to an application-owned metrics/logging pipeline.
decision = evaluation.authoritative_decision
if decision.allowed:
    execute_action()
```

`authoritative_decision` is always the baseline decision. `candidate_decision` is available after
a successful candidate run and is `None` after a candidate-domain error. Do not enforce
`candidate_decision` during a shadow rollout.

Input validation and baseline evaluation happen first. Their errors propagate fail closed, so no
shadow result authorizes an action when the baseline cannot decide. After a successful baseline,
candidate `SamsarixEthicsError` failures become observational telemetry. Unexpected exceptions are
not swallowed; programming and system failures remain visible to the embedding application.

The evaluator validates and detaches one bounded JSON context before either engine runs. Both
policies therefore observe the same copied facts, rather than retaining the caller's mutable
object.

## What the report measures

Shadow and offline comparison deliberately use the same five observable changes:

- authorization outcome;
- ordered matched-rule IDs;
- warning count;
- reason messages; and
- warning messages.

Reason and warning text is compared in memory, but the serialized report emits only the
`reason_messages` or `warning_messages` change label. `authorization_changed` is true exactly when
`outcome` appears in `changes`. Strict schema conditionals reject contradictory status, change,
and authorization flags.

Both snapshots include policy ID, version, exact fingerprint, and—on successful evaluation—the
decision ID, UTC evaluation time, outcome, matched-rule IDs, warning count, and evaluated-rule
count. A candidate error snapshot retains policy provenance while making every unavailable
decision field null.

## Privacy and trust boundary

`to_dict()` excludes the complete action input, reason text, and warning text. It still exposes
operator-authored policy/rule identifiers, decision IDs, timestamps, fingerprints, outcomes,
counts, and candidate error messages. Treat these as operational metadata. Keep secrets and
personal data out of identifiers; route telemetry through an application-owned sink with suitable
access, masking, retention, and integrity controls.

The exact fingerprint proves which policy content ran. It does not prove who approved or deployed
that content. The application owns authenticated policy distribution, baseline pinning, rollout
assignment, durable telemetry, and promotion/rollback decisions.

## Production rollout sequence

1. Lint and regression-test the candidate, then require relevant rule coverage.
2. Compare baseline and candidate over the maintained suite and review every authorization change.
3. Pin the approved baseline and candidate by exact fingerprint in deployment configuration.
4. Shadow a caller-selected sample while continuing to enforce only `authoritative_decision`.
5. Monitor candidate errors, authorization-change rates, and operation-specific impact outside
   this library. Do not place raw action input in the telemetry envelope.
6. Expand sampling only after latency and error budgets are healthy.
7. Promote through the application's normal reviewed deployment mechanism, retaining the prior
   policy for rollback.

Shadow evaluation is synchronous and performs a second policy evaluation. It can add latency and
resource use even though it cannot change the returned authoritative outcome. The library does not
provide sampling, asynchronous queues, remote logging, statistical significance, automatic
promotion, or rollback. Those stateful controls belong to the embedding system.
