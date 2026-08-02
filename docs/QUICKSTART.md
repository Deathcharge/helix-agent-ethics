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
warning, or suggestion. Lint output excludes condition values, descriptions, and rule messages. See
[policy authoring diagnostics](POLICY_LINTING.md).

## 4. Run the policy regression suite

```bash
samsarix-ethics test --policy examples/policies/safe-agent-actions.json examples/tests/safe-agent-actions.tests.json
```

The five cases cover allow, deny, review, missing approval, and warning behavior. All pass and the
command exits `0`; an unmet expectation or evaluation error exits `1`.

## 5. Compose organization and application layers

```bash
samsarix-ethics compose --id tool-call-baseline --version 1.0.0 --description "Fail-closed baseline for read, destructive, external, and sensitive tool capabilities." --policy examples/policies/organization-tool-guardrails.json --policy examples/policies/support-agent-tool-permissions.json --output composed-policy.json
```

This build-time step combines eight organization-owned guardrails with four support-agent rules.
It emits one ordinary policy plus a value-minimized source-provenance report. Existing output is
never replaced without `--force`. See [layered policy composition](POLICY_COMPOSITION.md).

Lint and regression-test the exact generated deployment artifact:

```bash
samsarix-ethics lint composed-policy.json --fail-on suggestion
samsarix-ethics test --policy composed-policy.json examples/tests/tool-call-baseline.tests.json
```

## 6. Measure policy rule coverage

```bash
samsarix-ethics coverage --policy composed-policy.json examples/tests/tool-call-baseline.tests.json --threshold 100
```

The tool-call suite matches all twelve rules and observes allow, deny, and review. Missing the
threshold or encountering an evaluation error exits `1`; the report never includes fixture inputs.
See [policy rule coverage](POLICY_COVERAGE.md).

## 7. Compare a candidate before rollout

```bash
samsarix-ethics compare --baseline examples/policies/safe-agent-actions.json --candidate examples/policies/safe-agent-actions-candidate.json examples/tests/safe-agent-actions.tests.json
```

The candidate keeps four cases unchanged and moves one sensitive read from `allow` to `review`.
The report excludes inputs and exits `1` because observable behavior changed. Review that impact
before adopting the candidate. See [policy impact comparison](POLICY_COMPARISON.md).

## 8. Shadow the candidate on a live-shaped action

```bash
samsarix-ethics shadow \
  --baseline examples/policies/safe-agent-actions.json \
  --candidate examples/policies/safe-agent-actions-candidate.json \
  --input examples/actions/read-restricted-resource.json
```

The approved baseline still returns `allow`, so the command exits `0`; the candidate observation
returns `review`, and the report marks an authorization change. During rollout, enforce only the
`authoritative` baseline outcome and monitor the independent shadow `status`. The report excludes
the action input and all reason/warning text. See [shadow policy rollout](POLICY_SHADOWING.md).

## 9. Evaluate an allowed action

```bash
samsarix-ethics check --policy examples/policies/safe-agent-actions.json --input examples/actions/read-resource.json
```

The JSON result has `outcome: allow`, `allowed: true`, a new `decision_id`, the policy version, and
the matching rule explanation. The command exits `0`.

## 10. Observe safe denial

```bash
samsarix-ethics check --policy examples/policies/safe-agent-actions.json --input examples/actions/delete-resource.json
```

The example lacks human approval, so the deny rule wins and the command exits `3`. This nonzero
exit is intentional and suitable for shell or CI gates.

## 11. Add a privacy-minimized audit record

```bash
samsarix-ethics check --policy examples/policies/safe-agent-actions.json --input examples/actions/read-resource.json --audit-log decisions.jsonl
```

`decisions.jsonl` receives decision metadata only. The input document is not copied. Its
`policy_fingerprint` identifies the exact canonical policy body evaluated even if an operator
reuses a policy version label. Decide access, rotation, retention, and deletion policy before
enabling this in a real application.

## 12. Enforce a real tool callback

The bundled tool policy treats read-only work as allowed, destructive work without approval as
denied, external writes as reviewable, and unknown capabilities as reviewable:

```python
from samsarix_ethics import ToolGate, load_policy

gate = ToolGate(load_policy("composed-policy.json"))
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
samsarix-ethics test --policy composed-policy.json examples/tests/tool-call-baseline.tests.json
```

See [tool-call integrations](TOOL_CALLS.md) before connecting an agent runtime.

