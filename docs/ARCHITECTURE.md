# Architecture

## Product boundary

Samsarix Agent Ethics is an embedded policy decision point. The caller supplies trusted policy
configuration and an action-context object, receives an explainable decision, and remains
responsible for enforcement immediately before the protected operation.

```text
trusted policy JSON ──> bounded parser ──> immutable Policy ─┐
                                                            ├─> PolicyEngine ─> Decision
untrusted action JSON ─> bounded parser ──> context object ──┘                  │
                                                                               ├─> optional metadata-only JSONL
                                                                               └─> ToolGate ─> callback or typed block
```

There is no network service, identity provider, database, model provider, or dependency on
the legacy `helix-unified` repository.

## Components

- `models.py`: strict schema validation and immutable policy/decision values.
- `validation.py`: shared bounded JSON validation for parsed and in-memory contexts.
- `engine.py`: dotted-field resolution, typed condition operators, rule matching, and precedence.
- `io.py`: bounded UTF-8 JSON parsing, safe sample generation, and audit append.
- `schema.py` and `schemas/`: offline access to versioned Draft 2020-12 contracts.
- `testing.py`: bounded regression suites and input-free aggregate reports.
- `gate.py`: normalized tool-call contexts and fail-closed sync/async callback enforcement.
- `cli.py`: non-interactive commands, rendering, stderr discipline, and exit codes.
- `__init__.py`: deliberate public Python API.

## Key decisions

### Explicit, deterministic facts

The engine evaluates caller-supplied JSON facts and never invokes an LLM. This keeps decisions
reproducible, offline, testable, and cost-free. It also means the caller must supply accurate facts.

### Validation before evaluation

Unknown fields/operators, duplicate IDs, invalid references, malformed JSON, non-finite numbers,
non-JSON in-memory values, and bounded-resource violations are rejected before a decision. Operator
type errors stop the evaluation. An embedding application must treat errors as non-authorization.

### Schemas plus executable examples

The JSON Schemas support editors and generic CI validators; the Python validators remain
authoritative for semantic and aggregate constraints. Policy-test suites evaluate real engine
behavior and separate unmet expectations from evaluation errors. Reports omit raw inputs just as
the audit helper does.

### Deny and review override allow

The outcome order is `deny > review > allow > default_effect`. This makes guardrail rules
independent of future grants. `warn` and `audit` are descriptive matches, not grants.

### No embedded expression language

The policy language is intentionally smaller than OPA or Cedar. It excludes regex, templates,
dynamic functions, imports, and network lookups to limit injection, denial-of-service, and policy
analysis risk. Cross-field comparison uses the explicit `{"$ref": "path.to.field"}` form.

### Privacy-minimized audit

Raw action context can contain credentials or personal data, so the built-in audit record stores
only decision metadata. Audit durability is local best effort (`append` plus `fsync`), not an
immutable or cross-process ordered ledger.

### Enforcement remains local and immediate

`ToolGate` closes the common integration gap between receiving a decision and invoking an
in-process tool. It evaluates a detached context, writes the optional audit record, and calls a
callback with the evaluated detached arguments only for `allow`. Deny and review outcomes are
distinct typed exceptions.
Applications with durable approval workflows should store their own pending-call state, then
re-evaluate with fresh trusted facts immediately before execution.

## Trust boundaries

- **Policy authors/operators** are trusted to define correct rules and secure policy files.
- **Evaluation input** may be attacker-controlled and is bounded and type-checked.
- **Embedding application** owns authentication, authorization, fact integrity, enforcement,
  concurrency, and the protected side effect.
- **Tool capability labels** are trusted application facts; model output must not assign its own
  permissions or approval state.
- **Filesystem/audit operator** owns access control, rotation, retention, backups, and tamper
  detection for audit files.

## Distribution

The smallest distribution is a Python wheel and source distribution with console entry point.
Publishing is owner-gated. A hosted service would add authentication, tenancy, availability,
privacy, and cost risks without improving the repository's core evidence-backed use case.
