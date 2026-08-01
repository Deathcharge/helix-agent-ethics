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
- Versioned policy/test schemas, policy regression suites, and bounded batch evaluation are in the
  release candidate; preserve their compatibility fixtures as the language evolves.
- [x] Add one fail-closed downstream integration with a consumer-owned contract test.
- A fail-closed in-process tool gate and baseline tool-capability policy pack are integrated into
  Samsarix Agent Framework at an exact Agent Ethics commit.
- [x] Expose one immutable metadata-only audit record to a caller-supplied sink while preserving
  the existing JSONL API and fail-closed behavior.
- [x] Bind decisions and audit evidence to the exact canonical policy body, independent of
  operator-authored policy ID/version labels.
- [x] Reuse bounded regression suites for deterministic, input-free baseline/candidate impact
  reports before policy rollout.
- [x] Reuse the same suites for input-free rule coverage and explicit CI thresholds so passing
  expectations cannot silently leave policy branches unexercised.
- [x] Add stable severity-coded authoring diagnostics without condition-value disclosure or
  heuristic claims about application intent.
- [x] Add deterministic central composition for organization guardrails plus application
  permissions, with exact source provenance and one ordinary deployable policy artifact.
- [x] Add baseline-authoritative shadow evaluation so live candidate changes/errors can be
  measured without granting the candidate enforcement authority or serializing action input.

## Release candidate

- Build and install the wheel in a clean environment.
- [x] Prove one real consumer and a versioned compatibility fixture.
- Publish only after package-name ownership, licensing, provenance, and rollback are recorded.

Current hardening backlog:

- No published package/release, public third-party adopter, or production deployment evidence.
- The first verified consumer is a private Samsarix repository; its evidence is maintainer-visible,
  not a publicly reproducible external case study.
- Installed-wheel smoke coverage, retained CI distributions, and GitHub build-provenance
  attestations exist. PyPI project ownership, Trusted Publishing, protected release approval, and
  durable registry publication evidence are not yet configured.
- The “ethics” name may still overpromise relative to a deterministic authorization/policy gate.
- Local audit logs are operational records, not tamper-evident compliance evidence.
- Caller-owned sinks provide a delivery seam, not built-in HTTP, queues, retries, exactly-once
  storage, retention, or a hosted audit service.
- Migration from any surviving `helix_ethics` callers is destructive; old compatibility imports are not retained.

## Samsarix adoption

- Define a public API, event, schema, artifact, or deployment contract before connecting to Samsarix Unified.
- [x] Add a consumer-owned contract fixture covering authentication, privacy, limits, errors, and version compatibility.
- Make one implementation canonical; remove or freeze duplicate behavior only after parity and rollback are proven.
- [x] Record an owner, support level, compatibility window, and measurable adoption signal.

## Completion evidence

A milestone is complete only when its exact commit, commands and results, artifact digest, consumer or deployment, and rollback path are recorded in a pull request or release record. README claims must not exceed that evidence.
