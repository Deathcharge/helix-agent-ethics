# Deployment locks

A deployment lock binds one exact policy and, when used, one exact application context contract.
Human-readable IDs and versions remain useful labels; the lock adds canonical content fingerprints
so a reused version or unnoticed file edit fails closed before evaluation.

## Create and verify

Create the lock from the reviewed artifacts and commit all three files together:

```bash
samsarix-ethics lock create \
  --policy examples/policies/tool-call-baseline.json \
  --context-contract examples/contracts/tool-call-context.json \
  > deployment-lock.json

samsarix-ethics lock verify deployment-lock.json \
  --policy examples/policies/tool-call-baseline.json \
  --context-contract examples/contracts/tool-call-context.json
```

A policy-only deployment omits `--context-contract` from both commands. Presence is exact: a lock
created with a contract cannot be verified without it, and a policy-only lock cannot silently add
one later.

Use the lock at the production decision boundary:

```bash
samsarix-ethics validate policy.json \
  --context-contract context-contract.json \
  --deployment-lock deployment-lock.json

samsarix-ethics check --policy policy.json \
  --context-contract context-contract.json \
  --deployment-lock deployment-lock.json \
  --input action.json
```

`validate`, `check`, `PolicyEngine`, and `ToolGate` verify the lock before an action can be
authorized. A mismatch is an error and must remain non-authorizing. The checked-in
`examples/deployment/tool-call-baseline.lock.json` is continuously verified against the runnable
tool-call policy and contract.

## Python API

```python
from samsarix_ethics import (
    PolicyEngine,
    load_context_contract,
    load_deployment_lock,
    load_policy,
    verify_deployment_lock,
)

policy = load_policy("policy.json")
contract = load_context_contract("context-contract.json")
lock = load_deployment_lock("deployment-lock.json")

verify_deployment_lock(lock, policy, contract)
engine = PolicyEngine(policy, context_contract=contract, deployment_lock=lock)
```

`create_deployment_lock(policy, contract)` returns an immutable `DeploymentLock`. Its `to_dict()`
method produces the strict version 1 JSON artifact. `fingerprint_context_contract(contract)` is the
authoritative domain-separated context-contract serializer, just as `fingerprint_policy(policy)`
is authoritative for policies. Both use `v1:sha256:<hex>` labels, but their canonical payloads use
different domain separators.

Export the artifact schema for editors and generic CI validation:

```bash
samsarix-ethics schema deployment-lock > deployment-lock-v1.schema.json
```

Schema validity proves only shape. `lock verify` or `verify_deployment_lock` is required to compare
the artifact with the actual policy and contract content.

For coherent local transport and restart, package the complete artifacts plus this mandatory lock
as one [`PolicyDeployment`](POLICY_DEPLOYMENTS.md). The single-file loader recomputes the same lock
before returning and `PolicyRuntime` can activate the unit directly.

## Safe rollout workflow

1. Review and test the policy and contract together.
2. Generate a new lock from those exact files; never hand-edit its fingerprints.
3. Review the policy, contract, and lock in one change.
4. Verify the lock in CI and at process startup or deployment validation.
5. Supply the same locked artifacts to the live engine or gate.
6. Retain the prior reviewed set so rollback changes all artifacts together.

Any content change requires a new lock, even when an operator intentionally keeps the same ID or
version. An additive contract migration normally deploys a new optional fact first, then updates
the policy only after producers populate it; each reviewed stage gets its own lock.

## Security boundary

A deployment lock proves equality with the content used to create it. It is not a signature,
approval record, transparency log, freshness signal, secure distribution channel, or rollback
controller. An attacker who can replace the policy can also generate a matching lock. Protect and
authenticate the artifact set using repository review, signed build provenance, deployment access
controls, and any organization-required signing system. Keep an independently trusted expected
commit, release, or signed artifact identity when rollback prevention matters.

Lock files expose policy and contract IDs, versions, and equality-oracle fingerprints. They contain
no rules, conditions, contract paths, or evaluation input, but should still be treated as
operational metadata.
