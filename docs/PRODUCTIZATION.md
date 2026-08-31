# Productization record

Last updated: 2026-08-31

## Current increment: source-archive test completeness

Post-merge PR #49 verification passed all 14 main CI jobs (`33408878186`) at
`7f5f5b8cbee0f77cbfcda9d25a98a88e59eed6b8`, both exact-commit/ref/workflow attestations, Twine,
a fresh dependency-free wheel CLI smoke, and all six installed-wheel SDK lanes (153 contracts
and six demos). All 56 runtime package files matched the preceding attested wheel byte-for-byte.
The subsequent extracted-source check exposed an omission: setuptools included `test_*.py`
but not `tests/conftest.py`. Reproducing with the attested archive's CLI tests and `-x` produced
two passes and `fixture 'write_json' not found` (exit 1). This archive-test failure is not green
and is not hidden by the successful installed-wheel checks.

The affected user is an adopter or release operator checking shipped source without a checkout.
The manifest now explicitly includes core Python tests and helpers. The Python 3.11 build lane
compares every checkout core-test file byte-for-byte with its archived regular file, safely extracts
the sdist into a temporary directory, installs the built wheel, and runs the full archived core
suite with the unchanged coverage gate. Import-root and environment checks prevent an editable
checkout from masking the installed artifact. This is a focused packaging follow-up, not a runtime,
dependency, API, license or security-boundary change. Branch: `codex/sdist-test-completeness`.

