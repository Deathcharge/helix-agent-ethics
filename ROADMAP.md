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
- [x] Add one public, reproducible OpenAI Agents SDK `FunctionTool` adapter with native approval
  routing, exact-version dependency locking, a real SDK contract test, and explicit unsupported
  execution paths.
- [x] Add exact-registry LangChain sync/async middleware with final-argument enforcement, native
  LangGraph review interrupts, fingerprint-bound resume, exact-version locking, and a real
  no-network agent contract.
- [x] Add an exact-registry Pydantic AI wrapper toolset with native deferred review,
  fingerprint-bound Samsarix resume evidence, exact slim-version locking, and a real no-network
  agent contract.
- [x] Add exact-registry enforcement at the stable MCP Python SDK server handler, with fresh
  request facts, one-shot application-owned review, exact-version locking, and a real in-memory
  client/server contract.
- [x] Add MCP v2 client-side enforcement with paginated definition pinning, explicit single-round
  continuation authorization, full-request review binding, and a separate exact-version CI lane.
- [x] Expose one immutable metadata-only audit record to a caller-supplied sink while preserving
  the existing JSONL API and fail-closed behavior.
- [x] Correlate metadata-only decisions with a caller-owned OpenTelemetry trace through an optional
  exact-version-tested event sink, while retaining durable storage through bounded ordered fan-out.
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
- [x] Add application context contracts that reject undeclared policy facts and incompatible
  operator types before deployment, then enforce required fact types at the runtime boundary.
- [x] Apply one shared context contract across policy regression, coverage, comparison, and shadow
  workflows so lifecycle evidence cannot silently use weaker input validation than production.
- [x] Bind exact reviewed policy and context-contract content in a versioned deployment lock and
  fail closed on drift at CLI, engine, and tool-gate activation boundaries.
- [x] Add operator-facing evaluation explanations that share production semantics while omitting
  action input, policy values, and authored messages.
- [x] Add last-known-good atomic in-process activation with coherent generation status,
  compare-and-swap conflict detection, whole-batch consistency, and live `ToolGate` integration.
- [x] Package a policy, optional contract, and mandatory matching lock as one strict bounded
  deployment unit for coherent transport, restart, atomic output, and runtime activation.
- [x] Add immutable prepared tool calls and all-calls-before-dispatch batch enforcement, with one
  checked coding-agent deployment covering workspace, process, network, destructive, and sensitive
  capabilities under conservative MCP trust defaults.
- [x] Add a standalone versioned tool-capability catalog with exact-content provenance and strict
  full-registry matching before immutable gate bindings are created.
- [x] Package a verified policy deployment and exact trusted catalog into one bounded coherent
  tool-gate deployment with atomic output and fail-closed registry binding.
- [x] Bind verified catalogs to immutable final callback snapshots with framework-neutral sync,
  async, and all-calls-before-dispatch batch execution.
- [x] Add a bounded keyed metadata-only audit chain and strict verifier for single-writer local
  evidence, including externally anchored valid-prefix rollback detection without claiming a
  cross-process ledger or hosted log service.
- [x] Add authenticated complete tool-gate deployment envelopes with exact audience, bounded
  validity, key rotation, and caller-anchored monotonic sequence enforcement while keeping
  asymmetric identity and distributed desired state outside the library.

## Release candidate

- Build and install the wheel in a clean environment.
- [x] Prove one real consumer and a versioned compatibility fixture.
- Publish only after package-name ownership, licensing, provenance, and rollback are recorded.

Current hardening backlog:

- [x] Provide bounded, correctness-checked performance evidence for policy scaling, real coding-agent
  dispatch/batches, shadow and local audit fsync, with strict report comparison and Linux/Windows CI
  artifacts. Controlled deployment load/SLO acceptance remains distinct from these local observations.

- [x] Add opt-in encoded/decoded MCP HTTP response budgets before SDK JSON/SSE parsing, with
  fail-closed transport latching and real gzip/deflate, cancellation and pool-pressure evidence.
- [x] Exercise verified TLS and the stock SDK client-credentials OAuth provider against separate
  loopback resource/authorization servers: credential isolation, revocation, scoped grants,
  certificate/metadata rejection, bounded discovery/token bodies, and interrupted token exchange.
