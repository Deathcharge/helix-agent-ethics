# Authenticated tool-gate deployments

`ToolGateDeployment` makes policy, context contract, deployment lock, and trusted tool catalog one
coherent document. A `ToolGateDeploymentEnvelope` adds bounded HMAC-SHA-256 authentication and
freshness claims to that complete enforcement unit without adding a runtime dependency.

Use this layer when a deployment moves through storage or a delivery system whose bytes are not
implicitly trusted, and the deployment target can receive a symmetric key through a separate
trusted channel. If policy authors must be unable to impersonate verifiers—or individual signer
identity, public verification, threshold signing, transparency, or supply-chain federation is
required—use an asymmetric system such as Sigstore, TUF, or an organization release service before
calling the ordinary verified-deployment API.

## Envelope contract

Version 1 authenticates all of these fields together:

- the complete embedded `ToolGateDeployment`;
- its domain-separated exact-content `v1:sha256` fingerprint;
- `key_id`, selecting one out-of-band trusted key;
- an exact `audience` for environment or workload binding;
- a positive monotonic `sequence` for caller-anchored rollback rejection;
- whole-second UTC `issued_at` and `expires_at` timestamps;
- the version and `hmac-sha256` algorithm identifiers.

The MAC uses a separate domain from audit chains. Keys are copied from a 32-4096 byte bytes-like
value. Envelopes have a maximum 30-day lifetime; verification accepts at most one hour of explicit
clock skew. A verifier keyring contains no more than 32 named keys, allowing a controlled overlap
during rotation.

The envelope is strict JSON: duplicate or unknown fields, invalid nested artifacts, non-finite
numbers, structural abuse, fingerprint drift, invalid timestamps, and files larger than 5 MiB are
rejected.

## Create and verify with the CLI

Store the raw key outside the deployment artifact and make it readable only by its intended
operator. The CLI never strips whitespace from key files.

Generate a fresh 256-bit key and refuse accidental replacement:

```python
import os

from samsarix_ethics import generate_deployment_auth_key

descriptor = os.open(
    "deployment-auth.key",
    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
    0o600,
)
with os.fdopen(descriptor, "wb") as key_file:
    key_file.write(generate_deployment_auth_key())
    key_file.flush()
    os.fsync(key_file.fileno())
```

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

`authenticate` creates an envelope; it does not claim that the target currently trusts the key,
audience, time, or sequence. `verify-authentication` exits `0` only after all cryptographic and
freshness checks pass. Its JSON/text result contains identity and claim metadata, never policy
rules or catalog capabilities.

`--at` provides a deterministic UTC verification time for CI fixtures. Production callers should
normally omit it and use the current clock. `--clock-skew-seconds` is explicit and bounded from 0
through 3600; keep it at zero when clocks are reliable.

## Bind immediately before use

Parsing is deliberately not authentication. `load_tool_gate_deployment_envelope` returns an
untrusted `ToolGateDeploymentEnvelope`. Verify and bind in one call so expiry is checked at the
enforcement boundary:

```python
from samsarix_ethics import (
    ToolDispatcher,
    load_tool_gate_deployment_envelope,
)

envelope = load_tool_gate_deployment_envelope("coding-agent.authenticated.json")
dispatcher = ToolDispatcher.bind_authenticated_deployment(
    envelope,
    authentication_keys={"prod-2026-q3": deployment_key},
    expected_audience="coding-agent:production",
    minimum_sequence=last_accepted_sequence,
    registered_tools=callbacks,
)
```

`ToolGate.bind_authenticated_deployment` provides the same immediate check when the application
owns scheduling. Both paths authenticate first, exact-match the complete registry, and only then
construct bindings or freeze callback references. Their returned object exposes the immutable
verification as `authenticated_deployment` for operational provenance.

`verify_tool_gate_deployment_envelope` is available for inspection workflows and returns a
`VerifiedToolGateDeployment` with the exact deployment and value-minimized verification metadata.
Do not cache that result as an indefinite authorization: time and the trusted minimum sequence can
change. Re-verify at every load, restart, or binding operation.

## Rotation, expiry, and rollback

- Distribute new key material out of band, then temporarily include both old and new IDs in the
  trusted keyring. Issue new envelopes with the new ID and remove the old ID after the overlap.
- Persist the highest accepted release sequence in protected, durable target state. Pass that
  value as `minimum_sequence`. The library does not persist it because safe storage and atomic
  multi-host promotion are deployment-system responsibilities.
- Use short validity periods. Expiry limits replay/freeze duration only when the verifier has a
  trustworthy clock.
- Sequence equality is allowed so a process can restart on its current desired deployment. If an
  application needs one-time activation, it must atomically consume its own authorization record.
- Never reset the protected minimum sequence merely because a process restarted, and do not
  silently fall back to a previous/staged envelope after missing, corrupt or unauthorized input.
  The [process-recovery contract](POLICY_DEPLOYMENTS.md#interrupted-publication-and-restart) exercises
  fresh-process key, audience, expiry, not-yet-valid, rollback and MAC rejection before callbacks.
- `PolicyRuntime` still provides last-known-good in-process activation after an envelope has been
  authenticated. Remote distribution and host convergence remain external.

## Security boundary

- HMAC is symmetric. Every verifier holding the key can mint an indistinguishable envelope; the
  MAC does not prove individual author, approver, or service identity.
- Authentication is not encryption. The envelope contains complete policy rules, values,
  messages, catalog names, and capability labels.
- `key_id` is a routing label, not trust by itself. Trust comes only from the caller-supplied
  keyring and expected audience.
- A valid envelope can be replayed until expiry while its sequence remains at or above the
  caller's protected minimum. The package supplies no nonce database or distributed desired state.
- Expiry and issuance checks depend on trusted time. Clock skew weakens the effective boundaries.
- Atomic output prevents partial or implicit local replacement. It does not secure file ownership,
  key storage, transport, backups, or filesystem availability.
- The authenticated fingerprint is an equality oracle for private deployments. Protect reports
  and envelopes according to the policy content they identify.
- The feature does not fetch artifacts, negotiate keys, call a KMS, verify Sigstore/TUF metadata,
  provide threshold authorization, or coordinate multiple processes or hosts.

The format schema is available offline with:

```bash
samsarix-ethics schema tool-gate-deployment-envelope
```
