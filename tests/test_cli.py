"""Command-level behavior and exit-code tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def _run_cli(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    source_path = str(Path(__file__).parents[1] / "src")
    environment["PYTHONPATH"] = source_path + os.pathsep + environment.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "samsarix_ethics", *args],
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )


def test_help_and_version() -> None:
    help_result = _run_cli("--help")
    version_result = _run_cli("--version")

    assert help_result.returncode == 0
    assert "check" in help_result.stdout
    assert "schema" in help_result.stdout
    assert "test" in help_result.stdout
    assert version_result.returncode == 0
    assert version_result.stdout.strip() == "samsarix-ethics 0.1.0"


def test_check_exit_codes_and_json(write_json: Any, policy_document: dict[str, Any]) -> None:
    policy_path = write_json("policy.json", policy_document)

    allowed = _run_cli(
        "check", "--policy", str(policy_path), stdin='{"action":{"operation":"read"}}'
    )
    denied = _run_cli(
        "check", "--policy", str(policy_path), stdin='{"action":{"operation":"delete"}}'
    )
    review = _run_cli(
        "check", "--policy", str(policy_path), stdin='{"action":{"operation":"write"}}'
    )

    assert allowed.returncode == 0
    assert json.loads(allowed.stdout)["outcome"] == "allow"
    assert denied.returncode == 3
    assert json.loads(denied.stdout)["outcome"] == "deny"
    assert review.returncode == 4
    assert json.loads(review.stdout)["outcome"] == "review"


def test_invalid_input_uses_stderr_and_error_exit(
    write_json: Any, policy_document: dict[str, Any]
) -> None:
    policy_path = write_json("policy.json", policy_document)

    result = _run_cli("check", "--policy", str(policy_path), stdin="not json")

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.startswith("error: input is not valid JSON")


def test_validate_and_init_commands(
    tmp_path: Path, write_json: Any, policy_document: dict[str, Any]
) -> None:
    policy_path = write_json("policy.json", policy_document)
    sample_path = tmp_path / "sample.json"

    validate = _run_cli("validate", str(policy_path), "--format", "json")
    initialize = _run_cli("init", str(sample_path))
    overwrite = _run_cli("init", str(sample_path))

    assert validate.returncode == 0
    assert json.loads(validate.stdout)["rule_count"] == 2
    assert initialize.returncode == 0
    assert sample_path.exists()
    assert overwrite.returncode == 2
    assert "refusing to overwrite" in overwrite.stderr


def test_text_output_and_audit_log(
    tmp_path: Path, write_json: Any, policy_document: dict[str, Any]
) -> None:
    policy_path = write_json("policy.json", policy_document)
    input_path = write_json("input.json", {"action": {"operation": "read"}})
    audit_path = tmp_path / "audit.jsonl"

    result = _run_cli(
        "check",
        "--policy",
        str(policy_path),
        "--input",
        str(input_path),
        "--format",
        "text",
        "--audit-log",
        str(audit_path),
    )

    assert result.returncode == 0
    assert "Outcome: ALLOW" in result.stdout
    assert "Reasons:" in result.stdout
    assert json.loads(audit_path.read_text(encoding="utf-8"))["outcome"] == "allow"


def test_schema_commands_emit_versioned_json() -> None:
    policy = _run_cli("schema")
    policy_tests = _run_cli("schema", "policy-test")
    tool_context = _run_cli("schema", "tool-context")

    assert policy.returncode == 0
    assert json.loads(policy.stdout)["$id"].endswith("/policy/v1.json")
    assert policy_tests.returncode == 0
    assert json.loads(policy_tests.stdout)["$id"].endswith("/policy-test/v1.json")
    assert tool_context.returncode == 0
    assert json.loads(tool_context.stdout)["$id"].endswith("/tool-context/v1.json")


def test_policy_test_command_reports_pass_and_fail(
    write_json: Any, policy_document: dict[str, Any]
) -> None:
    policy_path = write_json("policy.json", policy_document)
    passing_path = write_json(
        "passing.tests.json",
        {
            "schema_version": 1,
            "cases": [
                {
                    "name": "read is allowed",
                    "input": {"action": {"operation": "read"}},
                    "expected_outcome": "allow",
                    "expected_matched_rules": ["allow-read"],
                }
            ],
        },
    )
    failing_path = write_json(
        "failing.tests.json",
        {
            "schema_version": 1,
            "cases": [
                {
                    "name": "wrong expectation",
                    "input": {"action": {"operation": "read"}},
                    "expected_outcome": "deny",
                }
            ],
        },
    )

    passing = _run_cli("test", "--policy", str(policy_path), str(passing_path), "--format", "json")
    failing = _run_cli("test", "--policy", str(policy_path), str(failing_path))

    assert passing.returncode == 0
    assert json.loads(passing.stdout)["successful"] is True
    assert failing.returncode == 1
    assert "FAIL wrong expectation" in failing.stdout
    assert "1 failed" in failing.stdout
