# Atomic policy runtime

`PolicyRuntime` lets a long-running Python process activate a complete policy, optional application
context contract, and optional deployment lock as one generation. Existing `ToolGate` and
`BoundToolGate` objects follow successful activations without being rebuilt.

## Why it exists

A rollout must not expose a half-updated policy/contract pair, replace a working policy with an
invalid candidate, or let two deployers silently overwrite each other. The runtime therefore has
four invariants:

1. A candidate `PolicyEngine` is fully constructed, contract-checked, and lock-verified before live
   state is touched.
2. Policy, contract, lock, and exact fingerprints swap together under one in-process lock.
3. Candidate failure retains the last successfully activated generation.
4. Optional `expected_generation` compare-and-swap rejects stale concurrent activation attempts.

## Activate a generation

```python
from samsarix_ethics import PolicyRuntime, ToolGate, load_policy

baseline = load_policy("policy-v1.json")
candidate = load_policy("policy-v2.json")
runtime = PolicyRuntime(baseline)
tool = ToolGate(runtime).bind("read_ticket", capabilities=["resource:read"])

before = tool.evaluate({"ticket_id": "T-100"})
status = runtime.activate(candidate, expected_generation=runtime.status.generation)
after = tool.evaluate({"ticket_id": "T-100"})
print(status.generation, before.outcome, after.outcome)
```

`activate` returns the immutable new `PolicyRuntimeStatus`. Generation numbering starts at `1` and
increases on every successful activation, including a rollback. A stale expected generation raises
`PolicyActivationError`; invalid candidate artifacts retain their existing validation error type.

To activate reviewed exact artifacts together:

```python
status = runtime.activate(
    candidate_policy,
    context_contract=candidate_contract,
    deployment_lock=candidate_lock,
    expected_generation=runtime.status.generation,
)
```

The deployment lock is verified while the candidate engine is built. Any policy, contract,
contract-presence, or fingerprint mismatch prevents the swap.

When artifacts travel or persist together, prefer the single-file deployment API:

```python
from samsarix_ethics import PolicyRuntime, load_policy_deployment

runtime = PolicyRuntime.from_deployment(load_policy_deployment("baseline.deployment.json"))
status = runtime.activate_deployment(
    load_policy_deployment("candidate.deployment.json"),
    expected_generation=runtime.status.generation,
)
```

The mandatory embedded lock is checked during the bounded single-file load and again while the
runtime constructs the engine. See [single-file policy deployments](POLICY_DEPLOYMENTS.md).

## Evaluation consistency

`evaluate` and `explain` capture one engine reference under the runtime lock, release the lock, and
then do normal bounded work. An evaluation already in flight finishes entirely on its captured
generation while later calls see the newly activated generation. `evaluate_many` captures once for
the entire bounded batch, so one batch cannot straddle generations.

The lock is never held during policy evaluation, explanation, audit delivery, or a tool callback.
Activation therefore does not wait for slow calls to finish, and slow calls do not serialize other
evaluations.

## Status and observability

`runtime.status`, `gate.runtime_status`, and `bound_gate.runtime_status` return one coherent frozen
status snapshot containing:

- runtime status version, generation, and UTC activation time;
- active policy ID, version, and exact canonical fingerprint;
- optional context-contract ID, version, and exact fingerprint; and
- whether a deployment lock was supplied and successfully verified.

It excludes policy descriptions, rules, paths, values, messages, action input, decisions, and
errors. Export its Draft 2020-12 schema with:

```bash
samsarix-ethics schema policy-runtime-status
```

When a gate is backed directly by a static `Policy`, `runtime_status` is `None`. Individual gate
properties such as `policy` and `context_contract` report the current runtime value, but callers
that need mutually coherent metadata should read the single `runtime_status` snapshot.

## Rollback and control-plane boundary

Rollback is an ordinary activation of a retained prior policy/contract/lock set. The generation
still increases, making the rollback observable rather than reusing an old generation number.

This package does not fetch, watch, persist, authenticate, approve, sign, schedule, or distribute
artifacts. It also does not coordinate generations across processes or hosts. The embedding
application owns artifact transport, durable desired state, leader election, retries, health
monitoring, and deployment authorization. On process restart, construct the runtime from the
desired last-known-good artifacts; a generation is process-local operational state, not a global
revision or rollback-prevention counter.

Run the checked-in example with:

```bash
python examples/policy_runtime_demo.py
```
