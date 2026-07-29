# Productization record

Last updated: 2026-07-28

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

**Helix Agent Ethics is a zero-runtime-dependency Python library and CLI that acts as a local,
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

This product exists independently of `helix-unified`: it is offline, embeddable, has a deliberate
public API, requires no private service, and can guard any Python agent system.

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
- The checked-in BSL file reflects some owner intent, but its product name and the second license
  file require owner/legal clarification.
- No package name, version, or public distribution is assumed reserved until the owner verifies it.

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
- [ ] Run the added CI matrix on GitHub; local execution cannot substitute for hosted runners.
- [ ] Confirm wheel behavior on Python 3.12-3.14; local verification currently uses Python 3.11.9.

### P2 — valuable post-candidate work

- [ ] Publish a standalone JSON Schema and editor integration for policy authoring.
- [ ] Add property-based precedence/parser tests if another dependency is justified.
- [ ] Add an optional caller-supplied audit sink interface for centralized logging.
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
- [ ] Owner resolves license/package identity before publication.

## Completed work

- Established the `helix_ethics` public API and `helix-ethics` console command.
- Added 67 real tests; latest local run: 67 passed, 93.39% branch coverage.
- Rebuilt the final wheel and source distribution, passed `twine check`, and verified the wheel in
  an isolated environment: install/import/version/validate/allow exited `0`, deny exited `3`,
  review exited `4`, and the audit record excluded raw input.
- Completed a schema-sealed security review of all 34 in-scope files with complete coverage, no
  deferred surfaces, and no reportable findings.
- Replaced unverified conduct contact, SLA, and committee claims with an honest project-scoped
  reporting and enforcement policy.
- Added strict typing, Ruff formatting/linting, pinned tools, examples, CI, and package metadata.
- Removed non-functional duplicate validators, fake compliance checks, generic policy package,
  unrelated dependencies, mock-only test suite, and stale portal HTML.
- Added accurate README, quick start, API, policy, architecture, security, changelog, contribution,
  and productization documentation.

## Deferred and blocked work

Owner/legal controlled:

- Confirm whether BSL 1.1 applies to this repository; correct the `Licensed Work`, licensor contact,
  change date, and relationship to `LICENSE.PROPRIETARY` through legal review.
- Confirm distribution name (`helix-agent-ethics`) and first public version (`0.1.0`).
- Enable GitHub private vulnerability reporting and nominate a monitored security contact.
- Authorize and perform PyPI publication, signing/provenance, and GitHub release creation.

External validation gates:

- Observe the first GitHub Actions matrix on Python 3.11-3.14.
- Gather feedback from at least one real embedding application before declaring a stable `1.0` API.

## Known risks

- Policy correctness is only as good as operator rules and caller-supplied facts.
- The local JSONL audit is not tamper-evident and has no cross-process ordering guarantee.
- A decision can become stale before enforcement; callers must avoid TOCTOU gaps.
- File permissions and retention vary by operating system and are caller responsibilities.
- Python dependency tooling resolves transitive development dependencies; exact direct pins reduce
  drift but do not constitute a fully hashed supply-chain lock.
- License ambiguity blocks an honest public release disposition.

## Distribution and sustainability

The simplest distribution is a source distribution and universal Python wheel. No hosted service
is required, so operating cost is effectively zero beyond repository maintenance and release
infrastructure. Plausible sustainability is paid integration support, policy design/review, and
commercial licensing under whatever owner-approved license replaces or clarifies the current
files. No subscription or usage-priced service is justified by repository evidence.