- [x] Exercise actual publisher process death and fresh-process enforcement for all four artifact
  writers, concurrent exclusive creation, and authenticated restart rejection on Linux/Windows.
  Clean staged files during ordinary Python interruption and document ambiguous post-publication
  errors. This is not OS/power-loss durability or a persisted desired-state/sequence service.
- [x] Verify post-grant MCP refresh rotation/omission, same-provider concurrency, review-time
  rejection, storage divergence, response budgets and interruption over TLS. Seeded grants/cached
  metadata are not browser authorization, issuer discovery or durable credential recovery.
- Body budgets are not whole-process memory/CPU, request/header, rate or workflow quotas.
  Real identity-provider/proxy acceptance, durable credential lifecycle and deployment crash recovery
  remain deployment work. Local ephemeral TLS/OAuth fixtures are not a production auth service.
- No published package/release, public third-party adopter, or production deployment evidence.
- The first verified consumer is a private Samsarix repository; its evidence is maintainer-visible.
  Its current default branch has also passed paired Windows/Python 3.11 installed-wheel
  qualification against its original Agent Ethics pin and the attested `4d5efad` candidate:
  14 policy contracts and 239 collected consumer tests per lane. Its source pin is unchanged;
  this is not a new hosted-matrix, MCP-extra, external-customer or production claim. See
  [the exact qualification record](docs/ADOPTION.md#current-default-qualification-2026-08-31).
  The public OpenAI, LangChain, Pydantic AI, MCP, and OpenTelemetry adapters are reproducible
  integration evidence,
  not external adopter case studies.
- LangChain review checkpoints intentionally contain proposed tool arguments. Reviewer identity,
  checkpoint confidentiality, expiry, one-time resume, and multi-call transactionality remain
  application-owned.
- MCP review requests intentionally contain proposed tool arguments and capability labels.
  Reviewer identity/authentication, confidentiality, timeout/cancellation, and side-effect
  transactionality remain application-owned; only low-level stable-SDK tool calls routed through
  the adapter are covered.
- MCP v2 client review also contains metadata and continuation state. Pinning discovers advertised
  drift, not hidden server code changes, cryptographic target identity, or atomic remote state.
  V1 server and v2 client SDK contracts require separate environments.
- Installed-wheel smoke coverage, retained CI distributions, and GitHub build-provenance
  attestations exist. PyPI project ownership, Trusted Publishing, protected release approval, and
  durable registry publication evidence are not yet configured.
- The “ethics” name may still overpromise relative to a deterministic authorization/policy gate.
- Plain local audit logs remain operational records. The optional keyed chain supplies
  single-writer integrity evidence, not compliance evidence, individual signatures, availability,
  or cross-process coordination; rollback detection depends on an externally protected head.
- Caller-owned sinks provide a delivery seam, not built-in HTTP, queues, retries, exactly-once
  storage, retention, or a hosted audit service.
- OpenTelemetry events provide sampled correlation only. SDK/exporter configuration, propagation,
  collector delivery, backend access, and durable authorization evidence remain caller-owned.
- Atomic runtime generations are process-local; durable desired state, artifact distribution,
  authenticated deployment, restart recovery, and multi-host convergence remain caller-owned.
- Complete tool-gate deployments can now be wrapped in a freshness-aware symmetric HMAC envelope.
  Public signer identity, immutable OCI/repository transport, threshold authorization, trusted
  clock and sequence persistence, Sigstore/TUF policy, and multi-host promotion remain caller-owned.
- Tool catalogs now have deployment-level pinning and immutable callback-reference snapshots;
  authenticated distribution, freshness, approval, callable code identity, mutable callback state,
  and semantic correctness remain caller-owned.
- Migration from any surviving `helix_ethics` callers is destructive; old compatibility imports are not retained.

## Samsarix adoption

- Define a public API, event, schema, artifact, or deployment contract before connecting to Samsarix Unified.
- [x] Add a consumer-owned contract fixture covering authentication, privacy, limits, errors, and version compatibility.
- Make one implementation canonical; remove or freeze duplicate behavior only after parity and rollback are proven.
- [x] Record an owner, support level, compatibility window, and measurable adoption signal.

## Completion evidence

A milestone is complete only when its exact commit, commands and results, artifact digest, consumer or deployment, and rollback path are recorded in a pull request or release record. README claims must not exceed that evidence.
