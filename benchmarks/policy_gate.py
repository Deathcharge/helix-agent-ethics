# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Bounded, correctness-checked local policy workloads and compatible-run comparison."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import os
import platform
import re
import statistics
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import samsarix_ethics
from samsarix_ethics import (
    AuditRecord,
    Outcome,
    Policy,
    PolicyEngine,
    PolicyShadowEvaluator,
    SamsarixEthicsError,
    ToolCallBlockedError,
    ToolDispatcher,
    build_tool_context,
    create_tool_gate_deployment,
    fingerprint_policy,
    load_policy_deployment,
    load_tool_catalog,
)

ROOT = Path(__file__).resolve().parents[1]
REPORT_VERSION = 1
MAX_SAMPLES = 20_000
MAX_RULE_VISITS = 10_000_000
MAX_REPORT_BYTES = 2_000_000
ENVIRONMENT_FIELDS = {
    "python",
    "implementation",
    "system",
    "release",
    "machine",
    "processor",
    "logical_cpus",
    "gc_enabled",
    "clock_resolution_ns",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


@dataclass
class Workload:
    name: str
    rule_count: int
    decisions_per_call: int
    fingerprint: str
    run: Callable[[], None]
    slow: bool = False


def synthetic_workloads(rule_counts: list[int]) -> list[Workload]:
    workloads = []
    for count in rule_counts:
        policy = Policy.from_dict(
            {
                "schema_version": 1,
                "id": "benchmark-linear-policy",
                "version": "1",
                "default_effect": "deny",
                "rules": [
                    {
                        "id": f"allow-{index}",
                        "effect": "allow",
                        "conditions": [
                            {"field": "action.operation", "operator": "eq", "value": str(index)}
                        ],
                    }
                    for index in range(count)
                ],
            }
        )
        engine = PolicyEngine(policy)
        for label, operation, expected in (
            ("last-match", str(count - 1), Outcome.ALLOW),
            ("no-match", "absent", Outcome.DENY),
        ):

            def run(
                engine: PolicyEngine = engine,
                operation: str = operation,
                expected: Outcome = expected,
            ) -> None:
                decision = engine.evaluate({"action": {"operation": operation}})
                require(decision.outcome == expected, "Synthetic decision changed")
                require(decision.evaluated_rules == len(engine.policy.rules), "Rule scan changed")

            workloads.append(
                Workload(f"linear/{count}/{label}", count, 1, fingerprint_policy(policy), run)
            )
    return workloads


def coding_workloads(directory: Path) -> tuple[list[Workload], Callable[[], None], str]:
    deployment = create_tool_gate_deployment(
        load_policy_deployment(ROOT / "examples/deployment/coding-agent-baseline.deployment.json"),
        load_tool_catalog(ROOT / "examples/catalogs/coding-agent-tools.json"),
    )
    policy = deployment.policy_deployment.policy
    fingerprint = digest(deployment.to_dict())
    actor = {"id": "benchmark-coding-agent"}
    context = {"workspace_contained": True}
    callback_count = 0
    audit_calls = 0
    audit_path = directory / "decisions.jsonl"

    def callback(**_arguments: Any) -> str:
        nonlocal callback_count
        callback_count += 1
        return "benchmark-read-result"

    callbacks = dict.fromkeys(deployment.tool_catalog.tool_names, callback)
    dispatcher = ToolDispatcher.bind_deployment(deployment, registered_tools=callbacks)
    audited = ToolDispatcher.bind_deployment(
        deployment, registered_tools=callbacks, audit_log=audit_path
    )

    def execute(tool: str, expected: Outcome, *, audit: bool = False, batch: bool = False) -> None:
        nonlocal audit_calls
        before = callback_count
        selected = audited if audit else dispatcher
        count = 8 if batch else 1
        try:
            if batch:
                calls = [
                    selected.prepare(
                        "read_file" if index < count - 1 else tool,
                        {"path": "README.md"},
                        actor=actor,
                        context=context,
                    )
                    for index in range(count)
                ]
                results = selected.execute_many(calls)
            else:
                results = (
                    selected.execute(tool, {"path": "README.md"}, actor=actor, context=context),
                )
        except ToolCallBlockedError as error:
            require(expected != Outcome.ALLOW, "Allowed workload was blocked")
            require(error.decision.outcome == expected, "Wrong blocked decision")
            require(callback_count == before, "Blocked workload executed a callback")
            if batch:
                require(error.blocking_index == 7, "Wrong blocking batch index")
                require(len(error.decisions) == 8, "Batch was not fully evaluated")
            return
        require(expected == Outcome.ALLOW, "Blocked workload was allowed")
        require(len(results) == count, "Wrong result count")
        require(callback_count == before + count, "Callback count changed")
        require(all(result.decision.allowed for result in results), "Non-allow result executed")
        require(all(result.value == "benchmark-read-result" for result in results), "Wrong result")
        if audit:
            audit_calls += 1

    def load_and_bind() -> None:
        # Deliberately include bounded JSON parsing, fingerprint/lock verification and binding.
        restored = type(deployment).from_dict(json.loads(serialized))
        bound = ToolDispatcher.bind_deployment(restored, registered_tools=callbacks)
        require(len(bound) == len(callbacks), "Restored registry mismatch")

    serialized = json.dumps(deployment.to_dict())
    candidate_data = policy.to_dict()
    candidate_data["version"] = "benchmark-candidate"
    candidate_data["rules"].append(
        {
            "id": "benchmark-lockdown",
            "effect": "deny",
            "conditions": [{"field": "action.operation", "operator": "eq", "value": "read_file"}],
        }
    )
    shadow = PolicyShadowEvaluator(
        policy,
        Policy.from_dict(candidate_data),
        context_contract=deployment.policy_deployment.context_contract,
    )
    shadow_input = build_tool_context(
        "read_file",
        {"path": "README.md"},
        capabilities=next(
            t.capabilities for t in deployment.tool_catalog.tools if t.name == "read_file"
        ),
        actor=actor,
        context=context,
    )

    def observe() -> None:
        result = shadow.evaluate(shadow_input)
        require(result.authoritative_decision.allowed, "Shadow baseline changed")
        require(result.candidate_decision is not None, "Shadow candidate failed")
        require(result.candidate_decision.outcome == Outcome.DENY, "Shadow candidate changed")

    specifications: list[tuple[str, int, Callable[[], None], bool]] = [
        ("load-and-bind", 0, load_and_bind, True),
        ("dispatch-read", 1, lambda: execute("read_file", Outcome.ALLOW), False),
        ("dispatch-deny", 1, lambda: execute("delete_file", Outcome.DENY), False),
        ("dispatch-review", 1, lambda: execute("run_command", Outcome.REVIEW), False),
        ("batch-read-8", 8, lambda: execute("read_file", Outcome.ALLOW, batch=True), False),
        ("batch-deny-8", 8, lambda: execute("delete_file", Outcome.DENY, batch=True), False),
        ("jsonl-read", 1, lambda: execute("read_file", Outcome.ALLOW, audit=True), True),
        ("shadow-read", 2, observe, False),
    ]

    def verify_audit() -> None:
        with audit_path.open(encoding="utf-8") as stream:
            records = [AuditRecord.from_dict(json.loads(line)) for line in stream]
        require(len(records) == audit_calls, "Audit delivery count changed")
        require(all(record.outcome == Outcome.ALLOW for record in records), "Audit outcome changed")
        require(
            audit_path.stat().st_size <= MAX_REPORT_BYTES * 10, "Audit fixture grew unexpectedly"
        )

    return (
        [
            Workload(f"coding/{name}", len(policy.rules), units, fingerprint, run, slow)
            for name, units, run, slow in specifications
        ],
        verify_audit,
        fingerprint,
    )


def summarize(samples: list[int]) -> dict[str, float]:
    require(
        isinstance(samples, list)
        and 0 < len(samples) <= MAX_SAMPLES
        and all(type(x) is int and 0 < x <= 600_000_000_000 for x in samples),
        "Invalid timing sample",
    )
    ordered = sorted(samples)
    return {
        "min_ns": min(samples),
        "median_ns": statistics.median(samples),
        "p95_ns": ordered[math.ceil(0.95 * len(samples)) - 1],
        "p99_ns": ordered[math.ceil(0.99 * len(samples)) - 1],
        "mean_ns": statistics.mean(samples),
    }


def measure(
    workload: Workload, iterations: int, repeats: int, warmup: int, deadline: float
) -> dict:
    samples: list[int] = []
    repeat_means = []
    for repeat in range(-1, repeats):
        current = []
        for _ in range(warmup if repeat == -1 else iterations):
            require(
                time.monotonic() < deadline, "Benchmark time budget exhausted; no report written"
            )
            started = time.perf_counter_ns()
            workload.run()
            elapsed = time.perf_counter_ns() - started
            require(
                time.monotonic() < deadline, "Benchmark time budget exhausted; no report written"
            )
            if repeat >= 0:
                current.append(elapsed)
        if repeat >= 0:
            samples.extend(current)
            repeat_means.append(statistics.mean(current))
    summary = summarize(samples)
    return {
        "name": workload.name,
        "rule_count": workload.rule_count,
        "decisions_per_call": workload.decisions_per_call,
        "workload_fingerprint": workload.fingerprint,
        "iterations": iterations,
        "repeats": repeats,
        "warmup": warmup,
        "samples_ns": samples,
        "repeat_mean_ns": repeat_means,
        **summary,
    }


def run_benchmarks(
    iterations: int, repeats: int, warmup: int, rule_counts: list[int], seconds: float
) -> dict:
    require(type(iterations) is int and 1 <= iterations <= 1000, "iterations must be 1..1000")
    require(type(repeats) is int and 1 <= repeats <= 20, "repeats must be 1..20")
    require(type(warmup) is int and 0 <= warmup <= 1000, "warmup must be 0..1000")
    require(bool(rule_counts) and len(rule_counts) <= 5, "Provide 1..5 rule counts")
    require(
        all(type(n) is int and 1 <= n <= 1000 for n in rule_counts), "rule counts must be 1..1000"
    )
    require(len(set(rule_counts)) == len(rule_counts), "Duplicate rule counts")
    require(
        type(seconds) in (int, float) and math.isfinite(seconds) and 0 < seconds <= 600,
        "max-seconds must be finite and in (0, 600]",
    )
    deadline = time.monotonic() + seconds
    with TemporaryDirectory(prefix="samsarix-benchmark-") as directory:
        coding, verify_audit, fixture_fingerprint = coding_workloads(Path(directory))
        workloads = synthetic_workloads(rule_counts) + coding
        counts = [
            (min(iterations, 10), min(warmup, 2)) if w.slow else (iterations, warmup)
            for w in workloads
        ]
        calls = [repeats * n + warm for n, warm in counts]
        require(sum(calls) <= MAX_SAMPLES, "Requested work exceeds 20000 invocation budget")
        require(
            sum(
                c * w.rule_count * max(1, w.decisions_per_call)
                for c, w in zip(calls, workloads, strict=True)
            )
            <= MAX_RULE_VISITS,
            "Requested work exceeds estimated rule-visit budget",
        )
        results = [
            measure(w, n, repeats, warm, deadline)
            for w, (n, warm) in zip(workloads, counts, strict=True)
        ]
        verify_audit()
    environment = {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "logical_cpus": os.cpu_count(),
        "gc_enabled": gc.isenabled(),
        "clock_resolution_ns": time.get_clock_info("perf_counter").resolution * 1e9,
    }
    return {
        "report_version": REPORT_VERSION,
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "fixture_fingerprint": fixture_fingerprint,
        "package_version": samsarix_ethics.__version__,
        "package_fingerprint": digest(
            {
                p.relative_to(Path(samsarix_ethics.__file__).parent).as_posix(): hashlib.sha256(
                    p.read_bytes()
                ).hexdigest()
                for p in sorted(Path(samsarix_ethics.__file__).parent.rglob("*"))
                if p.is_file() and p.suffix in {".py", ".json"}
            }
        ),
        "environment": environment,
        "results": results,
    }


def read_report(path: Path) -> dict:
    with path.open("rb") as stream:
        payload = stream.read(MAX_REPORT_BYTES + 1)
    require(len(payload) <= MAX_REPORT_BYTES, "Report exceeds byte budget")

    def unique(pairs: list[tuple[str, Any]]) -> dict:
        require(len({key for key, _ in pairs}) == len(pairs), "Duplicate report key")
        return dict(pairs)

    def reject_constant(_value: str) -> None:
        raise ValueError("Non-finite JSON value")

    report = json.loads(
        payload.decode("utf-8-sig"), object_pairs_hook=unique, parse_constant=reject_constant
    )
    validate_report(report)
    return report


def validate_report(report: Any) -> None:
    require(
        isinstance(report, dict)
        and type(report.get("report_version")) is int
        and report["report_version"] == REPORT_VERSION,
        "Unsupported benchmark report",
    )
    for field in ("harness_sha256", "fixture_fingerprint", "package_fingerprint"):
        require(
            isinstance(report.get(field), str)
            and re.fullmatch(r"[0-9a-f]{64}", report[field]) is not None,
            f"Invalid {field}",
        )
    require(
        isinstance(report.get("package_version"), str)
        and 0 < len(report["package_version"]) <= 100,
        "Invalid package_version",
    )
    env = report.get("environment")
    require(isinstance(env, dict) and set(env) == ENVIRONMENT_FIELDS, "Invalid environment")
    require(
        all(
            isinstance(env[f], str) and len(env[f]) <= 1000
            for f in ENVIRONMENT_FIELDS - {"logical_cpus", "gc_enabled", "clock_resolution_ns"}
        ),
        "Invalid environment label",
    )
    require(type(env["gc_enabled"]) is bool, "Invalid GC metadata")
    require(
        env["logical_cpus"] is None
        or (type(env["logical_cpus"]) is int and 1 <= env["logical_cpus"] <= 100_000),
        "Invalid CPU metadata",
    )
    require(
        type(env["clock_resolution_ns"]) in (int, float)
        and math.isfinite(env["clock_resolution_ns"])
        and 0 < env["clock_resolution_ns"] <= 1e9,
        "Invalid clock metadata",
    )
    results = report.get("results")
    require(isinstance(results, list) and 1 <= len(results) <= 18, "Invalid workload count")
    names = set()
    total = 0
    for result in results:
        require(isinstance(result, dict), "Invalid workload object")
        name = result.get("name")
        require(
            isinstance(name, str)
            and re.fullmatch(r"[a-z0-9/-]{1,100}", name) is not None
            and name not in names,
            "Invalid or duplicate workload name",
        )
        names.add(name)
        fingerprint = result.get("workload_fingerprint")
        require(
            isinstance(fingerprint, str)
            and re.fullmatch(r"(?:v1:sha256:)?[0-9a-f]{64}", fingerprint) is not None,
            "Invalid workload fingerprint",
        )
        for field, minimum, maximum in (
            ("rule_count", 1, 1000),
            ("decisions_per_call", 0, 8),
            ("iterations", 1, 1000),
            ("repeats", 1, 20),
            ("warmup", 0, 1000),
        ):
            require(
                type(result.get(field)) is int and minimum <= result[field] <= maximum,
                f"Invalid workload {field}",
            )
        samples = result.get("samples_ns")
        summarize(samples)
        require(len(samples) == result["iterations"] * result["repeats"], "Invalid sample count")
        total += len(samples)
    require(total <= MAX_SAMPLES, "Total sample budget exceeded")


def compare(before: dict, after: dict, max_regression_percent: float) -> dict:
    validate_report(before)
    validate_report(after)
    require(
        type(max_regression_percent) in (int, float)
        and math.isfinite(max_regression_percent)
        and 0 <= max_regression_percent <= 1000,
        "Regression budget must be finite and 0..1000",
    )
    for field in ("report_version", "harness_sha256", "fixture_fingerprint", "environment"):
        require(field in before and before[field] == after.get(field), f"Incompatible {field}")
    old, new = before["results"], after["results"]
    require(len(old) == len(new), "Incompatible workload count")
    comparisons = []
    for baseline, candidate in zip(old, new, strict=True):
        for field in (
            "name",
            "rule_count",
            "decisions_per_call",
            "workload_fingerprint",
            "iterations",
            "repeats",
            "warmup",
        ):
            require(baseline[field] == candidate[field], f"Incompatible workload {field}")
        a, b = summarize(baseline["samples_ns"]), summarize(candidate["samples_ns"])
        change = (b["median_ns"] / a["median_ns"] - 1) * 100
        comparisons.append(
            {
                "name": baseline["name"],
                "median_change_percent": change,
                "within_budget": b["median_ns"] * 100
                <= a["median_ns"] * (100 + max_regression_percent),
            }
        )
    return {
        "comparison_version": 1,
        "max_regression_percent": max_regression_percent,
        "passed": all(r["within_budget"] for r in comparisons),
        "results": comparisons,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser(
        "run", help="Measure fixed local workloads; no real agent tools or network"
    )
    run.add_argument("--iterations", type=int, default=50)
    run.add_argument("--repeats", type=int, default=5)
    run.add_argument("--warmup", type=int, default=5)
    run.add_argument("--rules", type=int, nargs="+", default=[10, 100, 1000])
    run.add_argument("--max-seconds", type=float, default=60)
    run.add_argument("--output", type=Path, help="Create a new UTF-8 report; refuses overwrite")
    comparison = commands.add_parser(
        "compare", help="Compare compatible reports; exit 1 over budget"
    )
    comparison.add_argument("baseline", type=Path)
    comparison.add_argument("candidate", type=Path)
    comparison.add_argument("--max-regression-percent", type=float, default=20)
    args = parser.parse_args(argv)
    try:
        if args.command == "compare":
            result = compare(
                read_report(args.baseline), read_report(args.candidate), args.max_regression_percent
            )
            print(json.dumps(result, indent=2, allow_nan=False))
            return 0 if result["passed"] else 1
        if args.output is not None:
            require(not args.output.exists(), "Output exists; choose a new report path")
            require(args.output.parent.is_dir(), "Output parent directory does not exist")
        report = run_benchmarks(
            args.iterations, args.repeats, args.warmup, args.rules, args.max_seconds
        )
        payload = json.dumps(report, indent=2, allow_nan=False) + "\n"
        if args.output is None:
            print(payload, end="")
        else:
            with args.output.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(payload)
        return 0
    except (OSError, ValueError, TypeError, KeyError, RecursionError, SamsarixEthicsError) as error:
        print(f"Benchmark failed ({type(error).__name__}): {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
