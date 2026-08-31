# Changelog

All notable product changes are recorded here.

## 0.1.0 - Unreleased

### Added

- Real-process deployment publication/restart contracts on Linux/Windows, including interrupted
  create/replace, concurrent exclusive creators, and reauthentication before fresh callbacks.
  A runnable emergency-policy example demonstrates why memory-only activation is not persistence.
- Staged artifact cleanup during normal Python interruption, including KeyboardInterrupt and
  SystemExit; documented post-publication error and process-crash versus power-loss boundaries.
- Real verified-TLS MCP client-credentials OAuth acceptance on Linux/Windows, including credential
  isolation, certificate/metadata rejection, token/review revocation, bounded auth response bodies,
  and interrupted token exchange. Documented/tested HTTPX2 request-hook wiring supplies missing
  SDK-generated token-request timeouts; no runtime dependency or authentication service was added.
- Optional MCP HTTP response budgets with separate wire/decoded byte limits, bounded streaming
  gzip/deflate handling, early declared-length rejection, terminal failure latching, owned cleanup,
  and adversarial real-network/pool-pressure tests. HTTPX2 2.12.0 is now a direct client-extra pin
  (already in its lock); the base package remains dependency-free.
- Real loopback Streamable HTTP MCP v2 contracts on Linux/Windows: JSON/SSE and auto/legacy
  workflows, tenant isolation, origin/auth rejection, review-time revocation/drift, audit failure,
  cancellation, timeout and lost-result behavior; documented application-owned HTTP lifecycle.
- Optional MCP v2 (`2.1.1`) client adapter with bounded full-registry discovery/pinning,
  fail-closed outbound policy enforcement, complete-request one-shot review binding,
  explicit continuation reauthorization, per-phase deadlines, a real SDK CI contract,
  and a no-network support workflow. Its `mcp-client` extra is separate from the v1 server extra.
- Installable `samsarix-agent-ethics` Python package with zero runtime dependencies.
- `samsarix-ethics` CLI for policy initialization, validation, and action checks.
- Immutable JSON policy model with bounded parsing and strict validation.
- Explainable `allow`, `deny`, and `review` decisions with deny-overrides semantics.
- Privacy-minimized optional JSONL audit records.
- Real unit and command-level tests with a 90% coverage gate.
- Python 3.11-3.14 CI, package build validation, examples, API docs, and productization record.
- Samsarix LLC ownership metadata, supported contact addresses, Apache-2.0 licensing, NOTICE
  attribution, and explicit trademark guidance.
- Public support guidance, issue forms, code ownership, and a security-aware pull request template.
- Reproducible hashed development lock, commit-pinned CI actions, and installed-wheel CI smoke test.
- Fail-closed sample policy coverage for missing destructive-action approval.
- Bounded batch evaluation and shared validation for parsed and in-memory JSON contexts.
- Bundled Draft 2020-12 policy and policy-test schemas, an executable regression-suite API/CLI,
  privacy-minimized test reports, and a five-case real policy example.
- Dependency-free `ToolGate` enforcement for sync and async callbacks, typed deny/review errors,
  a detached versioned context builder and schema, and a fourteen-case baseline tool policy pack.
- Version-pinned Samsarix Agent Framework adoption evidence, compatibility fixtures, rollback path,
  and an evidence-backed next milestone for application-owned audit sinks.
- Frozen, versioned metadata-only `AuditRecord`, synchronous caller-owned `AuditSink`, and
  `JsonlAuditSink`, with fail-closed pre-authorization delivery, no implicit retries, bounded public
  construction, and an exportable Draft 2020-12 audit-record schema.
- Retained verified wheel/source artifacts for every successful CI build plus least-privilege GitHub
  build-provenance attestations for distributions built from `main`.
- Immutable structured `ToolCallApproval` records, bounded deterministic exact-call fingerprints,
  fail-closed binding in every `ToolGate` path, and an exportable Draft 2020-12 approval schema.