## 13. Package exact deployment artifacts as one file

```bash
samsarix-ethics deployment create \
  --policy composed-policy.json \
  --context-contract examples/contracts/tool-call-context.json \
  --output composed-policy.deployment.json
samsarix-ethics deployment verify composed-policy.deployment.json
samsarix-ethics check \
  --deployment composed-policy.deployment.json \
  --input examples/actions/tool-read-config.json

samsarix-ethics compose \
  --id tool-call-candidate \
  --version 1.1.0-candidate \
  --policy composed-policy.json \
  --policy examples/policies/restricted-read-candidate-guardrail.json \
  --output candidate-policy.json
samsarix-ethics deployment create \
  --policy candidate-policy.json \
  --context-contract examples/contracts/tool-call-context-candidate.json \
  --output candidate.deployment.json
samsarix-ethics deployment verify candidate.deployment.json
```

The result contains the complete policy, optional contract, and a mandatory matching lock. One
bounded read cannot observe a mixed local artifact set. The file is internally consistent but
unsigned. The primary evaluation commands accept it directly and reject separate contract or lock
arguments that could create an ambiguous configuration. See
[single-file policy deployments](POLICY_DEPLOYMENTS.md).

## 14. Authenticate a complete tool-gate deployment

After creating a coherent tool-gate deployment, bind its complete bytes to one target environment,
release sequence, and validity window:

```bash
samsarix-ethics gate-deployment authenticate coding-agent.gate-deployment.json \
  --key-file deployment-auth.key \
  --key-id prod-2026-q3 \
  --audience coding-agent:production \
  --sequence 42 \
  --issued-at 2026-08-02T12:00:00Z \
  --expires-at 2026-08-03T12:00:00Z \
  --output coding-agent.authenticated.json

samsarix-ethics gate-deployment verify-authentication \
  coding-agent.authenticated.json \
  --key-file deployment-auth.key \
  --key-id prod-2026-q3 \
  --audience coding-agent:production \
  --minimum-sequence 42 \
  --at 2026-08-02T12:00:00Z
```

Keep the key and highest accepted sequence outside the envelope in protected target state. HMAC
verifiers can also mint envelopes; use an asymmetric release system where author/verifier
separation is required. See [authenticated deployments](AUTHENTICATED_DEPLOYMENTS.md).

## 15. Activate a reviewed candidate without rebuilding live gates

```python
from samsarix_ethics import PolicyRuntime, ToolGate, load_policy_deployment

deployment = load_policy_deployment("composed-policy.deployment.json")
runtime = PolicyRuntime.from_deployment(deployment)
read = ToolGate(runtime).bind("read", capabilities=["resource:read"])
runtime.activate_deployment(
    load_policy_deployment("candidate.deployment.json"),
    expected_generation=runtime.status.generation,
)
assert read.runtime_status is runtime.status
```

The complete candidate is validated before one atomic in-process swap. A stale generation or
invalid candidate leaves the last successful policy active. See
[atomic policy runtime](POLICY_RUNTIME.md).

## 16. Start a policy of your own

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
samsarix-ethics schema policy-composition > policy-composition-v1.schema.json
samsarix-ethics schema policy-coverage > policy-coverage-v1.schema.json
samsarix-ethics schema policy-explanation > policy-explanation-v1.schema.json
samsarix-ethics schema policy-lint > policy-lint-v1.schema.json
samsarix-ethics schema policy-runtime-status > policy-runtime-status-v1.schema.json
samsarix-ethics schema policy-shadow > policy-shadow-v1.schema.json
samsarix-ethics schema context-contract > context-contract-v1.schema.json
samsarix-ethics schema deployment-lock > deployment-lock-v1.schema.json
samsarix-ethics schema policy-deployment > policy-deployment-v1.schema.json
samsarix-ethics schema tool-context > tool-context-v1.schema.json
samsarix-ethics schema tool-approval > tool-approval-v1.schema.json
samsarix-ethics schema tool-catalog > tool-catalog-v1.schema.json
samsarix-ethics schema tool-gate-deployment > tool-gate-deployment-v1.schema.json
samsarix-ethics schema tool-gate-deployment-envelope > tool-gate-deployment-envelope-v1.schema.json
samsarix-ethics schema audit-record > audit-record-v1.schema.json
samsarix-ethics schema audit-chain-entry > audit-chain-entry-v1.schema.json
samsarix-ethics schema audit-chain-verification > audit-chain-verification-v1.schema.json
```