The rebuilt archive passes the exact CI block locally: **808 passed, one POSIX-only skip,
95.56% coverage in 141.44s**, using installed site-packages (5,260 statements). All 38 archived Python
test/helper files match the checkout; the old attested archive fails this check on the missing
fixture. Build/Twine, Ruff check/format (103 files), mypy (41 source files) and dependency checks pass.
All 56 runtime package files match the attested baseline wheel byte-for-byte. Final-head/main CI
and exact-main artifact evidence will be recorded on
[PR #50](https://github.com/Deathcharge/samsarix-agent-ethics/pull/50). No registry publication,
paid API, live service, customer contact, sibling changes or independent security scan. P1 gates
remain a selected production identity/storage/operating environment, real adopter pilot, protected
publication approval and legal review; P2 includes deployment load/SLOs and selected browser/SSE
flows. Disposition remains release candidate with those external gates, not a completed product goal.

## Previous increment: clean-room release and adoption verification

Baseline: clean synchronized `main` at `d78fdcc3c12fd700cd0e1baf0feda34a85587e23`, green main CI
`33406051342`. Previous turn was progress: PR #48 merged 16 refresh/fixture cases, addressed review
comments, verified exact-main artifact provenance and passed 139 installed-wheel MCP contracts.
Its [final record](https://github.com/Deathcharge/samsarix-agent-ethics/pull/48#issuecomment-5480277840)
contains the evidence. Work branch: `codex/clean-room-release-verification`.

The product remains an independent deterministic policy-gating library/CLI. This increment serves
new adopters and release operators evaluating its actual installed package without inherited
development state. A current-state audit found five missing project-install steps in the release
guide: core, OpenAI Agents, LangChain, Pydantic AI and OpenTelemetry. Hash-locked test/SDK dependencies
do not install Samsarix. An actual fresh core environment reproduced `ModuleNotFoundError` during
public API test collection (exit 2); explicit regular installation fixes that import boundary.
The guide also verified artifact repository identity without pinning the intended commit/ref/signer,
and downloaded into the same `dist/` directory used for local builds.

Bounded primary research checked
[pip regular versus editable installs](https://pip.pypa.io/en/stable/topics/local-project-installs/)
and [GitHub CLI attestation constraints](https://cli.github.com/manual/gh_attestation_verify).
The concrete decision is to repair and exercise the actual release path before adding more API
surface. Every documented lane now installs the package and checks dependencies in a separate new
environment; CI's eight installation steps use regular installs. Candidate verification requires
a successful main-push run, exact commit/ref/workflow constraints, separate download paths, and
repeating each SDK contract/demo with the exact verified wheel. The guide distinguishes checkout
resources from an sdist, Bash from PowerShell continuation, source builds from downloaded artifacts,
and cryptographic provenance from runtime safety or release approval.

Ten static guide regressions cover lane completeness, dependency/install/check ordering, isolated
lock combinations, both artifact identities and download separation. They initially produced nine
failures, including the two formerly editable MCP lanes under the new regular-install requirement;
after repair all ten pass. These are intentionally not represented as execution of the prose.
Separate clean environments execute the real dependency installs, package imports, SDK contracts
and examples. No runtime API, schema, dependency, licensing or sibling-repository change is intended.
Verification results and final commit/CI/artifact evidence will be recorded as they complete.

The first regular-install core run exposed a second verification defect: all **807 tests passed**
(one POSIX-only skip), but coverage failed at **71.79%** because the CLI test helper unconditionally
prepended checkout `src` to `PYTHONPATH`. Parent tests exercised site-packages while child tests
exercised a different copy, doubling the measured module set. The helper now pins the parent's
actual imported package root, matching the existing restart/process helpers. A regression models a
distinct installed path and ensures no checkout or unrelated import root is injected. The 90%
coverage threshold remains unchanged; the failed run is retained as evidence, not called green.

After the helper fix, the actual regular-install Windows run passes **808 tests, one POSIX-only
skip, 95.56% coverage in 199.37s**, with only the installed package measured (5,260 statements rather
than the two-copy 10,520). Process recovery passes **38 tests in 35.39s** and its demo. Build/Twine,
Ruff check/format (103 files), mypy (41 source files) and ten guide checks pass. CI `33407950805`
is green at `8df424d`; the superseded first run was cancelled by normal workflow concurrency.
Every CI installer now also runs `pip check`. Clean SDK and exact-final-main evidence remain
in progress and will be recorded on [PR #49](https://github.com/Deathcharge/samsarix-agent-ethics/pull/49).

P1 acceptance still requires a selected production identity/storage/operational environment, real
adopter pilot, protected registry publication setup/approval and legal review. P2 includes selected
browser/long-lived SSE workflows and deployment load/SLOs. No live deployment, paid API, registry
publication or external customer contact. Disposition remains release candidate with named external
gates; this repair does not establish demand or complete the broader product objective.

## Previous increment: post-grant MCP credential refresh acceptance

Baseline revalidated: clean synchronized `main` at `e6e19f84bf4df544fe440d712166a7ebaa927dbc`,
successful main CI `33402887441`. Previous turn was progress: PR #47 merged the exact-built-in
optimization, verified exact-main wheel/sdist attestations and package checks, and documented the
partial security-report bookkeeping limitation. Its
[final record](https://github.com/Deathcharge/samsarix-agent-ethics/pull/47#issuecomment-5479876927)
contains the post-merge evidence. Work branch: `codex/mcp-refresh-contracts`.

The product remains an independent deterministic library/CLI for agent developers, not a hosted
authorization service. The acceptance gap is a long-lived support agent's existing OAuth grant:
can a read or human-reviewed send safely proceed across access-token expiry, and what happens
when refresh or token persistence fails? Prior TLS contracts only covered client-credentials
reacquisition. This increment adds post-grant refresh evidence without enlarging the runtime API.

Bounded primary research checked the
[pinned SDK OAuth provider contract](https://py.sdk.modelcontextprotocol.io/client/oauth-clients/),
[RFC 6749 refresh semantics](https://www.rfc-editor.org/rfc/rfc6749.html#section-6) and
[RFC 9700 rotation/replay guidance](https://www.rfc-editor.org/rfc/rfc9700.html#section-4.14).
Tests deliberately seed a prior confidential-client grant and cached trusted issuer metadata;
test-only SDK expiry updates avoid wall-clock sleeps. They do not simulate browser consent or
claim dynamic discovery, production issuer acceptance or durable credential recovery.

Implemented: stock MCP 2.1.1 provider refresh over verified TLS, Basic/form-post auth, two successive
rotations or omitted replacement fields, preserved scopes, same-provider concurrency, policy denial
and exact human-reviewed dispatch. Failure cases cover revoked/wrong-tenant grants, unavailable or
malformed token responses, storage failure during review, oversized response, timeout and cancellation.
Assertions observe actual protected handlers, token requests, store writes and credential exclusion
from resource bodies/audit records. A reload case preserves evidence that `expires_in` alone does
not restore an absolute expiry clock. CI and contributor/release commands include the new module.

Important boundary: a store failure after rotation leaves issuer/provider/store state divergent;
discarding the provider/client is necessary but does not recover the lost replacement. Likewise,
an interruption after issuer commit is different from the tested interruption before issuance.
No cross-process lock, refresh-token family replay detector, credential database or automatic retry
is introduced. SDK third-party log redaction remains the application's responsibility.

Acceptance: focused and full MCP client contracts, unchanged core quality checks, installed-wheel
contracts, review of real handler/request assertions, green exact commits and distribution provenance.
Initial verification: **45 OAuth/refresh tests pass in 34.22s**, including 14 new refresh cases;
the **137-test complete MCP client contract passes in 58.52s**. Ruff check/format (102 files),
mypy (41 source files), build and Twine pass. Full core, installed-wheel and exact final-commit
CI/provenance checks are post-commit gates; their final results will be recorded on the PR.

Follow-up evidence: full Windows core **797 passed, one POSIX-only skip, 95.56% coverage in
181.67s**; the installed local wheel passed **137 MCP contracts in 61.82s** and the support demo.
All 56 runtime package files are byte-identical to the attested baseline wheel. PR #48 CI
`33404899886` is green at `c3bb5f1`: 798 core tests on Python 3.11-3.14 and 137 MCP contracts on
Linux/Windows. CodeRabbit review `5067914133` returned two nonblocking test-hardening comments;
follow-ups reject missing/mismatched injected token stores before HTTP and guard secret-exclusion
assertions against empty capture. Two new fixture guard cases bring the refresh module to 16 cases.
The bot's test-function docstring-coverage warning is informational; descriptive tests and fixture
boundary docstrings are retained, without changing configured quality gates. Final-head/main
verification is recorded on [PR #48](https://github.com/Deathcharge/samsarix-agent-ethics/pull/48).

P1 gates remain deployment issuer/credential storage/rollback/supervisor and aggregate resource
acceptance, external pilot, protected package-publication approval and legal review. P2 remains
selected browser/long-lived SSE flows and controlled deployment load/SLO selection. No paid service,
production deployment, registry publication or sibling-repository change. Release candidate with
named external gates; the broader product goal is unchanged.

## Previous increment: profile-led policy evaluation optimization

Baseline revalidated: clean synchronized `main` at `a4f07077d96b82c29ba52c7ca806268694a185be`,
successful main CI `33399806731`. Previous turn was progress: PR #46 added performance tooling,
merged with all 14 main jobs green, and verified exact-main wheel/sdist attestations, installed-wheel
and extracted-sdist workloads. Final Windows suite: 744 passed, one POSIX-only skip, 95.47% coverage.
The [final PR #46 record](https://github.com/Deathcharge/samsarix-agent-ethics/pull/46#issuecomment-5479494413)
contains the post-merge evidence. Work branch: `codex/policy-hot-path-parity`.

The independently useful product remains a deterministic local library/CLI for agent developers.
This increment lowers avoidable evaluation overhead while retaining authorization semantics, so
operators can spend less of a coding/support agent's latency budget on policy checks. It does not
substitute a benchmark score for actual adopter validation or change the broader goal.

Current profiling of 30 baseline 1,000-rule evaluations attributed 1.053s of 1.949s instrumented
execution to JSON equality and 0.402s to field lookup. Both paths also appear in coding dispatch.
These profiler timings include instrumentation and are not ordinary request latency. Bounded
primary research checked [Python's profiler guidance](https://docs.python.org/3/library/profile.html),
[type/subclass behavior](https://docs.python.org/3/library/functions.html#isinstance) and
[OPA's profiling guidance](https://www.openpolicyagent.org/docs/policy-performance).

Implemented exact-built-in fast paths for string equality and dictionary path traversal; generic
subclass, Mapping, structured JSON and bool/number semantics remain in the existing fallback.
There is no input cache, changed policy language, skipped validation/rules, public API or dependency
change. Frozen pre-change reference helpers, independent golden assertions and bounded generated
JSON pairs test equivalence. Public decision/explanation/batch checks preserve precedence, warnings,
ordering and errors; mutation/reference checks protect fresh reads. Focused engine/parity/explanation
checks pass 103 tests. Ruff and mypy (41 source files), build, Twine and no-optional-SDK wheel install
pass. The full Windows suite passes **797 tests, one POSIX-only skip, 95.56% coverage in 283.06s**.
The installed candidate wheel passes **331 engine/parity/explanation/benchmark, process-recovery
and MCP client contracts, with one POSIX-only skip, in 80.86s**. The SDK test environment was then
restored to an editable install. [PR #47](https://github.com/Deathcharge/samsarix-agent-ethics/pull/47)
CI `33401698358` is green at `e9ded056bbe80459f5d7b6314a4483cc00284aae`: 798 tests on each Python
3.11-3.14 job, plus Linux/Windows recovery and SDK contracts. CodeRabbit's automatic review was
skipped; that status is not review approval. Codex Security scan
`803d2cc7-74bb-4a8c-be07-b7621f1b4648` sealed the fixed `a4f0707..b00df32` runtime/test diff with
zero findings and no discovery candidates. Both changed files have no-issue review dispositions;
supporting gate/dispatch/runtime/shadow/MCP paths were inspected. The sealed report is nevertheless
**partial**: it retained the earlier administrative `compact-review-close` checkpoint as deferred,
despite final inventory/candidate recording. Do not represent it as a complete clean scan or a
whole-repository audit. The immutable report is preserved; this bookkeeping limitation is carried
into release evidence. Preflight passed without configuration changes; TAC access/grants could not
be verified because the connector was disconnected. Final-head CI and exact-main verification
remain post-commit checks to be recorded on the PR.

Three alternating installed-wheel pairs (A/B, B/A, A/B) retain all six raw reports under
`benchmarks/results/2026-08-31-hot-path/`. Each pair is compatible and passes a 20% median-regression
inspection budget. Coding read medians were lower in all three pairs; filesystem audit was slower
in one. Desktop variation is substantial, including changes in the unchanged load/bind path.
[Performance methodology and all workload results](PERFORMANCE.md#exact-built-in-optimization-observation-2026-08-31)
document those limitations rather than claiming controlled hardware, production SLOs or superiority.

Acceptance: source and installed-package semantic checks; unchanged harness/fixture/settings for
comparison; complete raw evidence including regressions; no cache or weakened authorization;
reviewed and green exact commits; verified final distribution provenance.
P1 gates remain deployment identity/storage/rollback/supervisor and aggregate resource acceptance,
external pilot, protected publication approval and legal review. P2 is controlled load/SLO selection
and selected long-lived/browser/refresh OAuth flows. No paid service, production deployment, package
publication or sibling repository change. Disposition remains release candidate with external gates.

## Previous increment: reproducible performance evidence

Baseline revalidated: clean, synchronized `main` at `c9c1e38286098c9f5b4ab304011e728ca2d38d49`,
with successful main CI `33395558329`. Previous turn was progress: real-process recovery was merged
and exact-main wheel/sdist provenance plus 175 installed-wheel checks were verified. Work branch:
`codex/policy-performance-evidence`. The full long-running product objective remains unchanged.

An adopter could reproduce correctness but could not measure or compare policy-gating overhead
through repository-owned tooling. This increment serves developers/operators deciding whether the
independent library fits a coding/support agent's latency and resource budget. It adds evidence,
not a hosted service, benchmark leaderboard, performance SLA or new runtime API.

Bounded primary research checked [OPA performance guidance](https://www.openpolicyagent.org/docs/policy-performance)
and [Python timing behavior](https://docs.python.org/3/library/timeit.html). The concrete choice is to
separate synthetic policy scans, complete gate/dispatch boundaries, preparation-inclusive batches,
shadow work, in-memory load/bind and real filesystem audit writes. Raw individual timings and repeat
means are retained; noisy hosted-runner performance is not a CI speed gate.

Implemented: 14 default workloads (10/100/1,000-rule last/no-match plus eight coding workloads), exact
outcome/callback checks on every invocation, actual audit-record verification, cooperative time and
work/report-size budgets, exclusive UTF-8 report output, environment/harness/fixture/package content
fingerprints, and strict compatible-run median comparison. Wrong decisions, forbidden callbacks,
lost audit records, invalid/incompatible evidence and exhausted budgets cannot produce success.
No arguments, actor, policy contents, callback values, local paths or hostname are emitted. Environment
labels and content fingerprints are operational metadata; reports are unsigned and need trusted storage.

Focused verification: **67 benchmark tests pass, one POSIX-only FIFO test is skipped on Windows**;
an isolated coverage run measured all 251 harness statements and 40 branches covered. This is test
coverage, not exhaustive correctness/security proof. The `f1107c7` full Windows run passed **742 tests,
one POSIX-only skip, 95.47% core coverage in 200.42s**, before two final stdout/output-race tests.
Final local report parsing rejects exponent-overflow numbers and non-file inputs before reading.
The source baseline including the initial
59 benchmark tests passed **736 tests in 262.08s, 95.47% core coverage**; four additional callback/audit/
deadline adversarial tests then passed in the focused run. Ruff check/format (100 files), mypy
(41 source files), build and Twine pass. The installed wheel, with no optional SDKs, completed the
default 14 workloads and a zero-budget self-comparison; raw samples are retained at
`benchmarks/results/2026-08-31-windows-python311.json`. This observation is not an isolated-hardware
SLO. [PR #46](https://github.com/Deathcharge/samsarix-agent-ethics/pull/46) has all 13 test jobs green at
`b0f4db22317fb6cb9edd30efb703fed604b81613`; both downloaded Linux/Windows artifacts contain 14 valid
workloads and pass self-comparison. The extracted sdist also ran against the no-optional-SDK installed
wheel. CodeRabbit review `5067256954` on `b0f4db2` returned three minor/trivial comments. Follow-ups
strengthen Windows JSON-escaped path privacy checks and pin/test subprocess cwd. Reports are retained
after a later CI failure; correctness failures and the explicit completion/resource cap remain
blocking, rather than enabling blanket continue-on-error. This distinction is now documented.
Final-head CI and exact-main package evidence remain post-commit checks recorded on the PR.
The performance guide distinguishes
empirical per-invocation quantiles from production queueing/tail latency, wall occupancy from CPU/cost,
temporary-volume fsync from deployment durability, and memory parsing from interpreter/disk startup.
The source distribution includes the harness; wheel runtime contents/public APIs/dependencies do not change.

Acceptance: runnable no-extra-dependency source/sdist/installed-wheel workloads; bounded errors and
non-overwrite output; no false success on changed behavior; exact report compatibility and recomputed
statistics; real Linux/Windows execution; retained raw evidence; reviewed/green commits and exact-main
package verification. Measured observations and final evidence will be recorded on this increment's PR.

Remaining P1 gates are owner-selected deployment identity/storage/rollback/supervisor acceptance,
aggregate resource/spend limits, external pilot, legal/publication identity/approval and actual release.
P2 work is controlled deployment load/SLO selection, profile-led optimizations with semantic parity,
and selected long-lived/browser/refresh OAuth flows. Local benchmark observations do not close those
gates. No paid service, production deployment, package publication or sibling repository change.

## Previous increment: interrupted artifact publication and process restart

Baseline revalidated: clean, synchronized `main` at `036e52ce0bcc0212ec80b5c655668803eb4183ab`
on 2026-08-31. Work branch: `codex/deployment-crash-recovery`. Previous goal turn was concrete
progress: the TLS/OAuth increment was merged and its exact main distributions were verified.
This increment keeps the independently useful library/CLI shape and addresses deployment operators
who must know which policy a restarted support/coding agent will enforce after an interrupted rollout.

The existing artifact writers flushed staged file contents and published one canonical pathname,
but tests only simulated collisions in process. Their cleanup handled selected ordinary errors,
not `KeyboardInterrupt`/`SystemExit` or other Python unwinding. An internal “durably replace” docstring
also overstated what file fsync alone establishes: directory metadata was not synced.

Bounded research checked [OPA persisted bundles](https://www.openpolicyagent.org/docs/management-bundles)
and its [storage boundary](https://www.openpolicyagent.org/docs/storage), which distinguish policy
recovery from an authoritative durable data source. Linux's
[fsync contract](https://man7.org/linux/man-pages/man2/fsync.2.html) distinguishes file contents from
directory-entry durability. The concrete decision is to prove the library's actual local process
boundary, not introduce a database, watcher, credential store, or claim OS/power-loss guarantees.

Implemented work:

- The shared atomic writer now attempts staging cleanup in `finally`, preserving the original
  exception when cleanup itself fails. Public APIs, serialized formats and dependencies are unchanged.
- Four artifact families (policy, policy deployment, tool-gate deployment, authenticated envelope)
  are tested with actual publisher termination during partial staging, after file fsync, and after
  publication. A separate fresh interpreter validates the selected canonical artifact and outcomes.
- Concurrent exclusive publishers are released from the same pre-publication barrier; exactly one
  succeeds, and the loser cannot overwrite the winning artifact.
- Fresh authenticated bindings reject wrong keys/audiences, expired/future envelopes, rollback below
  the trusted minimum sequence and tampered MACs before any callback. Missing/corrupt active files
  do not cause fallback to previous or abandoned staging files.
- The runnable emergency-lockdown demo shows that memory-only activation does not survive a fresh
  process, explicit publication changes the fresh process's decision, and corrupt input returns an
  error rather than a decision. It touches only its own temporary files and performs no tool effects.
- Linux/Windows process-contract CI is required by main distribution attestation. Contributor,
  release, runtime and deployment documentation describe the same recovery boundary.

Completed local checks: **677 core tests passed in 423.76 seconds, 95.47% coverage**;
**38 real-process contracts passed in 36.18 seconds**; **54 focused I/O tests passed**, including
14 new interruption/cleanup cases. Ruff check and format (97 files), mypy (41 source files), build,
Twine and the fresh-process demo pass on Windows/Python 3.11.9. The installed wheel passes all
**52 new interruption/process checks in 38.68 seconds** and **123 MCP client contracts in 46.16
seconds**. A separate no-optional-dependency environment passes pip check and the restart demo;
archive inspection confirms the example is in the sdist and the process-kill fixture is not shipped.

[PR #45](https://github.com/Deathcharge/samsarix-agent-ethics/pull/45) has all 13 test jobs green at
`b61e671d795e5b19145f39e406ccc8e9c72b07d9`, including both process-recovery platforms. The completed
Codex Security diff scan `23edb34a-39f4-471b-acb7-9b9d9cde3577` reviewed all 15 changed files at that
head with no reportable findings or deferred candidates. It is a focused source/regression review,
not a whole-repository independent penetration test. Preflight passed without configuration edits;
TAC access/grants could not be verified because the access connector was not connected. CodeRabbit's
automatic status said review skipped, which is not external review approval. Follow-up changes only
clarify best-effort cleanup wording and record this evidence. Final-head CI and exact-main artifact
attestation remain post-commit/merge checks, recorded on the PR rather than claimed prospectively here.

Acceptance requires: no partial canonical artifact after owned-process death; preserved exclusive
create semantics; fresh load/verification before decisions or callbacks; no implicit rollback or
temporary-file recovery; interruption cleanup that preserves primary failures; passing source and
installed-wheel contracts; exact-head CI and reviewed commits. A filesystem error can occur after
publication, so callers must reconcile the canonical artifact instead of blindly retrying.

Remaining work, in value order:

1. P1 deployment: an owner-selected controller/storage system must persist protected desired state,
   keys, trusted time/sequence anchors and reviewer identity; fence old workers during revocation;
   and prove OS/power-loss, volume and process-supervisor recovery. File publication is not that system.
2. P1 network/resource acceptance: real identity-provider/proxy configuration and outer process,
   request/header, aggregate workflow and spend limits remain deployment responsibilities.
3. P1 owner release/adoption gates: protected publication identity/approval, licensing review and
   an external pilot. No package/tag/release, paid service or production deployment is authorized here.
4. P2: measured latency/load targets and selected long-lived OAuth SSE/browser/refresh flows.

Release disposition remains **release candidate with named external gates**. The library does not
persist `PolicyRuntime` generations or choose a recovery artifact. Normal interruption cleanup is
best effort; abrupt process death or filesystem failure may leave private staging files. Operators
must identify abandoned files only after their writer stops, never glob-load or auto-promote them.
No sibling repository, licensing, runtime dependency, live infrastructure or system trust was changed.

## Previous increment: verified TLS and client-credentials OAuth

Baseline revalidated: clean, synchronized `main` at `277c379b8492cb093a256d7261af73bb00843f9a`
on 2026-08-31. Work branch: `codex/mcp-tls-oauth-contract`. The product remains an independently
usable policy-gating library/CLI for developers operating agents. This increment proves a concrete
machine-to-machine support workflow: read a ticket, approve a reply, block deletion, with a real
TLS connection and an OAuth-authenticated server principal.

The preceding TCP contract used static test bearer tokens and could not establish certificate
validation or the SDK's actual OAuth lifecycle. Added a narrow, ephemeral authorization server
and separate protected resource origin, both served over loopback HTTPS. Tests use the stock
`ClientCredentialsOAuthProvider` in MCP 2.1.1, not a mocked provider. The existing hashed client lock
already supplies cryptography; no package dependency, runtime API, external account, production
service or system trust-store change was required. Test servers/certificates/stores are explicitly
not a deployable identity service.

Primary research: the [SDK OAuth client guide](https://py.sdk.modelcontextprotocol.io/client/oauth-clients/),
[MCP authorization specification](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization),
and HTTPX2 [request hooks](https://httpx2.pydantic.dev/advanced/event-hooks/)/
[timeout extensions](https://httpx2.pydantic.dev/advanced/extensions/), checked on 2026-08-31.
Exact installed SDK/HTTPX2 source was inspected where wire behavior differed from expectations.

**123 MCP contracts pass locally in 66.18 seconds**, including **31 new TLS/OAuth cases**:

- Basic/form-post client credentials, JSON/finite SSE, auto/legacy negotiation, and read/review/deny.
- Separate client/provider/store tenant boundaries and no client credentials on metadata endpoints.
- Untrusted CA, hostname mismatch and expired certificates at both resource and issuer origins.
- Invalid client credentials and mismatched resource/issuer metadata before protected execution.
- Resource metadata, issuer metadata and token responses share the existing body-budget latch.
- Token service/storage outages and challenged unauthorized scopes prevent tool dispatch.
- Access-token reacquisition, client revocation during review, cancellation and token-request timeout.
- Exact-version characterization of missing auth-request timeout inheritance and plain-403 replay.

Two integration assumptions were corrected, not hidden by broad exception assertions. An OAuth
revocation error can be raised from the Client context exit as an exception group. More importantly,
the SDK constructs token requests without timeout extensions; HTTPX2 inserts the client default
only on the original request, not subsequent requests yielded by auth. A public async request hook
now supplies missing timeouts in the documented application wiring and test fixture. A wire-boundary
characterization test pins the upstream omission; a stalled token endpoint proves the hook aborts
with a real network read timeout and observable disconnect. A separate cancellation test proves
cleanup without issuing a token or reaching a tool. Every new deployment scenario has a cooperative
20-second bound in addition to bounded server startup/teardown.

The guide also records that remote challenges can replace constructor scopes, plain 403 responses
can be replayed once by SDK auth, SDK exceptions can include remote token-error bodies, and token
state can be updated before durable storage succeeds. Applications must enforce allowed grants and
egress destinations, isolate credential state, redact third-party logs, discard failed providers,
and bound the initial handshake independently of the later policy adapter. None of these behaviors
is misrepresented as a new Samsarix authentication, retry, storage or exactly-once guarantee.

CI now runs all four MCP client contract files on Linux and Windows; contributor/release commands
match. Local Windows/Python 3.11.9 core verification passes **663 tests with 95.36% branch-inclusive
coverage** (449.34 seconds). The local built wheel passes all **123 client contracts from
site-packages** (96.34 seconds). A separate `--no-deps` wheel environment without MCP/AnyIO/HTTPX2
passes imports, version, policy validation, schema output, and read/delete exits 0/3. Wheel/sdist
build and Twine checks pass; neither distribution includes integration fixtures or certificate
keys. Ruff check/format (93 files), mypy (41 source files), `pip check`, the MCP demo and all changed
local documentation links pass. Initial PR CI `33390715248` passes all 11 test jobs: core 663 tests
on Python 3.11–3.14 (3.11 Linux coverage 95.33%), plus every optional adapter including the 123 MCP
client contracts on Linux and Windows. Main-only attestation is correctly skipped on the PR.

Exact-head review/merge and final attested-artifact evidence belong to
[PR #44](https://github.com/Deathcharge/samsarix-agent-ethics/pull/44).
Independent review prompted explicit resource-body assertions for form-post credential containment
(including requests rejected before MCP reads them) and clearer default-versus-explicit timeout
wording. The bounded test observer replays original ASGI messages; all 31 TLS/OAuth cases pass
after this refinement. A stale verification-progress comment was reconciled against the completed
checks above; it did not represent an outstanding test failure.
Final release disposition remains **release candidate**, not publication
or proof of production hosting/product-market fit. No sibling repository or licensing was changed.

Remaining gates, in order:

1. P1 deployment: real identity-provider/proxy acceptance, durable credential rotation/expiry/recovery,
   reviewer identity, and process-crash recovery in an owner-selected environment. Local TLS/OAuth
   acceptance reduces this gap but does not close it.
2. P1 resource controls: process-memory/CPU, request/header, aggregate-workflow and spend quotas remain
   external to per-response body budgets and cooperative phase deadlines.
3. P1 owner gates: protected package publication identity/approval, licensing review, and a genuine
   external adopter evaluation. No package/tag/release or production deployment is authorized here.
4. P2: measured latency/load targets, long-lived OAuth SSE subscriptions/event-store resumption,
   and any selected browser/PKCE, registration or refresh-token flow. These are not covered by the
   machine-client acceptance fixture.

## Previous increment: bounded MCP HTTP response bodies

Baseline revalidated: clean, synchronized `main` at `8ab66e21228292c6537b97b67cb82c4c75e29e52`
on 2026-08-31. Work branch: `codex/mcp-http-response-budgets`. The preceding increment established
real-network policy behavior but left response aggregation unbounded until SDK decoding completed.

Inspection of HTTPX2 2.12.0 and its [public transport API](https://httpx2.pydantic.dev/advanced/transports/)
showed that gzip/deflate decoding already yields bounded chunks. The new wrapper therefore reuses
that streaming API rather than maintaining another compression implementation. Separate counters
bound encoded and decoded response bodies; Content-Length enables early rejection but is not relied
on for unknown/chunked lengths. A local budget/encoding violation closes the response and latches the
wrapper, preventing reconnects from resetting a breached budget. Only identity/gzip/deflate single
encodings are supported; other codings fail closed. No response body is stored in diagnostics.

Public additions: `create_mcp_http_transport`, `MCPHTTPTransport`, `MCPHTTPResponseError`,
`MCP_HTTP_RESPONSE_BUDGET_VERSION` and `DEFAULT_MCP_HTTP_RESPONSE_BYTES`. Each byte budget defaults to
4 MiB and must be an integer from 1 byte to 64 MiB. HTTPX2 2.12.0 is directly declared in the client
extra/input; the existing 30-package hashed lock is unchanged. Core imports still require no HTTP
or MCP dependencies. The recommended guide wiring now enables budgets before opening a Client and
places TLS/proxy/pool configuration on the wrapped transport to avoid bypassing it with HTTP mounts.

Local core verification before the review follow-up: **660 tests pass with 95.35% branch-inclusive
coverage**. The final module's **44 unit tests cover 100%** of its statements/branches.
**92 exact-SDK client tests pass**, including 52 new transport tests. Tests cover exact boundaries,
incremental wire/decoded overflow,
declared/chunked bodies, gzip/deflate inflation and corruption, unsupported encodings, failed
discovery before tool dispatch, oversized results after one authorized invocation, both MCP modes
and JSON/SSE formats, interleaved failure latching, cancellation and single-connection pool pressure.
Final engineering review caught an SDK-internal cleanup path outside the original timeout guard;
the stream close now has the same shielded deadline. Five deliberately stalled cleanup cases cover
iteration, explicit response close, header rejection, transport close and context exit.
An additional strict-consumer typing check found that the dynamic runtime transport base was not
visible to type checkers. A type-checking-only nominal base fixes direct `AsyncClient` wiring without
importing optional dependencies at runtime; a bounded subprocess regression now checks this in CI.
External review also prompted preservation of primary exceptions during failed cleanup. Close-only
errors still propagate, while an active primary error/cancellation receives a fixed recovery note;
12 exact-SDK regressions cover raised/timed-out cleanup after wire/decoded/decoder/header failures
and caller errors/cancellation. The reviewer withdrew a proposed HTTPS-enforcement change after
confirming endpoint/auth configuration is application-owned. The guide makes that boundary explicit;
SECURITY.md now accurately distinguishes network-free core evaluation from optional network I/O.
This corrects exposure documentation without introducing new vulnerability-class exclusions.

On Windows/Python 3.11.9, Ruff formatting/lint, mypy (41 source files), locked installation and
`pip check`, wheel/sdist build and Twine checks pass. The built wheel passes all 92 client contracts
from site-packages. A separate `--no-deps` wheel environment without MCP/AnyIO/HTTPX2 passes imports,
CLI version, policy validation and allow/deny exits 0/3. Wheel contents include the new module and
optional dependency metadata but exclude the integration server fixture; changed-document local
links resolve. `pip-audit` 2.10.1 reports no known vulnerabilities in the unchanged client lock.
Final-head full core/CI, review resolution and exact merged-artifact evidence will be recorded in
[PR #43](https://github.com/Deathcharge/samsarix-agent-ethics/pull/43).

Final acceptance remains a release candidate, not proven production hosting or external demand.
No sibling repository, production service, package publication or licensing was changed.
Remaining priorities:

1. P1: real TLS/OAuth/proxy and crash-recovery acceptance in an owner-selected deployment. Credential
   storage/rotation, authenticated reviewer identity and durable outcomes remain application-owned.
2. P1: outer process-memory/CPU, request/header and aggregate workflow quotas. Body counters run
   after HTTP parser buffers and one decoder chunk (up to 1 MiB) are allocated; they are not an RSS cap.
3. P1 owner gates: protected publication identity/approval and genuine external adopter validation.
4. P2: latency/load budgets and SSE event-store resumption acceptance. Ordinary pool errors and
   cancellation remain distinct from a latched response-contract failure.

Earlier delivered SSE events or remote side effects cannot be undone by a later result rejection.
In-flight streams check the latch on their next decoded chunk, not while waiting for network data.
The supplied transport must be trusted, streaming and unshared; custom eager buffering or routes
that bypass the wrapper remain outside this boundary. No automatic reconstruction/retry loop,
credential store, telemetry sink or paid service was added.

## Previous increment: real MCP v2 HTTP boundary

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

PR #42's actual review reported one documentation finding: the example's 30-second HTTP idle
timeout remains effective even when the adapter dispatch deadline is increased. Confirmed against
the exact SDK transport and clarified both independent limits, without weakening the bounded
default or implying that network heartbeats extend the adapter deadline.

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
