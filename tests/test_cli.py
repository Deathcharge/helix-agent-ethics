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
        [sys.executable, "-m", "helix_ethics", *args],
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
    assert version_result.returncode == 0
    assert version_result.stdout.strip() == "helix-ethics 0.1.0"


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
