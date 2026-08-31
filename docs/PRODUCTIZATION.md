# Productization record

Last updated: 2026-08-31

## Current increment: real MCP v2 HTTP boundary

Baseline: clean `main` at `b19de71785f817f2739869b98e4516f8b6f3b863` (PR #41),
re-fetched and checked on 2026-08-31. Work branch: `codex/mcp-http-contract`.
The client implementation already passed its in-memory contract, but production-facing network
claims lacked real socket evidence. No runtime API or dependency changes were needed for this
increment; no sibling repositories were touched.

Added 23 real loopback TCP tests alongside the existing 17 in-memory contracts. They cover
auto/legacy negotiation, JSON/SSE, allow/deny/review, authenticated principal isolation despite
forged metadata, concurrent clients, real 401/403 rejection, credential revocation and registry
drift during approval, unknown tools, audit outages, timeouts, cancellation, and response loss
after handler execution. Tests count wire requests and handler invocations, use random ephemeral
credentials, and close the caller-owned HTTP client and bounded local server/socket lifecycle.
Both Linux and Windows are now included in the client CI matrix.

Research used the current official [transport guide](https://py.sdk.modelcontextprotocol.io/client/transports/)
and [Streamable HTTP specification](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http).
Deployment guidance now shows application-owned HTTP configuration and scopes its auth, TLS,
redirect, proxy, connection-limit and lifecycle responsibilities. Observed SDK errors can appear
as nested exception groups at context exit; 401/403 can become generic MCP errors. OAuth hooks
can independently replay requests: the adapter's no-retry contract is not an HTTP exactly-once claim.

Verification on Windows/Python 3.11.9: `python -m pytest --no-cov
integration_tests/test_mcp_client_sdk.py integration_tests/test_mcp_client_http.py` passed
**40 tests**. `python -m ruff check .`, `python -m mypy` (40 source files), `python -m pip check`,
and `python examples/mcp_client_policy_demo.py` passed in the applicable locked environments.
The full local core rerun passed **619 tests, zero failures/errors/skips, and 95.22% branch-inclusive
coverage**. Build/Twine checks passed for wheel and sdist. A separate `--no-deps` wheel environment
without MCP passed import, CLI version, policy validation and read/delete decisions (exit 0/3).
The wheel excludes the test authentication fixture. Changed-document local links resolve.

[PR #42](https://github.com/Deathcharge/samsarix-agent-ethics/pull/42) records exact-head verification.
Its initial CI run `33381178508` passed all 11 test jobs, including the 40 real SDK/client contracts
on Linux and Windows. Main-only attestation and any review-follow-up evidence belong to the final
PR/release record, not an assumption based on that initial run.

Release disposition remains a **release candidate with named external gates**, not verified
production hosting or external product-market fit. No known local P0 was found in this increment.
Ordered remaining work:

1. P1 engineering: bound hostile remote response resources before SDK decoding and exercise
   connection-pool pressure; current registry limits apply after decoding.
2. P1 deployment acceptance: real TLS/OAuth/proxy and process-crash recovery in an owner-selected
   environment; test-only bearer auth is not a production authentication implementation.
3. P1 release/adoption gates: owner-controlled PyPI identity/Trusted Publisher and protected release
   approval, licensing review, and a genuine external adopter evaluation. No package/tag/release
   or production deployment was created.
4. P2: independently measured latency/load budgets and more deployment-specific reference workflows.

Final engineering review checks focus on false-positive tests, cleanup, secret handling, transport
retries, and overstated guarantees. A lost-result test deliberately runs the remote handler first:
an allow record alone proves neither successful delivery nor rollback. Test fixtures are never
packaged as an auth service. Final documentation review also distinguishes per-tenant HTTP clients
from per-tenant auth/token storage and explicitly excludes untested SSE event-store resumption.
No paid service or runtime operating cost was introduced.

## Previous increment: MCP v2 client enforcement

Baseline revalidated at `a99233a52da50824c621ea83d75053fe99c43f51` on clean, synchronized
`main`; work continued on `codex/mcp-client-policy`. The preceding MCP v1 server contract was
retested (13 focused core/real-SDK tests passed). No sibling repository is required or modified.

Primary-source research on 2026-08-31 found [MCP 2.1.1](https://pypi.org/project/mcp/2.1.1/)
current and [v1 in maintenance](https://py.sdk.modelcontextprotocol.io/migration/). The v2
[client API](https://py.sdk.modelcontextprotocol.io/client/) can drive automatic input-required
rounds, while its public session API exposes a one-round call. This changed the implementation
plan: add a separate exact v2 client extra and CI environment while retaining the v1 server API.

Implemented: complete bounded paginated discovery, trusted-catalog equality, canonical definition
pinning/recheck, captured session methods, fresh actor/context facts, full-request one-shot
review evidence, explicit continuation reauthorization, final current-policy enforcement,
fail-closed audit delivery, and bounded async phase deadlines. No automatic retries, resolver,
hosted proxy, new credential store, or dependency in the base package was introduced.

The no-network support workflow reads a ticket, reviews a reply, and blocks deletion before
dispatch. Unit coverage exercises malformed discovery, aggregate bounds, replay, mutations,
actor/context/policy changes, callback failures and audit failure. Real SDK tests exercise actual
pagination, auto/legacy connections, request normalization, progress, input-required continuation,
drift, timeout, cancellation and server errors. See [MCP_CLIENT.md](MCP_CLIENT.md).

Remaining acceptance gates: remote-transport deployment tests, external adopter feedback, and
owner-controlled publication. Definition pinning does not authenticate server code or make remote
side effects atomic. A timed-out authorized call may already have executed remotely. V1 server
and v2 client extras are intentionally incompatible in one environment.

Local verification on Python 3.11.9: the complete core suite passed **619 tests with 95.22%
branch-inclusive coverage**; all **17 real MCP v2 contract tests** and the no-network demo passed.
Ruff format/check and strict mypy (40 source files) passed. These measurements supersede the older
increment's test counts retained below; they are not a claim of exhaustive correctness.

Build and Twine distribution checks passed. The development/client locks resolved together for
Linux x86-64, and `pip-audit -r requirements-mcp-client.lock --no-deps --disable-pip` reported no
known vulnerabilities on this date (advisory matching is not a security guarantee). The retained
v1 adapter's 13 focused tests passed again after the new public exports were added.

PR review follow-up: declare the directly used AnyIO dependency explicitly (`4.14.2`, already in
the tested lock), repair release-guide list nesting, and replace growing-prefix discovery scans
with per-entry validation and incremental aggregate item/byte accounting plus one final digest.
Regression tests preserve the previous canonical fingerprint, exact byte boundary (including
escaped Unicode), page-spanning aggregate limits, and one registry hash for 64 tools.

The following HTTP increment addresses the former loopback-transport evidence gap; production
OAuth/TLS/proxy acceptance remains separate.

## Current repository assessment

The repository was extracted from `helix-unified` as an ethics framework, then accumulated three
incompatible implementations: a potentially useful standalone policy engine, a heuristic
coordination-score validator, and a purported SOC 2 compliance module. The checked-in package did
not install, import, or test those implementations. Documentation instead described absent
examples, CI, integrations, and deployment behavior and labeled the repository production-ready.

The strongest original evidence was the rule-based engine in `policy/engine.py`: explicit JSON
conditions, allow/deny decisions, and decision audit concepts. That evidence supports a narrow
developer tool, not a compliance platform or general moral-reasoning system.

### Baseline state

- Branch: `main`, tracking `origin/main`; worktree clean.
- Revision: `5d28fd287e97c2f23b8b0b8e32fb1d7c999f22e3`.
- Local branches: only `main`; remote branch: `origin/main`.
- 27 tracked in-scope files; no workflow, examples directory, `SECURITY.md`, changelog, or lockfile.
- No pre-existing user changes were present. Implementation work moved to
  `codex/productize-agent-ethics` before repository edits.

Baseline commands were run with system Python 3.11.9:

| Command | Actual baseline result |
| --- | --- |
| `python --version` | passed: Python 3.11.9 |
| `python -m pip install -e . --no-deps` | failed: `pyproject.toml` invalid at line 13 |
| `python -m pytest` | failed before collection: invalid `pyproject.toml` |
| `python -m ruff check .` | failed before lint: invalid `pyproject.toml` |
| `python -m mypy src policy` | failed before checking: invalid `pyproject.toml` |
| `python -m build` | failed before build: invalid `pyproject.toml` |
| `python -c "import helix_ethics"` | failed: package not installed |
| `python -m compileall -q src policy tests` | passed; syntax compilation did not prove imports |

The README's `pip install -r requirements.txt` was not run against the system interpreter because
the file requested a large unrelated web/LLM/database/Discord/Celery stack. A clean `.venv` was
used after metadata correction.

## Chosen product

**Samsarix Agent Ethics is a zero-runtime-dependency Python library and CLI that acts as a local,
deterministic policy decision point for autonomous agent actions.**

The target user is a Python developer integrating an agent, tool runner, or workflow that needs a
small explicit gate before consequential operations.

The primary journey is:

1. install from source;
2. initialize or select a JSON policy;
3. validate it before use;
4. submit a JSON action context through the CLI or library;
5. receive an explained `allow`, `deny`, or `review` decision;
6. enforce that result and optionally append a metadata-only audit record.

This product exists independently of the legacy `helix-unified` repository: it is offline,
embeddable, has a deliberate public API, requires no private service, and can guard any Python
agent system.

## Research-backed decisions

Bounded review used current primary sources:

- [Cedar authorization semantics](https://docs.cedarpolicy.com/auth/authorization.html) support
  explicit grants, default deny, forbid-overrides-permit, and decision diagnostics.
- [Cedar policy validation](https://docs.cedarpolicy.com/policies/validation.html) separates policy
  validation from request evaluation to catch authoring errors early.
- [OPA decision logs](https://www.openpolicyagent.org/docs/management-decision-logs) emphasize
  decision identity and masking/removing sensitive input in logs.
- [OpenTelemetry Python instrumentation](https://opentelemetry.io/docs/languages/python/instrumentation/)
  recommends API-only dependencies for instrumentation libraries and application-owned SDK setup;
  its tracing API models events as occurrences within an active operation. A metadata-only decision
  event can add production correlation without owning an exporter or copying sensitive tool data.
- [NIST SP 800-92](https://csrc.nist.gov/pubs/sp/800/92/final) treats log management as a practical
  enterprise security control, while the
  [NIST AI RMF Generative AI Profile](https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence)
  calls for recording and analyzing generative-AI incidents. A bounded local integrity chain is a
  defensible library feature; a generic log service or duplicate approval database is not.
- [OPA signed bundles](https://www.openpolicyagent.org/docs/management-bundles) authenticate the
  complete bundle before activation and retain the last known good bundle on failure, while
  [The Update Framework](https://theupdateframework.github.io/specification/) uses monotonic
  versions and expiry against rollback/freeze attacks. This supports a bounded authenticated
  deployment envelope without claiming a full update framework.
- [NIST AI RMF Core](https://airc.nist.gov/airmf-resources/airmf/5-sec-core/) emphasizes documented
  governance roles and human-AI oversight rather than treating an automated score as certification.
- [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0) requires redistribution of the
  license and applicable notices, includes an explicit patent grant, and does not grant trademark
  rights. The [Apache application guidance](https://www.apache.org/legal/apply-license) recommends
  an unmodified `LICENSE`, a `NOTICE`, and short source headers.
- [Mozilla's MPL 2.0 FAQ](https://www.mozilla.org/en-US/MPL/2.0/FAQ/) confirms that MPL's file-level
  copyleft requires distributed modifications to covered files to remain available. Apache-2.0 was
  selected instead to minimize obligations for applications embedding this small library.
- [OpenAI Agents SDK guardrails](https://openai.github.io/openai-agents-python/guardrails/) rerun
  tool guardrails after approval and immediately before execution.
- [Pydantic AI deferred tools](https://pydantic.dev/docs/ai/tools-toolsets/deferred-tools/) model
  paused tool calls while warning that human approval is not itself application authorization.
- [Pydantic AI toolsets](https://pydantic.dev/docs/ai/tools-toolsets/toolsets/) expose
  `WrapperToolset.call_tool` as the public execution-wrapping seam. A safe adapter can therefore
  exact-match the real per-step tool registry and defer natively, but it receives schema-validated
  arguments after custom validators and cannot cover other toolsets or provider-side tools.
- [MCP client security guidance](https://modelcontextprotocol.io/docs/develop/clients/client-best-practices)
  emphasizes per-call confirmation and keeping authorization decisions outside model control.
- [OpenAI Agents SDK tools](https://openai.github.io/openai-agents-python/tools/) and
  [LangChain middleware](https://docs.langchain.com/oss/python/langchain/middleware/custom) attach
  execution interception to registered tool objects rather than trusting model-supplied metadata.
- LangChain documents `wrap_tool_call` as the hook around each tool execution, its first configured
  middleware as outermost, and LangGraph interrupts as checkpointed pause/resume. A Samsarix
  adapter can therefore use only public runtime contracts, but it must run last to authorize final
  arguments and bind the resume response to the exact interrupted call.
- [OpenAI Agents SDK runner configuration](https://openai.github.io/openai-agents-python/running_agents/)
  documents concurrent function-tool calls by default, while its tool documentation says hosted
  and built-in tools do not use the function-tool guardrail pipeline. A portable gate therefore
  needs an explicit all-calls-before-dispatch boundary and cannot claim universal interception from
  one framework adapter.
- [Claude Code CLI permissions](https://docs.anthropic.com/en/docs/claude-code/cli-usage) expose
  allowed/disallowed tools and interactive permission modes, while
  [LangChain human-in-the-loop middleware](https://docs.langchain.com/oss/python/langchain/human-in-the-loop)
  supports ordered decisions for every simultaneously paused action. The
  [OpenAI Agents SDK approval flow](https://openai.github.io/openai-agents-python/human_in_the_loop/)
  likewise exposes multiple run-wide interruptions that can be resolved individually. These
  reinforce separating deterministic local authorization, exact-call approval evidence,
  framework-owned scheduling, and a complete ordered batch decision surface.
- The [MCP schema](https://modelcontextprotocol.io/specification/2025-11-25/schema) explicitly says
  tool annotations are hints and must not drive decisions when their server is untrusted.
- The [MCP tools specification](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)
  recommends keeping a human in the loop with the ability to deny tool invocations for sensitive
  operations, and the
  [official Python SDK](https://github.com/modelcontextprotocol/python-sdk) exposes a stable public
  low-level `Server.call_tool` handler. This supports exact-registry server enforcement without
  claiming coverage of direct handlers, other protocol primitives, or proxy/provider paths.
- The SDK's [WebSocket transport advisory](https://github.com/modelcontextprotocol/python-sdk/security/advisories/GHSA-vj7q-gjh5-988w)
  affects releases before 1.28.1. The integration therefore pins 1.28.1 and still documents that
  deprecated-WebSocket users must explicitly enable strict Host/Origin security settings.
- Samsarix Core and Samsarix Agent Framework both expose deterministic local registry-name
  snapshots, but only Core carries MCP behavioral hints and neither registry owns Agent Ethics
  capabilities. This supports a separate application-authored catalog that checks the complete
  local name set instead of coupling Agent Ethics to either runtime or inferring labels from hints.
- [OPA decision logs](https://www.openpolicyagent.org/docs/management-decision-logs) carry the
  evaluated bundle revision alongside each decision, while
  [OPA bundles](https://www.openpolicyagent.org/docs/management-bundles) define revision as bundle
  metadata. This supports recording evaluated policy-artifact provenance rather than relying only
  on a policy name; a local content digest can make that association independent of revision-label
  discipline.
- [Amazon Verified Permissions policy stores](https://docs.aws.amazon.com/verifiedpermissions/latest/userguide/policy-stores.html)
  centralize policy/schema validation, and
  [policy updates](https://docs.aws.amazon.com/verifiedpermissions/latest/userguide/policies-edit.html)
  expose update timestamps. Agent Ethics remains local, but needs equivalent evidence that two
  decisions actually used identical policy content.
- [OPA policy testing](https://www.openpolicyagent.org/docs/policy-testing) treats executable tests
  as the change-safety mechanism for evolving rules, while the
  [Verified Permissions test bench](https://docs.aws.amazon.com/verifiedpermissions/latest/userguide/authorization-testing.html)
  supports evaluating requests while policies change. The existing bounded suite can therefore
  serve as a privacy-minimized candidate-impact corpus without a second fixture format.
- OPA's same policy-testing contract reports policy coverage and supports a CI threshold, while
  [OpenFGA model testing](https://openfga.dev/docs/modeling/testing) recommends exercising every
  application relation. Rule-match coverage fits the existing JSON language without pretending it
  has source-line coverage.
- [OPA's style guidance](https://www.openpolicyagent.org/docs/style-guide) recommends strict checks
  and linting for policy mistakes, while
  [IAM Access Analyzer validation](https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-policy-validation.html)
  separates security warnings, warnings, and suggestions. A small certain-finding set is safer for
  this schema-free language than inferred business-intent diagnostics.
- [Cedar authorization](https://docs.cedarpolicy.com/auth/authorization.html) evaluates every
  supplied policy, lets a satisfied forbid override permits, and defaults to deny when no permit
  matches. [Verified Permissions policy stores](https://docs.aws.amazon.com/verifiedpermissions/latest/userguide/policy-stores.html)
  group validated policies per application or tenant, while
  [OPA bundles](https://www.openpolicyagent.org/docs/management-bundles) recommend central
  aggregation when policy comes from multiple sources. A bounded build-time composer can support
  separate guardrail/application ownership without adding a runtime control plane.
- Official `actions/upload-artifact` v6+ and `actions/download-artifact` v7+ releases use the
  Node 24 action runtime required by current GitHub-hosted runners.
- Official [`actions/attest-build-provenance` v4 release guidance](https://github.com/actions/attest-build-provenance/releases/tag/v4.1.1)
  identifies it as a compatibility wrapper and recommends direct `actions/attest` usage for new
  implementations.

Consequent decisions: validate before use; deny/review override allow; expose reasons and a decision
ID; omit raw input from audit records; preserve a first-class human-review outcome; do not claim
certification or ethics truth.

## Product and architecture decisions

- JSON policy version `1`, strict unknown-field rejection, immutable validated models.
- `deny > review > allow > default_effect` precedence; all rules evaluated.
- Errors are never grants. CLI code `0` is the only action-authorizing result.
- Small typed operator set; no regex, code, templates, imports, plugins, network, or environment
  substitution.
- Explicit `$ref` for cross-field comparison.
- Bounded file size, input size, nesting, strings, containers, rules, and conditions.
- Optional local audit stores decision metadata only and flushes successful appends.
- Python package plus CLI is the entire release shape; no frontend, API, authentication, database,
  AI provider, or cloud infrastructure.
- Runtime dependencies reduced from a broad unrelated stack to zero.

## Assumptions

- Policy files are trusted developer/operator configuration and are protected by the embedding
  system.
- Evaluation inputs may be untrusted.
- The caller provides authenticated, accurate facts and enforces the decision without a
  time-of-check/time-of-use gap.
- Samsarix LLC owns the current product identity and has supplied monitored contact addresses.
- Apache License 2.0 is the selected open-source posture; `NOTICE` preserves attribution and the
  separate trademark notice protects brand identity without restricting software use.
- The `samsarix-agent-ethics` PyPI name was unclaimed during the release review, but remains
  unreserved until publication succeeds.

## Findings

### P0 — baseline release blockers

- [x] Invalid TOML prevented install, tests, lint, type-check, and build.
- [x] Public package import referenced nonexistent `ComplianceAuditor` and swallowed import errors.
- [x] One validator imported missing private `helix-unified` modules and referenced nonexistent enum
  members.
- [x] The second validator's async wrapper referenced nonexistent decision attributes.
- [x] The package metadata discovered only the top-level package and conflicted with `setup.py`.
- [x] Tests exercised mocks rather than product code; no primary journey was tested.
- [x] Compliance manager generated passing controls without calling control evaluators, creating a
  false assurance path. The misleading compliance surface was removed.
- [x] README setup, CI, examples, license, links, Python support, and maturity claims were false.

### P1 — serious usefulness, reliability, or security issues

- [x] Original engine swallowed rule evaluation exceptions and allowed by default.
- [x] Unknown original condition keys passed by default.
- [x] Raw evaluation contexts, potentially including tokens or private data, were retained/logged.
- [x] Original JSON/policy loading was unbounded; regex rules could consume unbounded CPU.
- [x] Policy save paths derived directly from policy IDs.
- [x] Dependencies added substantial vulnerability and install surface unrelated to actual code.
- [x] No CLI contract, validation command, exit-code behavior, or runnable example existed.
- [x] No CI protected formatting, lint, typing, tests, coverage, or package shape.
- [x] [GitHub Actions run 30422122937](https://github.com/Deathcharge/samsarix-agent-ethics/actions/runs/30422122937)
  passed the complete Python 3.11-3.14 CI matrix.
- [x] Hosted runners confirmed tests and package checks on Python 3.12-3.14 in addition to the
  clean local Python 3.11 wheel verification.

### P2 — valuable post-candidate work

- [x] Publish standalone versioned JSON Schemas for policy authoring, test suites, normalized tool
  contexts, and audit-record consumers.
- [ ] Add property-based precedence/parser tests if another dependency is justified.
- [x] Add an optional caller-supplied audit sink interface for centralized logging while preserving
  JSONL compatibility and failing closed on configured sink errors.
- [x] Add optional exact-version-tested OpenTelemetry decision events and bounded ordered sink
  composition without making trace telemetry a durable audit claim.
- [x] Bind structured human-review evidence to the exact tool-call ID, normalized arguments,
  capabilities, and actor before allowing a resumed call.
- [x] Add immutable registration-time tool bindings so per-call payloads cannot downgrade trusted
  tool identity or capability labels.
- [x] Bind final callback references to verified catalogs so ordinary mutable registry replacement
  cannot change post-authorization dispatch selection.
- [x] Migrate artifact retention/provenance jobs off the deprecated Node 20 action runtime and add
  automated GitHub Actions update proposals.
- [x] Migrate new build-provenance generation from the compatibility wrapper to direct,
  exact-commit-pinned `actions/attest` v4 usage.
- [x] Add exact canonical policy fingerprints to decisions, test reports, gates, validation output,
  and audit records so an unchanged display version cannot hide changed evaluated policy content.
- [x] Compare baseline and candidate behavior over bounded regression suites, separating
  authorization changes, metadata-only changes, and fail-closed errors without reporting inputs.
- [x] Report declaration-ordered rule coverage, outcome counts, and input-free evaluation errors
  over bounded suites, with an explicit CI threshold.
- [x] Add stable, value-minimized authoring diagnostics for permissive defaults, unconditional
  allows, provably impossible/duplicate conditions, and missing explanations.
- [x] Add a keyed metadata-only audit chain for the validated single-writer local-file use case,
  with strict verification and external-head rollback detection; keep cross-process coordination
  and log services out of scope.
- [x] Add deterministic central policy-set composition with common-default and global-ID checks,
  value-minimized source provenance, and an ordinary deployable policy result.
- [x] Add atomic last-known-good in-process policy activation with compare-and-swap generations,
  coherent status, and live tool-gate integration.
- [x] Add one bounded deterministic deployment document for policy, optional contract, and
  mandatory lock, with atomic output and direct runtime activation.
- [x] Add a public optional OpenAI Agents SDK adapter with native review routing, final
  post-approval enforcement, bounded raw-argument parsing, an exact-version hashed dependency
  contract, and explicit unsupported execution paths.
- [x] Add exact-registry LangChain sync/async middleware with final raw-argument authorization,
  fingerprint-bound native LangGraph interrupt/resume, and an exact-version real-agent CI contract.
- [x] Add exact-registry Pydantic AI wrapper enforcement with native deferred review, strict
  Samsarix approval metadata, and an exact-version slim real-agent CI contract.
- [x] Add exact-registry enforcement at the stable MCP Python SDK low-level server handler with
  request-scoped facts, one-shot application review, and an exact-version in-memory client/server
  CI contract.
- [ ] Add policy-format version migration only after a second format and adopter need exist.
- [ ] Add benchmark thresholds once representative policy sizes are known.

## Implementation checklist

- [x] Protect and isolate the original clean worktree.
- [x] Inspect every original in-scope file, history, manifests, tests, docs, and configuration.
- [x] Record baseline commands and failures.
- [x] Define one standalone target user and primary journey.
- [x] Replace broken/duplicate code with a deliberate package API.
- [x] Implement strict policy validation and deterministic evaluation.
- [x] Implement CLI help, version, validation, check, init, stdout/stderr, and exit codes.
- [x] Add safe input limits, error behavior, and privacy-minimized audit output.
- [x] Add real library and command-level tests above the 90% coverage gate.
- [x] Add pinned development dependencies and build metadata.
- [x] Add CI for Python 3.11-3.14 and package build checks.
- [x] Replace stale documentation and add examples, security guidance, and changelog.
- [x] Complete final build, wheel install, command walkthrough, security scan, and adversarial review.
- [x] Prove the tool gate in a consumer-owned Agent Framework contract at an exact source commit.

## Release acceptance criteria

- [x] Product identity, target user, and out-of-scope claims are explicit.
- [x] Documented local installation succeeds in a fresh virtual environment.
- [x] Allowed, denied, review, invalid-input, and audit paths are tested.
- [x] Formatting, lint, strict typing, tests, and coverage pass locally.
- [x] Wheel and source distributions build and pass `twine check`.
- [x] Installed wheel imports and runs the CLI in a separate clean environment.
- [x] CI definition covers supported Python versions and release gates.
- [x] Configuration is local, bounded, versioned, and requires no secrets.
- [x] No locally actionable P0 remains.
- [x] Documentation describes implemented behavior rather than aspiration.
- [x] Owner resolves license/package identity before publication.

## Completed work

- Established the `samsarix_ethics` public API and `samsarix-ethics` console command.
- Added 563 real core tests; latest pinned local `python -m pytest` pytest-cov terminal report: 563
  passed and 95.01% total branch-aware coverage under the configured `--cov-branch` gate. Separate
  real-SDK contract tests run against exact hashed `openai-agents==0.18.3`, `langchain==1.3.14`,
  `pydantic-ai-slim==2.22.0`, `mcp==1.28.1`, and OpenTelemetry 1.44.0 dependency graphs.
- Rebuilt the wheel and source distribution, passed `twine check`, and verified the wheel in an
  isolated no-dependency environment: install/import/version/schema/deployment verification and a
  deployed allow decision all succeeded, and runtime construction used the packaged API.
- Completed a schema-sealed security review of the 34-file product core with complete coverage, no
  deferred surfaces, and no reportable findings. The subsequent 41-file Samsarix/legal/public-repo
  delta added no runtime capability and passed the full local release suite and clean-wheel checks.
- Replaced unverified conduct contact, SLA, and committee claims with an honest project-scoped
  reporting and enforcement policy.
- Rebranded the unreleased package to Samsarix, recorded Samsarix LLC ownership and working contact
  addresses, and replaced conflicting legacy licenses with Apache-2.0, NOTICE attribution, and
  trademark guidance.
- Added strict typing, Ruff formatting/linting, pinned tools, examples, CI, and package metadata.
- Removed non-functional duplicate validators, fake compliance checks, generic policy package,
  unrelated dependencies, mock-only test suite, and stale portal HTML.
- Added accurate README, quick start, API, policy, architecture, security, changelog, contribution,
  and productization documentation.
- Added monitored support/conduct/security paths, GitHub issue forms, code ownership, and a
  security-aware pull request template; confirmed GitHub private vulnerability reporting is enabled.
- Added versioned schemas, bounded batch evaluation, policy regression suites, a fail-closed sync
  and async `ToolGate`, a fourteen-case capability policy pack, and the `subset_of` operator.
- Added immutable versioned audit records plus one synchronous caller-owned sink seam; sink delivery
  runs before authorization, fails closed, does not retry, and preserves the JSONL path API.
- Added bounded versioned tool-call fingerprints and immutable structured approvals; a mutation to
  the call ID, tool, arguments, capabilities, or actor now fails before policy, audit, or execution.
- Added frozen bound-tool gates that reuse trusted registration metadata for fingerprinting,
  evaluation, sync execution, and async execution without per-call capability parameters.
- Added a canonical streamed exact-policy fingerprint with a pinned test vector and propagated it
  through decisions, regression reports, gates, CLI validation, and metadata-only audit record v1.
- Added a versioned baseline-versus-candidate impact report/API/CLI/schema and runnable candidate
  that detects a sensitive-read change from allow to review while omitting every case input.
- Added a versioned rule-coverage report/API/CLI/schema with exact threshold semantics; the
  included twelve-rule tool policy demonstrates 100% rule coverage across all three outcomes.
- Added a versioned policy-lint report/API/CLI/schema with five stable finding codes and explicit
  severity gates; every bundled policy passes the strict suggestion-level CI gate.
- Added bounded layered policy composition with atomic CLI output and exact source provenance. The
  existing twelve-rule support-agent policy is reproducibly assembled from eight organization
  guardrails and four application rules, then validated by its fourteen-case 100%-coverage suite.
- Added baseline-authoritative shadow evaluation with a strict versioned telemetry schema. A live
  candidate observes the same detached action after the baseline succeeds, candidate domain errors
  remain non-authoritative, and per-policy monotonic durations expose `PolicyEngine.evaluate` time
  while excluding input loading/validation, telemetry delivery, and end-to-end action latency.
  Serialized reports omit input plus reason/warning text.
- Added an atomic `PolicyRuntime` that fully validates candidate policy/contract/lock sets before
  swapping them into live gates, retains the last good generation after failure, rejects stale
  concurrent activation, and pins batches to one generation. Distribution and durable desired
  state remain external control-plane responsibilities.
- Added a strict `PolicyDeployment` format/API/CLI/schema and checked-in baseline artifact. One
  bounded read and mandatory embedded lock prevent mixed policy/contract/lock snapshots; atomic
  exclusive output prevents partial and implicit replacement. External systems still own origin
  authentication, immutable transport, signing, replication, and promotion approval.
- Added immutable gate-specific prepared calls and bounded `ToolGate` batch evaluation/enforcement.
  Every call is collected before evaluation, runtime batches pin one generation, contract errors
  precede audit delivery, and the base gate leaves dispatch framework-owned. A fifteen-rule
  coding-agent pack,
  matching context contract, 100%-covered suite, verified deployment, and runnable review/approval
  demo cover workspace, process, network, destructive, and sensitive capabilities.
- Added complete metadata-only batch diagnostics to the existing typed tool-call block exceptions.
  Integrations receive every ordered decision and the first blocked index from the original
  evaluation, preserving existing catch behavior while avoiding a second evaluation, new decision
  IDs, or duplicate audit records when populating multi-call review queues.
- Added strict standalone tool-catalog v1 artifacts with canonical exact-content fingerprints,
  bounded duplicate-safe loading, bundled schema/CLI validation, and exact full-registry name
  comparison before immutable gate bindings exist. The coding-agent example now proves a seven-tool
  catalog across workspace, process, network, external-write, destructive, and sensitive labels
  without trusting MCP annotations or adding sibling-repository dependencies.
- Added a separate coherent tool-gate deployment v1 artifact rather than changing policy
  deployment v1. It packages the already locked policy deployment, canonical catalog, and exact
  catalog fingerprint in one bounded atomically written unit. `ToolGate.bind_deployment` verifies
  the complete runtime registry before returning any binding; the artifact deliberately remains
  internal equality evidence rather than a signature or control plane.
- Added a zero-dependency `ToolDispatcher` that exact-matches complete callable mappings, snapshots
  final callback references, keeps authorization and dispatch on one object, supports sync/async
  calls, and preflights full batches before sequential execution. It deliberately does not claim
  code identity, immutable callback internals, or transactional side effects.
- Added an optional OpenAI Agents SDK adapter that protects copied strict top-level function tools,
  preserves existing controls, routes policy review into native interruptions, and re-enforces with
  fresh application facts immediately before execution. A public no-network example, focused
  guide, adversarial core suite, and exact real-SDK CI lane cover the integration without changing
  the base package dependency boundary.
- Added optional LangChain middleware that exact-matches a complete `BaseTool` registry, authorizes
  final raw arguments after outer middleware, and binds native LangGraph resume to the interrupted
  call. A real checkpointed-agent contract, no-network example, focused guide, and adversarial
  sync/async suite preserve the dependency-free base package boundary.
- Added an optional Pydantic AI wrapper toolset that exact-matches every real run-step registry,
  authorizes validated detached arguments, and converts native deferred review into
  fingerprint-bound, atomically consumed Samsarix resume evidence. A real no-network agent
  contract proves approval, replay blocking, rejection, deny, serialized-history resume, forged
  native-approval blocking, and registry-drift failure against exact
  `pydantic-ai-slim==2.22.0` without changing the dependency-free base install.
- Added an optional stable MCP Python SDK server adapter that snapshots real `Tool` definitions,
  exact-matches their name set, obtains fresh request-scoped facts, and protects the final
  low-level async handler.
  One-shot review evidence, adversarial tests, an in-memory client/server contract, no-network
  example, focused guide, and exact hashed lock preserve the dependency-free base package.
- Added a versioned metadata-only OpenTelemetry event sink, bounded ordered audit-sink composition,
  exact API/SDK contract test, and an in-memory no-network example. The application retains SDK,
  exporter, sampling, collector, trace access, durable audit, and partial-delivery recovery.
- Added a bounded HMAC-SHA-256 `AuditSink`, strict verifier/CLI, external-head rollback check,
  versioned entry/report schemas, adversarial mutation/reordering/truncation tests, and a runnable
  gate example. The design stays metadata-only and explicitly leaves key custody, external
  checkpoints, cross-process exclusion, recovery, and callback outcomes to the application.
- Added whole-tool-gate-deployment fingerprints and a bounded HMAC-SHA-256 envelope with key ID,
  audience, monotonic sequence, issuance/expiry, rotation keyring, atomic I/O, CLI/schema support,
  and immediate gate/dispatcher verification. Symmetric authorship, trusted time/sequence storage,
  asymmetric identity, and distributed rollout remain explicitly external.
- Added retained exact-commit wheel/source CI artifacts, main-branch build-provenance attestations,
  and an operator checklist that keeps artifact verification separate from registry publication.
- Merged a consumer-owned Agent Framework contract at consumer commit
  `02fe13ae102359958b8a02d125a41abaa814d472`, pinned to Agent Ethics
  `eb69207b14ddd79bdfe774ec5b166c8ca8ce940e`; the private consumer's 106-test suite and installed
  wheel checks passed on its supported integration matrix.

## Deferred and blocked work

Owner controlled:

- Authorize and perform PyPI publication, signing/provenance, and GitHub release creation.

External validation gates:

- Gather feedback from at least one real embedding application before declaring a stable `1.0` API.

## Known risks

- A policy explanation is value-minimized single-input diagnostics, not proof of policy correctness;
  repeated access reveals authorization behavior and belongs behind operator authentication.

- Policy correctness is only as good as operator rules and caller-supplied facts.
- A policy fingerprint proves exact canonical content equality, not authorship, review, freshness,
  secure distribution, or rollback protection.
- An identical comparison report proves only the supplied cases and observable fields; it is not
  exhaustive semantic equivalence or evidence for inputs the suite did not cover.
- Rule coverage proves that at least one successful supplied case matched a rule, not that every
  condition boundary, precedence interaction, type, or possible input was tested.
- A clean lint report covers a deliberately small set of certain authoring patterns, not application
  intent, least privilege, domain-schema correctness, or exhaustive reachability.
- Composition proves deterministic aggregation of trusted source artifacts, not source authorship,
  safe distribution, freshness, tenant isolation, or correctness of the combined business policy.
- Shadow evaluation proves only the two policies' behavior for one supplied action. It adds
  synchronous work and provides no sampling or durable telemetry. In-process promotion/rollback
  still requires external authorization and does not coordinate processes or hosts.
- Runtime generation numbers are process-local and reset at restart; they are not global freshness
  or rollback-prevention evidence.
- A policy deployment contains full trusted policy content and proves only internal consistency;
  its storage and transport need stronger controls than metadata-minimized reports.
- An authenticated deployment envelope remains readable and replayable until expiry while its
  sequence meets the target's durable minimum. HMAC verifiers can forge; the package does not
  persist sequence state, establish individual identity, or replace Sigstore/TUF release policy.
- Plain JSONL remains unauthenticated. The optional keyed chain authenticates mutation and order in
  one single-writer stream, but shared-key compromise permits rewriting, a valid-prefix rollback
  needs an external head, and cross-process ordering/locking remains caller-owned.
- A decision can become stale before enforcement; callers must avoid TOCTOU gaps.
- Prepared batches authorize no transaction: audit delivery may be partial on sink failure, and
  framework scheduling or callback failure may still produce partial side effects.
- Composite audit delivery is ordered but not transactional, and OpenTelemetry event acceptance
  does not prove sampling, export, collector receipt, storage, or retention.
- Catalog exact matching and dispatcher snapshots prove only that trusted names agree and selected
  callback object references remain stable. They do not authenticate the registry, catalog,
  deployment, or callback code; freeze closure/global/object state or delegated registry lookups;
  validate label correctness; or establish freshness.
- Approval binding does not authenticate reviewers or prevent replay; embedding applications own
  protected pending-call storage, expiry, and atomic one-time consumption.
- LangChain review checkpoints contain proposed tool arguments and require application-owned
  encryption, access control, retention, reviewer/thread authorization, CSRF protection, expiry,
  and one-time resume. Direct tool invocation, server-side tools, and pre-handler side effects can
  bypass or precede middleware, while parallel calls remain non-transactional.
- Pydantic AI schema and custom argument validation occur before the wrapper; validators must be
  side-effect-free and policy sees validated values. Deferred state contains proposed arguments,
  reviewer authentication/expiry remains application-owned, and durable reconstruction needs an
  application-owned first-write/consume store. Other execution paths can bypass the wrapped
  toolset, and parallel calls are not transactional.
- MCP SDK schema validation occurs before the adapter and produces no Samsarix audit decision.
  Review payloads contain proposed arguments; reviewer authentication, confidentiality, expiry,
  timeout/cancellation, and concurrency are application-owned. Direct handlers, FastMCP internal
  routes, non-tool primitives, and gateway/proxy/provider paths can bypass this adapter.
- File permissions and retention vary by operating system and are caller responsibilities.
- Python dependency tooling resolves transitive development dependencies; exact direct pins reduce
  drift but do not constitute a fully hashed supply-chain lock.
- Package-index ownership, release provenance/signing, and historical ownership authority remain
  owner checks before publication; the current tree consistently uses Apache-2.0 with NOTICE and
  separate trademark guidance.

## Distribution and sustainability

The simplest distribution is a source distribution and universal Python wheel. No hosted service
is required, so operating cost is effectively zero beyond repository maintenance and release
infrastructure. Plausible sustainability is paid integration support, policy design/review, and
support contracts around the Apache-2.0 core. The Samsarix marks remain separately protected. No
subscription or usage-priced service is justified by repository evidence.
