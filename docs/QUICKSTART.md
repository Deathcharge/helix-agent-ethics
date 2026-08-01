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
Valid policy safe-agent-actions@1.0.0: 6 rules, default=review
```

## 3. Run the policy regression suite

```bash
samsarix-ethics test --policy examples/policies/safe-agent-actions.json examples/tests/safe-agent-actions.tests.json
```

The five cases cover allow, deny, review, missing approval, and warning behavior. All pass and the
command exits `0`; an unmet expectation or evaluation error exits `1`.

## 4. Evaluate an allowed action

```bash
samsarix-ethics check --policy examples/policies/safe-agent-actions.json --input examples/actions/read-resource.json
```

The JSON result has `outcome: allow`, `allowed: true`, a new `decision_id`, the policy version, and
the matching rule explanation. The command exits `0`.

## 5. Observe safe denial

```bash
samsarix-ethics check --policy examples/policies/safe-agent-actions.json --input examples/actions/delete-resource.json
```

The example lacks human approval, so the deny rule wins and the command exits `3`. This nonzero
exit is intentional and suitable for shell or CI gates.

## 6. Add a privacy-minimized audit record

```bash
samsarix-ethics check --policy examples/policies/safe-agent-actions.json --input examples/actions/read-resource.json --audit-log decisions.jsonl
```

`decisions.jsonl` receives decision metadata only. The input document is not copied. Decide access,
rotation, retention, and deletion policy before enabling this in a real application.

## 7. Enforce a real tool callback

The bundled tool policy treats read-only work as allowed, destructive work without approval as
denied, external writes as reviewable, and unknown capabilities as reviewable:

```python
from samsarix_ethics import ToolGate, load_policy

gate = ToolGate(load_policy("examples/policies/tool-call-baseline.json"))
result = gate.execute(
    "read_ticket",
    {"ticket_id": "T-100"},
    lambda arguments: {"ticket_id": arguments["ticket_id"], "status": "open"},
    capabilities=["resource:read"],
    actor={"id": "support-agent"},
)
assert result.decision.allowed
```

Run the thirteen-case compatibility fixture:

```bash
samsarix-ethics test --policy examples/policies/tool-call-baseline.json examples/tests/tool-call-baseline.tests.json
```

See [tool-call integrations](TOOL_CALLS.md) before connecting an agent runtime.

## 8. Start a policy of your own

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
samsarix-ethics schema tool-context > tool-context-v1.schema.json
```
