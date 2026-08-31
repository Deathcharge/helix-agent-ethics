"""Measurement tooling must fail on wrong behavior, invalid evidence, or exhausted budgets."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from benchmarks import policy_gate as bench


@pytest.fixture(scope="module")
def report() -> dict[str, Any]:
    return bench.run_benchmarks(2, 2, 1, [1, 10], 30)


def test_real_workloads_check_outcomes_callbacks_audit_and_boundaries(
    report: dict[str, Any],
) -> None:
    bench.validate_report(report)
    assert len(report["results"]) == 12
    assert {r["name"] for r in report["results"]} >= {
        "coding/dispatch-read",
        "coding/dispatch-deny",
        "coding/dispatch-review",
        "coding/batch-read-8",
        "coding/batch-deny-8",
        "coding/jsonl-read",
        "coding/shadow-read",
    }
    assert all(len(r["samples_ns"]) == 4 for r in report["results"])
    payload = json.dumps(report)
    for private in (
        "benchmark-coding-agent",
        "README.md",
        "workspace_contained",
        str(bench.ROOT),
        json.dumps(str(bench.ROOT))[1:-1],
        bench.ROOT.as_posix(),
    ):
        assert private not in payload
    assert bench.compare(report, report, 0)["passed"]


def test_timing_samples_are_individual_calls_and_exclude_warmup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ticks = iter([0, 5, 5, 10, 10, 30, 30, 60, 60, 100, 100, 150])
    monkeypatch.setattr(bench.time, "perf_counter_ns", lambda: next(ticks))
    monkeypatch.setattr(bench.time, "monotonic", lambda: 0)
    calls = []
    workload = bench.Workload("test", 1, 1, "a" * 64, lambda: calls.append(1))
    result = bench.measure(workload, 2, 2, 2, 1)
    assert len(calls) == 6
    assert result["samples_ns"] == [20, 30, 40, 50]
    assert result["repeat_mean_ns"] == [25, 45]
    assert result["median_ns"] == 35
    assert result["p95_ns"] == result["p99_ns"] == 50


@pytest.mark.parametrize("ticks", [[2], [0, 2]])
def test_deadline_checked_before_and_after_operation(
    monkeypatch: pytest.MonkeyPatch, ticks: list[int]
) -> None:
    clock = iter(ticks)
    monkeypatch.setattr(bench.time, "monotonic", lambda: next(clock))
    workload = bench.Workload("test", 1, 1, "a" * 64, lambda: None)
    with pytest.raises(ValueError, match="time budget exhausted"):
        bench.measure(workload, 1, 1, 0, 1)


@pytest.mark.parametrize(
    "field,value",
    [
        ("iterations", 0),
        ("iterations", True),
        ("iterations", 1001),
        ("repeats", 0),
        ("repeats", 21),
        ("warmup", -1),
        ("warmup", 1001),
        ("rule_counts", []),
        ("rule_counts", [1, 1]),
        ("rule_counts", [0]),
        ("rule_counts", [1001]),
        ("rule_counts", [True]),
        ("seconds", float("nan")),
        ("seconds", float("inf")),
        ("seconds", 0),
        ("seconds", 601),
    ],
)
def test_invalid_run_options_do_not_construct_workloads(
    monkeypatch: pytest.MonkeyPatch, field: str, value: Any
) -> None:
    def unexpected(*_args: Any) -> None:
        pytest.fail("Invalid options reached workload construction")

    monkeypatch.setattr(bench, "coding_workloads", unexpected)
    options = dict(iterations=1, repeats=1, warmup=0, rule_counts=[1], seconds=10)
    options[field] = value
    with pytest.raises(ValueError):
        bench.run_benchmarks(**options)


@pytest.mark.parametrize(
    "iterations,repeats,rules,match",
    [
        (1000, 20, [1], "invocation budget"),
        (1000, 1, [1000, 999, 998, 997, 996], "rule-visit budget"),
    ],
)
def test_work_budget_rejects_before_measurement(
    monkeypatch: pytest.MonkeyPatch, iterations: int, repeats: int, rules: list[int], match: str
) -> None:
    monkeypatch.setattr(
        bench, "measure", lambda *_args: pytest.fail("Budget did not stop measurement")
    )
    with pytest.raises(ValueError, match=match):
        bench.run_benchmarks(iterations, repeats, 0, rules, 30)


@pytest.mark.parametrize(
    "field,value",
    [
        ("harness_sha256", "b" * 64),
        ("fixture_fingerprint", "b" * 64),
        ("environment", None),
        ("report_version", True),
        ("package_fingerprint", "not-a-digest"),
    ],
)
def test_incompatible_or_invalid_reports_rejected(report: dict, field: str, value: Any) -> None:
    altered = copy.deepcopy(report)
    altered[field] = value
    with pytest.raises(ValueError):
        bench.compare(report, altered, 20)


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", "other/workload"),
        ("rule_count", 999),
        ("iterations", 3),
        ("warmup", 2),
        ("decisions_per_call", 8),
        ("workload_fingerprint", "b" * 64),
        ("samples_ns", []),
        ("samples_ns", [True] * 4),
        ("samples_ns", [0] * 4),
        ("samples_ns", [-1] * 4),
        ("samples_ns", [1.5] * 4),
        ("samples_ns", [float("nan")] * 4),
        ("samples_ns", [10**18] * 4),
    ],
)
def test_wrong_workload_evidence_is_not_a_passing_comparison(
    report: dict, field: str, value: Any
) -> None:
    altered = copy.deepcopy(report)
    altered["results"][0][field] = value
    with pytest.raises(ValueError):
        bench.compare(report, altered, 20)


def test_environment_and_workload_omissions_rejected(report: dict) -> None:
    for change in ("environment", "missing", "duplicate", "version"):
        altered = copy.deepcopy(report)
        if change == "environment":
            altered["environment"]["python"] = "0.0.0"
        elif change == "missing":
            altered["results"].pop()
        elif change == "duplicate":
            altered["results"][1] = altered["results"][0]
        else:
            altered["report_version"] = 2
        with pytest.raises(ValueError):
            bench.compare(report, altered, 20)


def test_comparison_recomputes_from_samples_and_handles_exact_threshold(report: dict) -> None:
    baseline = copy.deepcopy(report)
    candidate = copy.deepcopy(report)
    for result in baseline["results"]:
        result["samples_ns"] = [100] * 4
    for result in candidate["results"]:
        result["samples_ns"] = [130] * 4
        result["median_ns"] = 1  # Untrusted summaries cannot hide a regression.
    assert bench.compare(baseline, candidate, 30)["passed"]
    assert not bench.compare(baseline, candidate, 29)["passed"]


@pytest.mark.parametrize("threshold", [True, -1, float("nan"), float("inf"), 1001])
def test_invalid_regression_budget(report: dict, threshold: Any) -> None:
    with pytest.raises(ValueError):
        bench.compare(report, report, threshold)


@pytest.mark.parametrize(
    "payload",
    [
        b'{"report_version":1,"report_version":1}',
        b'{"report_version":NaN}',
        b'{"report_version":1,"extra":Infinity}',
        b"[]",
        b"null",
        b'"text"',
        b"\xff",
        b"{" * 10000,
    ],
)
def test_malformed_report_has_clear_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture, payload: bytes
) -> None:
    target = tmp_path / "bad.json"
    target.write_bytes(payload)
    assert bench.main(["compare", str(target), str(target)]) == 2
    output = capsys.readouterr()
    assert output.out == "" and "Benchmark failed" in output.err


def test_report_byte_bound(tmp_path: Path) -> None:
    target = tmp_path / "oversized.json"
    target.write_bytes(b" " * (bench.MAX_REPORT_BYTES + 1))
    with pytest.raises(ValueError, match="byte budget"):
        bench.read_report(target)


def test_overflowing_json_float_is_rejected_even_in_extra_metadata(tmp_path: Path) -> None:
    target = tmp_path / "overflow.json"
    target.write_text('{"report_version":1,"extra":1e309}', encoding="utf-8")
    with pytest.raises(ValueError, match="Non-finite JSON"):
        bench.read_report(target)


def test_non_file_report_rejected_before_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "open", lambda *_args, **_kwargs: pytest.fail("Opened a non-file"))
    with pytest.raises(ValueError, match="regular file"):
        bench.read_report(tmp_path)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX named pipe contract")
def test_named_pipe_report_is_rejected_without_waiting_for_writer(tmp_path: Path) -> None:
    pipe = tmp_path / "pipe"
    os.mkfifo(pipe, 0o600)
    with pytest.raises(ValueError, match="regular file"):
        bench.read_report(pipe)


def test_existing_output_is_preserved_before_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "existing.json"
    target.write_text("preserve me", encoding="utf-8")
    monkeypatch.setattr(
        bench, "run_benchmarks", lambda *_args: pytest.fail("Existing output was ignored")
    )
    assert bench.main(["run", "--output", str(target)]) == 2
    assert target.read_text() == "preserve me"


def test_wrong_outcome_aborts_instead_of_recording_fast_sample(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workload = bench.synthetic_workloads([1])[0]
    original = bench.PolicyEngine.evaluate

    def deny(self: bench.PolicyEngine, _context: Any) -> Any:
        return original(self, {"action": {"operation": "absent"}})

    monkeypatch.setattr(bench.PolicyEngine, "evaluate", deny)
    with pytest.raises(ValueError, match="decision changed"):
        workload.run()


def test_cli_run_compare_and_regression_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    baseline, candidate = tmp_path / "baseline.json", tmp_path / "candidate.json"
    command = [sys.executable, "-m", "benchmarks.policy_gate"]
    result = subprocess.run(
        [
            *command,
            "run",
            "--iterations",
            "1",
            "--repeats",
            "1",
            "--warmup",
            "0",
            "--rules",
            "1",
            "--output",
            str(baseline),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        cwd=bench.ROOT,
    )
    assert result.returncode == 0 and result.stdout == "" and result.stderr == ""
    report = bench.read_report(baseline)
    for row in report["results"]:
        row["samples_ns"] = [row["samples_ns"][0] * 2]
    candidate.write_text(json.dumps(report), encoding="utf-8")
    result = subprocess.run(
        [*command, "compare", str(baseline), str(candidate)],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
        cwd=bench.ROOT,
    )
    assert result.returncode == 1 and result.stderr == ""
    assert json.loads(result.stdout)["passed"] is False


@pytest.mark.parametrize("batch", [False, True])
def test_forbidden_callback_is_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, batch: bool
) -> None:
    workloads, _, _ = bench.coding_workloads(tmp_path)
    if batch:
        original_batch = bench.ToolDispatcher.execute_many

        def unsafe_batch(self: Any, calls: Any) -> Any:
            original_batch(self, calls[:1])
            return original_batch(self, calls)

        monkeypatch.setattr(bench.ToolDispatcher, "execute_many", unsafe_batch)
        selected = "coding/batch-deny-8"
    else:
        original = bench.ToolDispatcher.execute

        def unsafe(self: Any, name: str, arguments: Any, **options: Any) -> Any:
            original(self, "read_file", arguments, **options)
            return original(self, name, arguments, **options)

        monkeypatch.setattr(bench.ToolDispatcher, "execute", unsafe)
        selected = "coding/dispatch-deny"
    with pytest.raises(ValueError, match="executed a callback"):
        next(w for w in workloads if w.name == selected).run()


def test_audit_loss_is_detected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from samsarix_ethics import JsonlAuditSink

    monkeypatch.setattr(JsonlAuditSink, "__call__", lambda *_args: None)
    workloads, verify, _ = bench.coding_workloads(tmp_path)
    next(w for w in workloads if w.name == "coding/jsonl-read").run()
    with pytest.raises(OSError):
        verify()


def test_exhausted_run_writes_no_report(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    output = tmp_path / "not-completed.json"
    assert (
        bench.main(["run", "--rules", "1", "--max-seconds", "1e-9", "--output", str(output)]) == 2
    )
    assert not output.exists()
    captured = capsys.readouterr()
    assert not captured.out and "time budget exhausted" in captured.err


def test_stdout_run_is_machine_readable(capsys: pytest.CaptureFixture) -> None:
    assert (
        bench.main(["run", "--iterations", "1", "--repeats", "1", "--warmup", "0", "--rules", "1"])
        == 0
    )
    output = capsys.readouterr()
    assert not output.err
    bench.validate_report(json.loads(output.out))


def test_report_creation_race_cannot_overwrite_winner(
    report: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "race.json"

    def concurrent_creator(*_args: Any) -> dict:
        target.write_text("other operator's report", encoding="utf-8")
        return report

    monkeypatch.setattr(bench, "run_benchmarks", concurrent_creator)
    assert bench.main(["run", "--output", str(target)]) == 2
    assert target.read_text() == "other operator's report"
