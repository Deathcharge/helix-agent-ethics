# Keyed audit chains

`HmacAuditChainSink` turns the existing metadata-only `AuditRecord` stream into a locally
verifiable integrity chain. It is useful when an embedding application needs portable evidence
that policy decisions in one single-writer file were not silently edited, inserted, removed from
the middle, reordered, or moved between streams.

This is an application-operated integrity primitive, not a hosted logging service or compliance
ledger. It has no runtime dependency, network access, raw evaluation input, key store, retention
policy, or background process.

## Why this product slice exists

[OPA decision logs](https://www.openpolicyagent.org/docs/management-decision-logs) treat decision
identity, evaluated policy revision, and deliberate input masking as operational policy-engine
concerns. [NIST SP 800-92](https://csrc.nist.gov/pubs/sp/800/92/final) describes log management as
an enterprise security control, while the
[NIST AI RMF Generative AI Profile](https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence)
calls for recording and analyzing generative-AI incidents. Agent Ethics supplies the narrow local
integrity mechanism; an application or log platform still owns collection, access, monitoring,
retention, and incident response.

## Write a chain

Generate and store a raw key separately from the chain. This example writes a new 256-bit key file;
production key storage and file permissions are operator decisions.

```python
from pathlib import Path

from samsarix_ethics import HmacAuditChainSink, ToolGate, generate_audit_chain_key

key = generate_audit_chain_key()
Path("audit-chain.key").write_bytes(key)

sink = HmacAuditChainSink(
    "decisions.chain.jsonl",
    key,
    stream_id="agent-prod-us-east-1",
)
gate = ToolGate(policy, audit_sink=sink)
```

The sink accepts the same synchronous `AuditSink` contract as any application-owned destination.
Each call writes and flushes one compact JSON line before the gate can authorize a callback. A
write, flush, validation, or observed external-change failure raises `AuditChainError`, which is an
`AuditLogError`, so existing fail-closed gate behavior is preserved.

The key must be a 32-4096 byte `bytes`, `bytearray`, or `memoryview`. The sink immediately copies
mutable key inputs and never includes the key in its representation or output. A `stream_id` is a
1-128 character application identifier and is authenticated in every entry.

## Verify and checkpoint

```python
from pathlib import Path

from samsarix_ethics import verify_audit_chain

result = verify_audit_chain(
    "decisions.chain.jsonl",
    Path("audit-chain.key").read_bytes(),
    expected_stream_id="agent-prod-us-east-1",
)
print(result.entry_count, result.head_mac)
```

Or use the non-interactive CLI:

```bash
samsarix-ethics audit-chain verify decisions.chain.jsonl \
  --key-file audit-chain.key \
  --stream-id agent-prod-us-east-1 \
  --format json
```

The key file contains raw bytes; whitespace is part of the key and is not stripped. Reads are
bounded at 4096 bytes. Chain entries are bounded at 256 KiB and streams at 1,000,000 entries or 1
GiB, whichever comes first. Rotate before either limit.
Parsing rejects duplicate JSON keys, blank lines, invalid UTF-8/JSON, unknown fields, non-canonical
record shapes, broken sequence/link values, incomplete final lines, and invalid MACs.

Persist `head_mac` somewhere an attacker who can modify the chain cannot also roll back—for
example, an authenticated deployment record or separate append-only store. Then require it:

```bash
samsarix-ethics audit-chain verify decisions.chain.jsonl \
  --key-file audit-chain.key \
  --expected-head 'v1:hmac-sha256:…'
```

Without an externally retained head, a valid earlier prefix is still a valid chain. `expected_head`
detects that rollback. When resuming a writer after restart, pass the same checkpoint to the sink:

```python
sink = HmacAuditChainSink(
    "decisions.chain.jsonl",
    key,
    stream_id="agent-prod-us-east-1",
    expected_head=retained_head,
)
```

Export the Draft 2020-12 interchange schemas with:

```bash
samsarix-ethics schema audit-chain-entry > audit-chain-entry-v1.schema.json
samsarix-ethics schema audit-chain-verification > audit-chain-verification-v1.schema.json
```

Run `python examples/audit_chain_demo.py` for a temporary end-to-end allowed/denied gate journey.
The demo deletes its ephemeral key and chain at exit.

## Integrity construction

Entry version 1 uses HMAC-SHA-256 over a domain-separated, ASCII, sorted-key, compact canonical JSON
encoding of:

- `audit_chain_version`, fixed at `1`;
- `algorithm`, fixed at `hmac-sha256`;
- `stream_id`;
- one-based `sequence`;
- `previous_mac`, null only for sequence 1;
- the complete metadata-only audit `record`.

The stored `mac` is `v1:hmac-sha256:<64 lowercase hex>`. Verification recomputes every MAC using
constant-time comparison and checks the full sequence and link history. The format does not depend
on Python object serialization or platform-specific newlines.

## Threat boundary and operating rules

- An attacker who can change the chain but does not have the key cannot silently rewrite, insert,
  remove from the middle, reorder, or cross-stream splice entries.
- HMAC authenticates possession of one shared secret; it does not identify an individual reviewer,
  policy author, machine, or tenant. Anyone with the key can rewrite the chain.
- A valid-prefix rollback or whole-file deletion needs a separately protected head/checkpoint to
  detect. Backups and availability remain external.
- Use one sink instance in one writer process per file. The instance serializes threads and rejects
  an observed external file change, but it does not acquire a cross-process lock. Another writer
  can still race between the pre-append check and the append.
- A crash or short write can leave an incomplete final line. Verification fails closed; this
  package does not truncate, repair, or guess which record was committed.
- A successful authorization record proves that policy evaluation and configured audit delivery
  occurred before execution. It does not prove the callback ran, succeeded, had immutable code or
  state, or produced a particular side effect.
- The package does not rotate or erase keys, encrypt records, ship logs, retry delivery, allocate
  tenant streams, or provide exactly-once storage. Put those controls in the embedding system or a
  dedicated log platform.
