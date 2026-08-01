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
  a detached versioned context builder and schema, and a thirteen-case baseline tool policy pack.

### Changed

- Membership policy literals are validated before evaluation, mixed integer/float comparisons are
  supported, decision sequences serialize as JSON arrays, and file reads remain bounded if a file
  grows during loading.
- Existence conditions reject unused values so runtime validation and the published schema agree.
- Policy condition values are recursively immutable and serialization returns fresh JSON
  containers, preventing retained source documents from mutating live policy behavior.
- Frozen policy-test inputs are thawed into fresh JSON before evaluation, preserving array support
  without weakening the public in-memory JSON contract.

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