- Frozen `BoundToolGate` registration profiles that keep application-owned tool names and canonical
  capability labels out of untrusted per-call payloads across sync, async, and approval flows.
- Coherent tool-gate deployments that package one verified policy deployment with one exactly
  fingerprinted trusted catalog before complete registry matching and enforcement.
- Freshness-aware authenticated tool-gate deployment envelopes with complete-artifact
  fingerprints, bounded HMAC key rotation, audience/sequence/time checks, atomic I/O, CLI and
  schema support, plus immediate gate and dispatcher authentication paths.
- Node 24-native artifact upload/download actions, an installed-wheel bound-profile smoke test, and
  monthly GitHub Actions dependency update proposals.
- Current exact-SHA checkout/setup actions and direct `actions/attest` v4 build provenance,
  replacing the compatibility wrapper for new attestation implementations.
- Canonical streamed `fingerprint_policy` provenance, propagated through engines, gates, decisions,
  policy-test reports, CLI validation, and privacy-minimized audit record v1.
- Versioned, privacy-minimized baseline-versus-candidate policy impact comparison API, CLI, schema,
  CI exit behavior, and a runnable sensitive-read rollout example.
- Versioned, privacy-minimized policy rule-coverage API, CLI, schema, exact CI threshold behavior,
  and a 100%-covered twelve-rule tool-policy example.
- Versioned, value-minimized policy authoring diagnostics with five stable finding codes, explicit
  severity gates, a bundled report schema, and strict checks over every example policy.
- Deterministic layered policy composition API/CLI, a versioned value-minimized provenance schema,
  atomic output writes, and a support-agent example that centrally combines organization
  guardrails with application permissions while retaining the ordinary policy toolchain.
- Baseline-authoritative shadow policy evaluation API/CLI, strict versioned input-free telemetry,
  exact baseline/candidate provenance and engine durations, candidate error observation, shared
  comparison semantics, and a runnable restricted-data rollout example.
- Versioned, immutable application context contracts with deployment-time policy path/operator
  checking, runtime required/type enforcement, `PolicyEngine` and `ToolGate` integration, a bundled
  Draft 2020-12 schema, and a runnable tool-call contract—all with zero runtime dependencies.
- Contract-aware regression, coverage, comparison, and shadow APIs/CLI so pre-deployment and
  rollout evidence enforces the same declared fact boundary as production evaluation.
- Canonical domain-separated context-contract fingerprints and strict versioned deployment locks
  that bind exact policy/contract content across CLI validation, live checks, `PolicyEngine`, and
  `ToolGate`, with a bundled schema and continuously verified real deployment example.
- Deterministic value-minimized policy explanations with rule/condition match, miss, and
  short-circuit status; decisive/default provenance; optional contract fingerprint; CLI/API/schema;
  and no serialized input, condition values, `$ref` targets, or authored messages.
- Atomic last-known-good `PolicyRuntime` activation with optional compare-and-swap generations,
  whole-batch generation pinning, coherent privacy-minimized status/schema, verified
  policy/contract/lock swaps, and live `ToolGate`/`BoundToolGate` integration.
- Strict deterministic `PolicyDeployment` documents containing one complete policy, optional
  contract, and mandatory matching lock; bounded single-read loading, atomic exclusive/forced
  output, CLI create/verify, self-contained schema, runtime activation, and a drift-checked real
  deployment fixture.
- Immutable gate-specific `PreparedToolCall` objects plus bounded `ToolGate.evaluate_many` and
  `enforce_many` preflight, with full-batch validation before audit delivery, one-generation runtime
  consistency, exact approval preservation, within-batch duplicate object/approval-ID rejection,
  streaming context thaw, and no package-owned callback scheduling.
- A 100%-rule-covered coding-agent policy, context contract, verified single-file deployment, and
  runnable batch demo for contained workspace reads and approval-bound process/network/write risk;
  missing containment fails closed even when the raw policy is used without its contract.
