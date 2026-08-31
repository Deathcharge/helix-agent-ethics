# Measure policy-gate overhead

Samsarix is an in-process deterministic gate. Measure its cost on the machine, policy, storage and
application boundary you intend to operate; correctness tests alone do not establish a latency SLO.
The repository includes a zero-extra-dependency benchmark tool, shipped in the source distribution
but deliberately not exposed as a runtime library API or installed CLI command.

## Run and compare

From this repository (or an extracted source distribution), after installing the package:

```bash
python -m benchmarks.policy_gate run --output baseline.json
python -m benchmarks.policy_gate run --output candidate.json
python -m benchmarks.policy_gate compare baseline.json candidate.json --max-regression-percent 20
```

The output path must be new and its parent must exist. Without `--output`, `run` writes JSON to
stdout. UTF-8 files are produced explicitly on Windows as well as Linux. A completed run exits `0`;
invalid options, malformed/incompatible reports, incorrect workload behavior, or exhausted budgets
exit `2`. Comparison exits `1` when any workload's median exceeds the chosen regression budget.
Equality with the budget passes. This is an operator-selected relative budget, not a shipped SLO.

Use the **same benchmark source, fixtures, machine, interpreter, GC settings and workload options**
for before/after measurements. To evaluate two wheels, keep this checkout unchanged and install
each wheel into otherwise identical environments, then invoke this same module using each
environment's Python. Do not compare measurements taken while another benchmark/test run is active.
Run multiple alternating baseline/candidate measurements on an otherwise quiet machine before
attributing a difference to code. CPU frequency, temperature, scheduling, virtualization and disk
caches can dominate short measurements even when reported environment labels match.

Reports record the package version and a content fingerprint of its imported Python/schema files,
the exact harness hash, fixture fingerprint, environment labels, and raw per-invocation nanoseconds.
No repository path, hostname, actor, arguments, policy content or callback result is emitted.
Environment fields describe the interpreter/OS/processor; inspect them before sharing. Reports are
unsigned observations, not authenticated benchmark evidence. Keep baseline files under trusted
change control. Matching labels do not prove identical hardware or load.

The comparator rejects changed harnesses, fixtures, environments, workload order/counts, fingerprints
and sampling options. It validates bounded positive integer raw samples, rejects duplicate JSON keys
and non-finite values (including overflowing exponent notation), and recomputes medians from samples
instead of trusting summary fields. Inputs must be regular files, not pipes/devices; keep input paths
and their parent directories under operator control while reading and comparing.
Package versions/content fingerprints may differ: that is the intended before/after variable.
It does not prove a performance change is statistically significant or safe for production.

## What the workloads include

| Workload | Timed boundary | Correctness check |
| --- | --- | --- |
| `linear/N/last-match`, `linear/N/no-match` | One `PolicyEngine.evaluate`, including input validation, all N single-condition rules, UUID/time and decision construction | Exact allow/default-deny outcome and evaluated-rule count |
| `coding/load-and-bind` | Parse an in-memory deployment JSON string, validate fingerprints/lock/contract/catalog and construct a dispatcher | Exact registry size; this excludes disk reads and interpreter startup |
| `coding/dispatch-read` | Prepare/validate a fresh call, enforce the checked-in coding policy and contract, invoke the frozen in-memory callback | Allow, one callback and expected result |
| `coding/dispatch-deny`, `coding/dispatch-review` | Same boundary, including typed block construction and handling | Correct deny/review, zero callbacks |
| `coding/batch-read-8`, `coding/batch-deny-8` | Fresh preparation and complete authorization of eight calls, plus callbacks only for an allowed batch | Eight allows/callbacks or a final denied call with zero callbacks for the entire batch |
| `coding/jsonl-read` | Full read dispatch plus real `JsonlAuditSink` open/append/file-fsync/close in a private temporary directory | One callback and one valid audit record per invocation |
| `coding/shadow-read` | Baseline and candidate evaluation with the real coding context contract and shadow report construction | Baseline allows; the candidate denies without changing baseline authority |

Every timed invocation includes small harness correctness checks. Do not subtract a guessed timer,
wrapper or callback overhead. Synthetic rules are deliberately simple and scan all rules; their
count is not a proxy for arbitrary policy complexity. Real coding workloads use the checked-in
deployment and trusted tool catalog. Callback bodies only increment a counter and return a fixed
string: there is no real file read, shell command, external call, reviewer, model or paid API.
Prepared calls are fresh for every batch; the benchmark never reuses an authorization as a capability.

## Sampling, safety and limitations

