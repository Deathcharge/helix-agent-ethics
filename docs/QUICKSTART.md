# Quick start

This walkthrough exercises the full local policy-gate journey.

## 1. Install from the repository

```bash
python -m venv .venv
```

Activate `.venv`, then:

```bash
python -m pip install -e .
samsarix-ethics --version
```

Expected version output:

```text
samsarix-ethics 0.1.0
```

## 2. Validate the policy

```bash
samsarix-ethics validate examples/policies/safe-agent-actions.json
```

Expected result:

```text
Valid policy safe-agent-actions@1.0.0: 6 rules, default=review, fingerprint=v1:sha256:...
```

## 3. Lint the policy

```bash
samsarix-ethics lint examples/policies/safe-agent-actions.json --fail-on suggestion
```

The included policy has no findings. The strict command exits `1` for any stable security warning,
warning, or suggestion without printing condition values. See [policy authoring diagnostics](POLICY_LINTING.md).

## 4. Run the policy regression suite

```bash
samsarix-ethics test --policy examples/policies/safe-agent-actions.json examples/tests/safe-agent-actions.tests.json
```

The five cases cover allow, deny, review, missing approval, and warning behavior. All pass and the
command exits `0`; an unmet expectation or evaluation error exits `1`.

## 5. Measure policy rule coverage

```bash
samsarix-ethics coverage --policy examples/policies/tool-call-baseline.json examples/tests/tool-call-baseline.tests.json --threshold 100
```

The tool-call suite matches all twelve rules and observes allow, deny, and review. Missing the
threshold or encountering an evaluation error exits `1`; the report never includes fixture inputs.
See [policy rule coverage](POLICY_COVERAGE.md).

## 6. Compare a candidate before rollout

```bash
samsarix-ethics compare --baseline examples/policies/safe-agent-actions.json --candidate examples/policies/safe-agent-actions-candidate.json examples/tests/safe-agent-actions.tests.json
```

The candidate keeps four cases unchanged and moves one sensitive read from `allow` to `review`.
The report excludes inputs and exits `1` because observable behavior changed. Review that impact
before adopting the candidate. See [policy impact comparison](POLICY_COMPARISON.md).

## 7. Evaluate an allowed action

```bash
samsarix-ethics check --policy examples/policies/safe-agent-actions.json --input examples/actions/read-resource.json
```

The JSON result has `outcome: allow`, `allowed: true`, a new `decision_id`, the policy version, and
the matching rule explanation. The command exits `0`.

## 8. Observe safe denial

```bash
samsarix-ethics check --policy examples/policies/safe-agent-actions.json --input examples/actions/delete-resource.json
```

The example lacks human approval, so the deny rule wins and the command exits `3`. This nonzero
exit is intentional and suitable for shell or CI gates.

## 9. Add a privacy-minimized audit record

```bash
samsarix-ethics check --policy examples/policies/safe-agent-actions.json --input examples/actions/read-resource.json --audit-log decisions.jsonl
```

`decisions.jsonl` receives decision metadata only. The input document is not copied. Its
`policy_fingerprint` identifies the exact canonical policy body evaluated even if an operator
reuses a policy version label. Decide access, rotation, retention, and deletion policy before
enabling this in a real application.

## 10. Enforce a real tool callback

The bundled tool policy treats read-only work as allowed, destructive work without approval as
denied, external writes as reviewable, and unknown capabilities as reviewable:

```python
from samsarix_ethics import ToolGate, load_policy

gate = ToolGate(load_policy("examples/policies/tool-call-baseline.json"))
read_ticket = gate.bind("read_ticket", capabilities=["resource:read"])
result = read_ticket.execute(
    {"ticket_id": "T-100"},
    lambda arguments: {"ticket_id": arguments["ticket_id"], "status": "open"},
    actor={"id": "support-agent"},
)
assert result.decision.allowed
```

Run the fourteen-case compatibility fixture:

```bash
samsarix-ethics test --policy examples/policies/tool-call-baseline.json examples/tests/tool-call-baseline.tests.json
```

See [tool-call integrations](TOOL_CALLS.md) before connecting an agent runtime.

## 11. Start a policy of your own

```bash
samsarix-ethics init my-policy.json
samsarix-ethics validate my-policy.json
```

The init command refuses to overwrite a file unless `--force` is present. Continue with the
[policy format reference](POLICY_FORMAT.md).

To configure an editor or external validator, export the versioned schemas:

```bash
samsarix-ethics schema policy > policy-v1.schema.json
samsarix-ethics schema policy-test > policy-test-v1.schema.json
samsarix-ethics schema policy-comparison > policy-comparison-v1.schema.json
samsarix-ethics schema policy-coverage > policy-coverage-v1.schema.json
samsarix-ethics schema policy-lint > policy-lint-v1.schema.json
samsarix-ethics schema tool-context > tool-context-v1.schema.json
samsarix-ethics schema tool-approval > tool-approval-v1.schema.json
samsarix-ethics schema audit-record > audit-record-v1.schema.json
```