- Backward-compatible complete batch diagnostics on typed tool-call block exceptions, retaining
  every metadata-only decision and the first blocked index from one evaluation for multi-call
  review surfaces without duplicate decision IDs or audit delivery.
- Strict versioned trusted tool-capability catalogs with canonical fingerprints, bounded loading,
  bundled schema and CLI validation, exact registry-name drift checks, immutable gate-specific
  binding maps, and a coding-agent catalog that never trusts remote MCP annotations.
- Framework-neutral `ToolDispatcher` bindings that exact-match and snapshot final Python callback
  references, authorize before sync/async execution, and preflight complete batches before ordered
  dispatch without claiming transactional side effects or callable-code authentication.
- Keyed metadata-only HMAC-SHA-256 audit chains with strict bounded verification, single-instance
  thread serialization, restart checkpoints, valid-prefix rollback detection, CLI/schema support,
  adversarial integrity tests, and an end-to-end gate example.
- An optional fail-closed OpenAI Agents SDK adapter for strict top-level `FunctionTool` objects,
  with native review interruptions, fresh post-approval enforcement, exact-call approval binding,
  resolved-call store cleanup, fail-visible storage exhaustion, bounded duplicate-safe raw argument
  parsing, preserved existing controls, a CI-executed no-network example, and an exact
  `openai-agents==0.18.3` hashed CI contract.
- An optional OpenTelemetry decision-event sink with a stable privacy-minimized `samsarix.*`
  attribute contract, exact `opentelemetry-api/sdk==1.44.0` integration lane, no-network example,
  and bounded ordered `CompositeAuditSink` fan-out for durable storage plus trace correlation.
- Optional exact-registry LangChain `1.3.14` sync/async tool middleware with final raw-argument
  enforcement, native LangGraph interrupts, strict fingerprint-bound approval resume, generic
  rejection results, a no-network real-agent example, and a dedicated hashed CI contract.
- Optional exact-registry Pydantic AI `2.22.0` wrapper toolset with native deferred approvals,
  strict Samsarix evidence on resume, atomic single-use approval consumption, fresh current-policy
  enforcement, a no-network real-agent example, adversarial tests, and a dedicated slim
  hash-locked CI contract.
- Optional exact-registry MCP Python SDK `1.28.1` server handler with fresh request-scoped facts,
  application-owned async review, one-shot fingerprint-bound approval evidence, immutable tool
  definition snapshots, a no-network in-memory client/server example, adversarial tests, and a
  dedicated hash-locked CI contract.

### Changed

- Text policy explanations now display the configured context-contract fingerprint, matching JSON
  provenance, and public API/schema inventories include the complete explanation surface.
- Membership policy literals are validated before evaluation, mixed integer/float comparisons are
  supported, decision sequences serialize as JSON arrays, and file reads remain bounded if a file
  grows during loading.
- Existence conditions reject unused values so runtime validation and the published schema agree.
- Policy condition values are recursively immutable and serialization returns fresh JSON
  containers, preventing retained source documents from mutating live policy behavior.
- Frozen policy-test inputs are thawed into fresh JSON before evaluation, preserving array support
  without weakening the public in-memory JSON contract.
- The bounded `subset_of` operator lets allow rules reject mixed known and unknown capability sets.
- The bundled tool-call policy now consumes the reserved structured approval record instead of an
  unbound `context.human_approved` boolean.

### Removed

- Broken duplicate ethics validators and the non-functional compliance module.
- Mock-only tests, unrelated runtime dependencies, stale portal page, and conflicting legacy setup
  metadata.
- Conflicting Business Source and proprietary license files, stale Helix branding, and unsupported
  contact details.

### Compatibility

The repository previously claimed version 1.0.0 but could not parse its own package metadata or
import its public API. `0.1.0` establishes the first supported package contract under the Samsarix
name; the unreleased Helix import and CLI names are not compatibility targets.
