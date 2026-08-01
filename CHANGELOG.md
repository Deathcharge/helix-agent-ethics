# Changelog

All notable product changes are recorded here.

## 0.1.0 - Unreleased

### Added

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

### Changed

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
