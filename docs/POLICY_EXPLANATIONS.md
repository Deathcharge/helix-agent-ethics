# Policy explanations

Policy explanations answer why a particular input matched or missed each rule without copying the
input, condition values, or authored messages into the report. They are intended for trusted
operators debugging policy behavior, regression failures, and integration fact-shape problems.

OPA exposes structured query explanations and documents decision logs as an auditing/debugging
tool, while explicitly warning that policy inputs can contain credentials and personal data. The
Samsarix version 1 report deliberately chooses a smaller privacy surface: condition field and
operator metadata are visible, but actual/expected values and messages are absent.

## CLI

```bash
samsarix-ethics explain \
  --policy examples/policies/safe-agent-actions.json \
  --input examples/actions/read-resource.json
```

Use `--format text` for an operator view. JSON conforms to the bundled versioned schema:

```bash
samsarix-ethics schema policy-explanation > policy-explanation-v1.schema.json
```

The command uses the same outcome exit codes as `check`: `0` for allow, `3` for deny, and `4` for
review. Evaluation/validation errors exit `2`. An explanation is diagnostic evidence, not a second
authorization mechanism; enforce the decision through `PolicyEngine`, `ToolGate`, or `check` at
the protected boundary.

The same production configuration can be required:

```bash
samsarix-ethics explain \
  --policy policy.json \
  --context-contract context-contract.json \
  --deployment-lock deployment-lock.json \
  --input action.json
```

Policy/contract mismatch fails before explanation. When a contract is configured, the report
includes its canonical fingerprint but not its paths or description.

## Python API

```python
from samsarix_ethics import PolicyEngine, load_policy

engine = PolicyEngine(load_policy("policy.json"))
explanation = engine.explain({"action": {"operation": "read"}})

print(explanation.outcome)
for rule in explanation.rules:
    print(rule.rule_id, rule.matched, rule.decisive)
```

`ToolGate.explain(...)` accepts the same normalized call fields as `evaluate`, and
`BoundToolGate.explain(...)` reuses its trusted registered tool name/capabilities. Explanation does
not authorize, execute, or emit an audit record; use the ordinary gate path for enforcement.

`PolicyExplanation` contains:

- exact policy identity and canonical fingerprint;
- an optional canonical context-contract fingerprint;
- outcome and whether the policy default supplied it;
- matched rule IDs in normal priority/ID decision order;
- decisive rule IDs whose effect determined the outcome; and
- every rule in declaration order with effect, priority, match/decisive flags, and condition
  statuses.

Each condition is `matched`, `not_matched`, or `not_evaluated`. Policy evaluation short-circuits a
rule after its first false condition. Later conditions are reported as `not_evaluated`; the
explanation path never evaluates work the decision path would skip. Domain errors that the normal
decision encounters remain errors and are not converted into partial explanations.

Warn and audit rules can match but are never decisive. When no allow, deny, or review rule matches,
`default_applied` is true even if descriptive warn/audit rules matched.

## Privacy and security boundary

Version 1 never serializes input, condition values, `$ref` targets, policy descriptions, rule
messages, decision UUIDs, or timestamps. It does expose policy/rule identifiers, condition field
paths and operators, match status, effects, priorities, outcome, and exact fingerprints. Do not put
secrets in identifiers or field paths.

Repeated explanations are still an authorization oracle: a caller can vary inputs and observe
which conditions change status. Limit explanation access to trusted policy operators and protect
reports as operational metadata. The report does not prove input truth, policy correctness,
authorship, approval, or exhaustive safety. It explains one supplied evaluation only.

References: [OPA REST API explanations](https://www.openpolicyagent.org/docs/rest-api) and
[OPA decision-log masking](https://www.openpolicyagent.org/docs/management-decision-logs).
