# Productization record

Last updated: 2026-08-01

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
- [MCP client security guidance](https://modelcontextprotocol.io/docs/develop/clients/client-best-practices)
  emphasizes per-call confirmation and keeping authorization decisions outside model control.
- [OpenAI Agents SDK tools](https://openai.github.io/openai-agents-python/tools/) and
  [LangChain middleware](https://docs.langchain.com/oss/python/langchain/middleware/custom) attach
  execution interception to registered tool objects rather than trusting model-supplied metadata.
- The [MCP schema](https://modelcontextprotocol.io/specification/2025-11-25/schema) explicitly says
  tool annotations are hints and must not drive decisions when their server is untrusted.

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
- [x] Bind structured human-review evidence to the exact tool-call ID, normalized arguments,
  capabilities, and actor before allowing a resumed call.
- [x] Add immutable registration-time tool bindings so per-call payloads cannot downgrade trusted
  tool identity or capability labels.
- [ ] Add cross-process ordering or tamper-evident audit chaining only for a validated use case.
- [ ] Add policy-set composition/version migration after real adopter feedback.
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
- Added 191 real tests; latest local run: 191 passed, 95.46% total coverage with branch measurement.
- Rebuilt the final wheel and source distribution, passed `twine check`, and verified the wheel in
  an isolated environment: install/import/version/validate/allow exited `0`, deny exited `3`,
  review exited `4`, and the audit record excluded raw input.
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

- Policy correctness is only as good as operator rules and caller-supplied facts.
- The local JSONL audit is not tamper-evident and has no cross-process ordering guarantee.
- A decision can become stale before enforcement; callers must avoid TOCTOU gaps.
- Approval binding does not authenticate reviewers or prevent replay; embedding applications own
  protected pending-call storage, expiry, and atomic one-time consumption.
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
