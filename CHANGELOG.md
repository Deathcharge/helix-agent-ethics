# Changelog

All notable product changes are recorded here.

## 0.1.0 - Unreleased

### Added

- Installable `helix-agent-ethics` Python package with zero runtime dependencies.
- `helix-ethics` CLI for policy initialization, validation, and action checks.
- Immutable JSON policy model with bounded parsing and strict validation.
- Explainable `allow`, `deny`, and `review` decisions with deny-overrides semantics.
- Privacy-minimized optional JSONL audit records.
- Real unit and command-level tests with a 90% coverage gate.
- Python 3.11-3.14 CI, package build validation, examples, API docs, and productization record.

### Removed

- Broken duplicate ethics validators and the non-functional compliance module.
- Mock-only tests, unrelated runtime dependencies, stale portal page, and conflicting legacy setup
  metadata.

### Compatibility

The repository previously claimed version 1.0.0 but could not parse its own package metadata or
import its public API. `0.1.0` establishes the first supported package contract. Publication naming
and versioning remain an owner decision.
