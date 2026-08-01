# Single-file policy deployments

A `PolicyDeployment` is one deterministic JSON document containing a complete policy, an optional
application context contract, and a mandatory deployment lock derived from those exact artifacts.
It closes the mixed-file read gap between artifact delivery and `PolicyRuntime` activation or
restart.

## Why one deployment unit

Loading `policy.json`, `contract.json`, and `deployment-lock.json` separately is fail closed, but an
updater can replace those files at different times. A process starting during that window may see
a mixed set and reject an otherwise valid rollout. One document gives the loader one bounded byte
snapshot and gives artifact stores one object to version, hash, replicate, retain, and roll back.

The design follows established policy-delivery boundaries:

- [OPA bundles](https://www.openpolicyagent.org/docs/management-bundles) package policy and related
  data together, validate the complete file set, and can persist the last activated unit for
  restart.
- [ORAS](https://oras.land/docs/commands/oras_push/) can push a file with a custom OCI artifact
  type and return its registry digest.
- [Sigstore Cosign](https://docs.sigstore.dev/cosign/verifying/verify/) can verify a blob signature
  and its bound digest without the application inventing a signing format.

Samsarix keeps local format validation separate from origin authentication. The embedded lock
proves internal exact equality; a protected repository, OCI digest, signature, or attestation can
prove which deployment operators approved.

## Create and verify

```bash
samsarix-ethics deployment create \
  --policy examples/policies/tool-call-baseline.json \
  --context-contract examples/contracts/tool-call-context.json \
  --output tool-call-baseline.deployment.json

samsarix-ethics deployment verify tool-call-baseline.deployment.json

samsarix-ethics check \
  --deployment tool-call-baseline.deployment.json \
  --input examples/actions/tool-read-config.json
```

Creation computes the mandatory lock, serializes one deterministic object, flushes the temporary
file, and atomically installs it. Existing files are never replaced unless `--force` is explicit;
an exclusive create does not overwrite a file that another process wins concurrently. CLI output
contains only artifact IDs, versions, fingerprints, lock status, and the output path—not policy
rules, values, descriptions, or messages.

`check` and `explain` accept `--deployment` instead of `--policy` and activate all three embedded
artifacts together. Supplying a separate `--context-contract` or `--deployment-lock` at the same
time is rejected so an operator cannot accidentally create a mixed deployment.

Verification strictly parses every nested model, rejects unknown top-level fields, and recomputes
the policy/contract lock. It exits `2` on malformed JSON, bounds violations, invalid nested
artifacts, contract incompatibility, or any lock mismatch.

Both deployment subcommands accept `--format json` for automation. Structured output contains
only policy and optional contract identity/fingerprint metadata, `lock_verified`, and the created
output path when applicable; it never copies rules, values, descriptions, or messages.

Export the self-contained Draft 2020-12 schema without network access:

```bash
samsarix-ethics schema policy-deployment > policy-deployment-v1.schema.json
```

The schema embeds fresh copies of the policy, context-contract, and deployment-lock schemas as
independent nested schema resources. Runtime parsing remains authoritative for cross-artifact lock
verification and aggregate semantic constraints.

## Runtime use

```python
from samsarix_ethics import PolicyRuntime, load_policy_deployment

baseline = load_policy_deployment("baseline.deployment.json")
runtime = PolicyRuntime.from_deployment(baseline)

candidate = load_policy_deployment("candidate.deployment.json")
status = runtime.activate_deployment(
    candidate,
    expected_generation=runtime.status.generation,
)
```

`from_deployment` re-verifies the lock while constructing generation `1`.
`activate_deployment` uses the existing atomic last-known-good activation path: the complete engine
is constructed before mutation, compare-and-swap rejects stale deployers, and policy, contract,
lock, and status change together.

`load_policy_deployment` reads at most `MAX_POLICY_DEPLOYMENT_BYTES` (4 MiB), rejects duplicate
keys, invalid UTF-8, non-finite numbers, excessive depth/containers/strings, invalid nested
formats, and lock mismatch. `create_policy_deployment`, `PolicyDeployment.from_dict`, `.to_dict`,
and `write_policy_deployment` provide the in-memory and filesystem APIs.

## Trust and distribution boundary

A valid deployment is self-consistent, not authenticated. Anyone who can replace the policy and
contract can compute a matching lock and deployment. Protect the one file with repository review,
least-privilege storage, immutable digests, signed release identity, and deployment authorization.

For OCI distribution, assign an organization-controlled artifact type, push the JSON file as one
layer, and deploy by immutable digest rather than mutable tag. Download to a temporary path and
verify the expected repository, digest, and any required signature over those exact bytes. Keep
the verified path immutable or atomically publish that same verified file to its final protected
path before calling `load_policy_deployment`; do not verify a writable path and then reopen it
after another process could replace it. This package does not execute ORAS/Cosign, manage keys,
accept trust roots, or interpret identity claims. See the TOCTOU responsibility in
[`SECURITY.md`](../SECURITY.md).

The atomic writer protects one local pathname operation. It does not make network transfer,
object-store replication, multi-host rollout, or process restart atomic. The embedding system owns
download-to-temporary, transport authentication, durable desired state, promotion approval,
retention, health checks, rollback selection, and cleanup. Keep the last known good deployment
available and reconstruct the runtime from it after restart.

The checked-in `examples/deployment/tool-call-baseline.deployment.json` is compared with freshly
loaded source policy and contract artifacts in CI, so drift in any copy fails verification.
