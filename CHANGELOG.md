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
