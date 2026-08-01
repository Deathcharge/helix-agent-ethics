# Samsarix Agent Ethics roadmap

This roadmap separates four gates: merge, release, publication, and flagship adoption. Passing one does not imply the next.

## Product boundary

Portfolio role: **reusable library or sdk**. Keep this as a small, independently versioned package. Samsarix Unified should consume it only through a public API adapter; private monorepo imports and copied implementations are out of scope.

Current disposition: The productized baseline is merged. Release, publication, and flagship
adoption remain separate evidence-based decisions.

## Stabilize the productized default

- Keep the default branch buildable from a clean checkout and preserve exact-head CI evidence.
- Keep Samsarix LLC branding, package identity, license metadata, and compatibility aliases internally consistent.
- Preserve the pre-productization default under a rollback ref before merging; do not delete legacy history.
- Review priority: publish policy schema and one fail-closed integration.
- Review priority: add policy test fixtures and batch evaluation for CI and pre-deployment use.
- Review priority: publish focused policy packs for high-value agent tool boundaries.

## Release candidate

- Build and install the wheel in a clean environment.
- Prove one real consumer and a versioned compatibility fixture.
- Publish only after package-name ownership, licensing, provenance, and rollback are recorded.

Current hardening backlog:

- No published package/release, policy JSON Schema, or downstream integration evidence.
- Installed-wheel smoke coverage exists locally and in CI, but publication provenance and signing
  are not yet configured.
- The “ethics” name may still overpromise relative to a deterministic authorization/policy gate.
- Local audit logs are operational records, not tamper-evident compliance evidence.
- Migration from any surviving `helix_ethics` callers is destructive; old compatibility imports are not retained.

## Samsarix adoption

- Define a public API, event, schema, artifact, or deployment contract before connecting to Samsarix Unified.
- Add a consumer-owned contract fixture covering authentication, privacy, limits, errors, and version compatibility.
- Make one implementation canonical; remove or freeze duplicate behavior only after parity and rollback are proven.
- Record an owner, support level, compatibility window, and measurable adoption signal.

## Completion evidence

A milestone is complete only when its exact commit, commands and results, artifact digest, consumer or deployment, and rollback path are recorded in a pull request or release record. README claims must not exceed that evidence.
