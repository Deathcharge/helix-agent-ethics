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

### Interrupted publication and restart

All four local writers (`write_policy`, `write_policy_deployment`, `write_tool_gate_deployment`,
and `write_tool_gate_deployment_envelope`) use the same staged-file protocol. They write and fsync
the body in the destination directory, close it, then either replace the canonical path or create
it exclusively using a hard link. A competing exclusive creator cannot overwrite the winner.
The destination filesystem must support these operations; there is no copy/delete fallback.

Normal Python exception unwinding, including `KeyboardInterrupt` and `SystemExit`, attempts to
remove the staging file without replacing the original exception. Abrupt process termination
cannot execute cleanup. A later cleanup/filesystem error can occur **after publication succeeded**:
an exception does not prove the destination is unchanged. Re-read and validate the canonical
artifact before deciding what happened; do not blindly retry, roll back, or promote a temporary file.

The real-process CI tests stop owned publisher processes at deterministic file-operation boundaries:

| Publisher stopped at | Canonical destination | Restart behavior |
| --- | --- | --- |
| Partial staged body or completed file fsync, before publication | Previous complete artifact, or absent on first create | Revalidate previous artifact; absent fails closed |
| After successful replacement | Complete new artifact | Load/verify new artifact, never a mixed policy/contract/catalog |
| After exclusive link, before staging cleanup | Complete new artifact plus an abandoned staging link | Load only the canonical artifact; do not select by filename/mtime |

On restart, select an explicit application-owned canonical path and re-run its bounded loader.
For authenticated deployments, re-verify the keyring, audience, current time and externally protected
minimum sequence **before binding callbacks**. A previous but still valid policy is not necessarily
authorized after a revocation: the process tests reject a sequence-1 envelope when the controller
requires sequence 2. Missing/corrupt/expired/unauthorized artifacts must not cause automatic fallback
to older or staged files. Restore only an explicitly authorized complete artifact.

`PolicyRuntime` generation numbers restart at `1`; they are not persistent release sequences.
An in-memory activation does not publish desired state. For emergency revocation, an application
controller must stop/fence old workers and ingress, authorize/validate and publish desired state,
preserve its rollback-prevention state, then construct and verify fresh bindings before reopening
traffic. The example below deliberately exposes the memory-only restart trap without running any
real tool side effects:

```bash
python examples/policy_restart_demo.py
```

It shows a memory-only lockdown still allowing a read in a fresh process, a published lockdown
denying it, and a corrupt canonical file producing CLI exit `2` instead of a decision. The example
uses temporary local files, not a deployment controller, production key store or recovery daemon.

Keep the parent directory private and free of untrusted writers. A staging file can contain complete
private policy content, not just metadata. After confirming that its writer has stopped, an operator
may remove that specifically identified abandoned file; never delete potential live staging files
or treat them as approved recovery state. Filesystem cleanup failures can also leave staging files.

**Process-crash atomicity is not power-loss durability.** The writer fsyncs file contents, not the
parent directory entry. Linux documents that a separate
[directory fsync is needed for that metadata](https://man7.org/linux/man-pages/man2/fsync.2.html).
OS crashes, power loss, hardware caches, network/FUSE filesystems, volume failure and multi-file
commit protocols are not established by these tests. Use a deployment/storage system with the
required durability guarantees and test it on the selected filesystem; the library does not claim
a durable transaction, backup service, distributed rollout or persistent rollback anchor.

Reproduce the local process contract after installing the development lock:

```bash
python -m pytest --no-cov integration_tests/test_deployment_process.py
```

Linux and Windows CI run the same actual-process termination, concurrent-create and authenticated
restart cases. The test workers use the exact installed/source package and no optional dependencies;
only their own child processes and temporary files are stopped/changed. No OS reboot is simulated.

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