Defaults are 50 iterations per repeat, five repeats, five warmups, and 10/100/1,000 synthetic rules.
Loading/binding and filesystem audit workloads are capped at ten iterations and two warmups per
run configuration (warmup happens once before all repeats). This limits real fsync calls. GC is not
disabled. Warmup samples are discarded; repeated measurements are individual calls, **not** batch
averages mislabeled as request percentiles. `repeat_mean_ns` also exposes per-repeat variation.
Median, arithmetic mean, minimum and nearest-rank empirical p95/p99 are reported. The default slow
workloads have only 50 measured samples; their high percentiles are especially weak tail estimates.
These closed-loop observations exclude queueing and are not open-loop production latency percentiles.

The tool caps total invocations (including warmup) at 20,000, estimated rule visits at 10 million,
and input reports at 2 MB. `--max-seconds` defaults to 60 and accepts at most 600; it checks before
and after each operation. **This cooperative deadline cannot interrupt a stuck filesystem syscall.**
Use an outer process supervisor for a hard wall-time limit. No partial-success performance report is
written after a failed workload. Output uses exclusive creation, not a durable transaction: an I/O
failure while saving may leave an incomplete report, which must not be used as a baseline.
Temporary audit files are cleaned on normal exit; abrupt termination can leave owned temporary files.

The audit scenario measures the system temporary directory's filesystem, not an operator-selected
production volume. File fsync is not directory/power-loss durability. It does not benchmark the HMAC
audit chain, remote collectors, TLS/OAuth, SDK execution, application side effects, concurrent clients,
aggregate memory, queueing or system failure. [Recovery boundaries](POLICY_DEPLOYMENTS.md#interrupted-publication-and-restart)
and [security responsibilities](../SECURITY.md) still apply.

At a workload rate `R` calls/second and measured mean wall time `t` seconds/call, `R * t` estimates
serial occupied seconds per second **for this workload only**. It is not CPU utilization, achievable
throughput or a cloud-cost quote; file waits and application concurrency matter. For batches, one
invocation contains eight decisions; for shadow it contains two. Set whole-application latency,
concurrency, memory and spend budgets using deployment measurements and leave measured headroom.

## CI evidence and methodology

### Exact-built-in optimization observation (2026-08-31)

Profiling the `a4f0707` baseline identified generic container/type checks during ordinary string
equality and dictionary field lookup. The candidate at `b00df32` adds exact `str`/`dict` fast paths;
subclasses and other mappings still use the existing generic behavior. There is no field-value
cache, policy index, skipped validation, early rule exit, new runtime dependency or API change.
Golden and baseline-differential tests cover scalar/structured equality, bool/number distinctions,
Unicode, custom mappings/subclasses, references, mutation, decisions, explanations and batches.

Three paired runs used separately installed baseline/candidate wheels, the same unchanged harness,
the default 14 workloads and the same Windows/CPython 3.11.9 interpreter. Execution order was
baseline-1, candidate-1, candidate-2, baseline-2, baseline-3, candidate-3. No other benchmark or test
ran concurrently, but the desktop and read-only developer tooling were not isolated. These are
**local observations with substantial between-run variation**, not a controlled experiment or SLO.

The table reports the median of the three run medians in milliseconds/invocation, and the range of
the three paired candidate changes. Negative changes mean a lower measured median, not a promised
speedup. The unchanged load/bind path also moved, showing why noise cannot be attributed to code.

| Workload | Baseline median of medians (ms) | Candidate median of medians (ms) | Paired median change range |
| --- | ---: | ---: | ---: |
| 10 rules / last-match | 0.09120 | 0.05035 | -70.14% to -35.04% |
| 10 rules / no-match | 0.08740 | 0.04680 | -69.68% to -34.68% |
| 100 rules / last-match | 0.65680 | 0.22750 | -80.00% to -56.45% |
| 100 rules / no-match | 0.58760 | 0.21805 | -62.89% to -45.78% |
| 1,000 rules / last-match | 6.65850 | 2.03950 | -81.19% to -58.70% |
| 1,000 rules / no-match | 8.42760 | 2.11130 | -78.59% to -69.66% |
| Coding load/bind | 5.49990 | 5.17480 | -9.72% to -5.91% |
| Coding read dispatch | 0.24930 | 0.19360 | -52.59% to -13.45% |
| Coding deny dispatch | 0.26775 | 0.19200 | -60.18% to -21.96% |
| Coding review dispatch | 0.32380 | 0.21035 | -44.00% to -31.54% |
| Eight-call allowed batch | 2.72775 | 1.84725 | -40.24% to -32.28% |
| Eight-call denied batch | 3.19550 | 2.05580 | -63.20% to -8.09% |
| Read with JSONL fsync | 2.26810 | 1.64860 | -41.99% to +8.06% |
| Baseline/candidate shadow | 0.76900 | 0.31455 | -68.66% to -24.94% |

All six reports are retained, including the slower candidate filesystem-audit observation:
[baseline 1](../benchmarks/results/2026-08-31-hot-path/baseline-1.json),
[candidate 1](../benchmarks/results/2026-08-31-hot-path/candidate-1.json),
[candidate 2](../benchmarks/results/2026-08-31-hot-path/candidate-2.json),
[baseline 2](../benchmarks/results/2026-08-31-hot-path/baseline-2.json),
[baseline 3](../benchmarks/results/2026-08-31-hot-path/baseline-3.json),
[candidate 3](../benchmarks/results/2026-08-31-hot-path/candidate-3.json).
Each pair passes strict compatibility checks and a 20% median-regression comparison. That chosen
budget is an inspection aid, not a statistical significance test or shared-runner CI threshold.

Reproduce the report comparison, substituting pair numbers 1, 2 and 3:

```bash
python -m benchmarks.policy_gate compare benchmarks/results/2026-08-31-hot-path/baseline-1.json benchmarks/results/2026-08-31-hot-path/candidate-1.json --max-regression-percent 20
```

The baseline is the attested `a4f07077d96b82c29ba52c7ca806268694a185be` wheel, SHA-256
`7efd712397f0179af36574c3381f300f6edee53e9b4482e6a7e95d0cc88e3e70`. The locally built candidate
wheel at `b00df32cfb5c46e0fe901cc9b71e777983bb2ea5` has SHA-256
`31913fdf49e1ffc8df4f62aa5a1cc6f8b66fc5060e697112217848418ebce1b0`.
All reports identify harness SHA-256 `25a20a9180ac2c44b377399f11597e4f5aeedea389447f257b0a3f7f7295c3d3`;
their package fingerprints distinguish the runtime contents despite both versions being 0.1.0.
Follow-up documentation/build metadata may change archive hashes without changing measured runtime
contents. Do not relabel historical reports as measurements of a later artifact.

### Initial baseline observation

One illustrative Windows/CPython 3.11.9 installed-wheel run is retained with
[all raw samples and environment metadata](../benchmarks/results/2026-08-31-windows-python311.json).
It used the default 14-workload configuration, eight reported logical CPUs, GC enabled and a 100 ns
reported clock resolution. No tests or another benchmark ran concurrently, but this was a developer
desktop, not isolated deployment hardware. Selected measured medians and empirical p95 values:

| Workload | Median milliseconds/invocation | Empirical p95 milliseconds/invocation |
| --- | ---: | ---: |
| Coding read dispatch | 0.42345 | 0.80700 |
| Eight-call allowed batch (including fresh preparation) | 3.86055 | 5.95650 |
| Read with local JSONL file fsync | 1.99205 | 3.69730 |
| Baseline/candidate shadow evaluation | 0.61530 | 1.38190 |
| 1,000-rule synthetic last-match evaluation | 13.93350 | 22.54650 |

These are historical observations, not promised thresholds or deployment sizing. They show why
scan complexity, batching and storage must be measured separately. The raw report identifies its
exact harness, fixture and imported-package content fingerprints; the package version alone is not
enough to identify an unreleased build. A changed harness requires a fresh compatible baseline.
The retained historical harness is at commit `ccad1729cec4c88d46ea7f1b795df03441645837`;
subsequent report-parser hardening does not retroactively change this observation.

Linux/Windows process-contract jobs run a short 14-workload suite (10 iterations, three repeats,
two warmups) and retain `policy-benchmarks-<os>-<commit>` JSON artifacts for 14 days. CI validates
workload correctness, report shape/comparison and resource limits; it does **not** gate on noisy
shared-runner latency statistics or a relative speed threshold. The 120-second cooperative run cap
is an intentional blocking resource/completion guard, like the enclosing job timeout: exhaustion
means this required run did not complete, not that a latency SLO was missed. Correctness failures
also remain blocking. A produced report is retained even if a later check fails; failed/incomplete
runs are not manufactured into successful timing evidence. The normal Python matrix tests invalid
evidence and comparator exit behavior.
Run larger acceptance measurements on controlled deployment hardware before selecting an SLO.

[OPA's performance guidance](https://www.openpolicyagent.org/docs/policy-performance) distinguishes
policy structure and profiling from end-to-end authorization overhead.
[Python's timing guidance](https://docs.python.org/3/library/timeit.html) explains repeated timing,
interference and GC behavior. Those sources informed this tool's explicit timed boundaries and raw
repeat evidence; this suite is not a comparative OPA/Cedar benchmark and makes no superiority claim.
