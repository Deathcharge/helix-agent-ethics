"""Command-level behavior and exit-code tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from copy import deepcopy
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
    assert "compare" in help_result.stdout
    assert "compose" in help_result.stdout
    assert "coverage" in help_result.stdout
    assert "explain" in help_result.stdout
    assert "lint" in help_result.stdout
    assert "lock" in help_result.stdout
    assert "schema" in help_result.stdout
    assert "shadow" in help_result.stdout
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
    allowed_decision = json.loads(allowed.stdout)
    assert allowed_decision["outcome"] == "allow"
    assert allowed_decision["policy_fingerprint"].startswith("v1:sha256:")
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
    validation = json.loads(validate.stdout)
    assert validation["rule_count"] == 2
    assert validation["policy_fingerprint"].startswith("v1:sha256:")
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
    assert "Policy fingerprint: v1:sha256:" in result.stdout
    assert "Reasons:" in result.stdout
    assert json.loads(audit_path.read_text(encoding="utf-8"))["outcome"] == "allow"


def test_schema_commands_emit_versioned_json() -> None:
    policy = _run_cli("schema")
    policy_tests = _run_cli("schema", "policy-test")
    policy_comparison = _run_cli("schema", "policy-comparison")
    policy_composition = _run_cli("schema", "policy-composition")
    policy_coverage = _run_cli("schema", "policy-coverage")
    policy_explanation = _run_cli("schema", "policy-explanation")
    policy_lint = _run_cli("schema", "policy-lint")
    policy_shadow = _run_cli("schema", "policy-shadow")
    context_contract = _run_cli("schema", "context-contract")
    deployment_lock = _run_cli("schema", "deployment-lock")
    tool_context = _run_cli("schema", "tool-context")
    tool_approval = _run_cli("schema", "tool-approval")
    audit_record = _run_cli("schema", "audit-record")

    assert policy.returncode == 0
    assert json.loads(policy.stdout)["$id"].endswith("/policy/v1.json")
    assert policy_tests.returncode == 0
    assert json.loads(policy_tests.stdout)["$id"].endswith("/policy-test/v1.json")
    assert policy_comparison.returncode == 0
    assert json.loads(policy_comparison.stdout)["$id"].endswith("/policy-comparison/v1.json")
    assert policy_composition.returncode == 0
    assert json.loads(policy_composition.stdout)["$id"].endswith("/policy-composition/v1.json")
    assert policy_coverage.returncode == 0
    assert json.loads(policy_coverage.stdout)["$id"].endswith("/policy-coverage/v1.json")
    assert policy_explanation.returncode == 0
    assert json.loads(policy_explanation.stdout)["$id"].endswith("/policy-explanation/v1.json")
    assert policy_lint.returncode == 0
    assert json.loads(policy_lint.stdout)["$id"].endswith("/policy-lint/v1.json")
    assert policy_shadow.returncode == 0
    assert json.loads(policy_shadow.stdout)["$id"].endswith("/policy-shadow/v1.json")
    assert context_contract.returncode == 0
    assert json.loads(context_contract.stdout)["$id"].endswith("/context-contract/v1.json")
    assert deployment_lock.returncode == 0
    assert json.loads(deployment_lock.stdout)["$id"].endswith("/deployment-lock/v1.json")
    assert tool_context.returncode == 0
    assert json.loads(tool_context.stdout)["$id"].endswith("/tool-context/v1.json")
    assert tool_approval.returncode == 0
    assert json.loads(tool_approval.stdout)["$id"].endswith("/tool-approval/v1.json")
    assert audit_record.returncode == 0
    assert json.loads(audit_record.stdout)["$id"].endswith("/audit-record/v1.json")


def test_deployment_lock_create_verify_and_enforce(
    tmp_path: Path, write_json: Any, policy_document: dict[str, Any]
) -> None:
    policy_path = write_json("locked-policy.json", policy_document)
    contract_path = write_json(
        "locked-contract.json",
        {
            "context_contract_version": 1,
            "id": "locked-context",
            "version": "1",
            "fields": {
                "action": {"type": "object"},
                "action.operation": {"type": "string"},
            },
        },
    )
    created = _run_cli(
        "lock",
        "create",
        "--policy",
        str(policy_path),
        "--context-contract",
        str(contract_path),
    )
    assert created.returncode == 0
    lock_document = json.loads(created.stdout)
    assert lock_document["deployment_lock_version"] == 1
    assert lock_document["policy"]["fingerprint"].startswith("v1:sha256:")
    assert lock_document["context_contract"]["id"] == "locked-context"
    lock_path = tmp_path / "deployment-lock.json"
    lock_path.write_text(created.stdout, encoding="utf-8")

    verified = _run_cli(
        "lock",
        "verify",
        str(lock_path),
        "--policy",
        str(policy_path),
        "--context-contract",
        str(contract_path),
    )
    validated = _run_cli(
        "validate",
        str(policy_path),
        "--context-contract",
        str(contract_path),
        "--deployment-lock",
        str(lock_path),
        "--format",
        "json",
    )
    checked = _run_cli(
        "check",
        "--policy",
        str(policy_path),
        "--context-contract",
        str(contract_path),
        "--deployment-lock",
        str(lock_path),
        stdin='{"action":{"operation":"read"}}',
    )
    explained = _run_cli(
        "explain",
        "--policy",
        str(policy_path),
        "--context-contract",
        str(contract_path),
        "--deployment-lock",
        str(lock_path),
        stdin='{"action":{"operation":"read"}}',
    )

    assert verified.returncode == 0
    assert "Verified deployment lock" in verified.stdout
    assert validated.returncode == 0
    assert json.loads(validated.stdout)["deployment_lock_verified"] is True
    assert checked.returncode == 0
    assert explained.returncode == 0
    assert (
        json.loads(explained.stdout)["context_contract_fingerprint"]
        == lock_document["context_contract"]["fingerprint"]
    )

    changed_policy = deepcopy(policy_document)
    changed_policy["description"] = "unreviewed mutation"
    changed_policy_path = write_json("changed-policy.json", changed_policy)
    mismatch = _run_cli(
        "lock",
        "verify",
        str(lock_path),
        "--policy",
        str(changed_policy_path),
        "--context-contract",
        str(contract_path),
    )
    omitted_contract = _run_cli(
        "validate",
        str(policy_path),
        "--deployment-lock",
        str(lock_path),
    )

    assert mismatch.returncode == 2
    assert "deployment lock does not match the policy" in mismatch.stderr
    assert omitted_contract.returncode == 2
    assert "context-contract presence does not match" in omitted_contract.stderr


def test_explain_command_is_value_minimized_and_uses_decision_exit_codes(
    write_json: Any, policy_document: dict[str, Any]
) -> None:
    policy_document["rules"][1]["conditions"].append(
        {"field": "action.secret", "operator": "eq", "value": "policy-secret"}
    )
    policy_path = write_json("explain-policy.json", policy_document)

    allowed = _run_cli(
        "explain",
        "--policy",
        str(policy_path),
        stdin='{"action":{"operation":"read","secret":"policy-secret"}}',
    )
    denied_text = _run_cli(
        "explain",
        "--policy",
        str(policy_path),
        "--format",
        "text",
        stdin='{"action":{"operation":"delete","secret":"private-input"}}',
    )

    assert allowed.returncode == 0
    document = json.loads(allowed.stdout)
    assert document["outcome"] == "allow"
    assert document["decisive_rule_ids"] == ["allow-read"]
    assert document["rules"][1]["conditions"][0]["status"] == "matched"
    assert "policy-secret" not in allowed.stdout
    assert denied_text.returncode == 3
    assert "Outcome: DENY" in denied_text.stdout
    assert "[NOT_EVALUATED] #1 action.secret eq" in denied_text.stdout
    assert "private-input" not in denied_text.stdout


def test_context_contract_validates_policy_and_live_input(
    write_json: Any, policy_document: dict[str, Any]
) -> None:
    policy_path = write_json("contract-policy.json", policy_document)
    contract_path = write_json(
        "context-contract.json",
        {
            "context_contract_version": 1,
            "id": "cli-context",
            "version": "1",
            "fields": {
                "action": {"type": "object"},
                "action.operation": {"type": "string"},
            },
        },
    )

    validated = _run_cli(
        "validate",
        str(policy_path),
        "--context-contract",
        str(contract_path),
        "--format",
        "json",
    )
    allowed = _run_cli(
        "check",
        "--policy",
        str(policy_path),
        "--context-contract",
        str(contract_path),
        stdin='{"action":{"operation":"read"},"extra":"accepted"}',
    )
    mistyped = _run_cli(
        "check",
        "--policy",
        str(policy_path),
        "--context-contract",
        str(contract_path),
        stdin='{"action":{"operation":1}}',
    )

    assert validated.returncode == 0
    assert json.loads(validated.stdout)["context_contract"] == {
        "format_version": 1,
        "id": "cli-context",
        "version": "1",
    }
    assert allowed.returncode == 0
    assert mistyped.returncode == 2
    assert "'action.operation' must have type 'string'" in mistyped.stderr


def test_context_contract_rejects_policy_typo_before_cli_evaluation(
    write_json: Any, policy_document: dict[str, Any]
) -> None:
    policy_document["rules"][1]["conditions"][0]["field"] = "action.operaton"
    policy_path = write_json("typo-policy.json", policy_document)
    contract_path = write_json(
        "typo-contract.json",
        {
            "context_contract_version": 1,
            "id": "cli-context",
            "version": "1",
            "fields": {
                "action": {"type": "object"},
                "action.operation": {"type": "string"},
            },
        },
    )

    result = _run_cli("validate", str(policy_path), "--context-contract", str(contract_path))

    assert result.returncode == 2
    assert "field 'action.operaton' is not declared" in result.stderr


def test_context_contract_is_shared_by_cli_lifecycle_workflows(
    write_json: Any, policy_document: dict[str, Any]
) -> None:
    policy_path = write_json("lifecycle-policy.json", policy_document)
    contract_path = write_json(
        "lifecycle-contract.json",
        {
            "context_contract_version": 1,
            "id": "lifecycle-context",
            "version": "1",
            "fields": {
                "action": {"type": "object"},
                "action.operation": {"type": "string"},
            },
        },
    )
    suite_path = write_json(
        "lifecycle.tests.json",
        {
            "schema_version": 1,
            "cases": [
                {
                    "name": "read",
                    "input": {"action": {"operation": "read"}},
                    "expected_outcome": "allow",
                }
            ],
        },
    )
    contract_arguments = ("--context-contract", str(contract_path))

    tested = _run_cli("test", "--policy", str(policy_path), *contract_arguments, str(suite_path))
    covered = _run_cli(
        "coverage", "--policy", str(policy_path), *contract_arguments, str(suite_path)
    )
    compared = _run_cli(
        "compare",
        "--baseline",
        str(policy_path),
        "--candidate",
        str(policy_path),
        *contract_arguments,
        str(suite_path),
    )
    shadowed = _run_cli(
        "shadow",
        "--baseline",
        str(policy_path),
        "--candidate",
        str(policy_path),
        *contract_arguments,
        stdin='{"action":{"operation":"read"}}',
    )

    assert tested.returncode == 0
    assert covered.returncode == 0
    assert compared.returncode == 0
    assert shadowed.returncode == 0


def test_context_contract_input_errors_fail_lifecycle_workflows_closed(
    write_json: Any, policy_document: dict[str, Any]
) -> None:
    policy_path = write_json("invalid-lifecycle-policy.json", policy_document)
    contract_path = write_json(
        "invalid-lifecycle-contract.json",
        {
            "context_contract_version": 1,
            "id": "lifecycle-context",
            "version": "1",
            "fields": {
                "action": {"type": "object"},
                "action.operation": {"type": "string"},
            },
        },
    )
    suite_path = write_json(
        "invalid-lifecycle.tests.json",
        {
            "schema_version": 1,
            "cases": [
                {
                    "name": "missing operation",
                    "input": {"action": {}},
                    "expected_outcome": "review",
                }
            ],
        },
    )

    tested = _run_cli(
        "test",
        "--policy",
        str(policy_path),
        "--context-contract",
        str(contract_path),
        str(suite_path),
    )
    shadowed = _run_cli(
        "shadow",
        "--baseline",
        str(policy_path),
        "--candidate",
        str(policy_path),
        "--context-contract",
        str(contract_path),
        stdin='{"action":{}}',
    )

    assert tested.returncode == 1
    assert "missing required contract field" in tested.stdout
    assert shadowed.returncode == 2
    assert "missing required contract field" in shadowed.stderr


def test_compose_command_writes_reusable_policy_and_requires_explicit_overwrite(
    tmp_path: Path, write_json: Any, policy_document: dict[str, Any]
) -> None:
    guardrails = deepcopy(policy_document)
    guardrails["id"] = "guardrails"
    guardrails["default_effect"] = "deny"
    guardrails["rules"] = [guardrails["rules"][0]]
    permissions = deepcopy(policy_document)
    permissions["id"] = "permissions"
    permissions["default_effect"] = "deny"
    permissions["rules"] = [permissions["rules"][1]]
    guardrails_path = write_json("guardrails.json", guardrails)
    permissions_path = write_json("permissions.json", permissions)
    output_path = tmp_path / "composed.json"
    arguments = (
        "compose",
        "--id",
        "composed",
        "--version",
        "1",
        "--description",
        "Layered policy.",
        "--policy",
        str(guardrails_path),
        "--policy",
        str(permissions_path),
        "--output",
        str(output_path),
    )

    composed = _run_cli(*arguments, "--format", "json")
    overwrite = _run_cli(*arguments)
    forced = _run_cli(*arguments, "--force")
    checked = _run_cli(
        "check", "--policy", str(output_path), stdin='{"action":{"operation":"read"}}'
    )

    assert composed.returncode == 0
    report = json.loads(composed.stdout)
    assert report["composition_version"] == 1
    assert report["source_count"] == 2
    assert report["total_rules"] == 2
    assert "Layered policy" not in composed.stdout
    assert [rule["id"] for rule in json.loads(output_path.read_text())["rules"]] == [
        "deny-delete",
        "allow-read",
    ]
    assert overwrite.returncode == 2
    assert "refusing to overwrite" in overwrite.stderr
    assert forced.returncode == 0
    assert "Rules: 2 from 2 sources" in forced.stdout
    assert checked.returncode == 0


def test_compose_command_bounds_sources_before_reading_files(tmp_path: Path) -> None:
    arguments = ["compose", "--id", "bounded", "--version", "1"]
    for index in range(33):
        arguments.extend(["--policy", str(tmp_path / f"missing-{index}.json")])
    arguments.extend(["--output", str(tmp_path / "composed.json")])

    result = _run_cli(*arguments)

    assert result.returncode == 2
    assert "exceeds the limit of 32 sources" in result.stderr
    assert "cannot read policy" not in result.stderr


def test_lint_command_reports_findings_and_enforces_explicit_severity(
    write_json: Any, policy_document: dict[str, Any]
) -> None:
    clean_path = write_json("clean-lint-policy.json", policy_document)
    dangerous_path = write_json(
        "dangerous-lint-policy.json",
        {
            "schema_version": 1,
            "id": "dangerous",
            "version": "1",
            "default_effect": "allow",
            "rules": [
                {
                    "id": "allow-everything",
                    "effect": "allow",
                    "message": "This is intentionally unconditional for the diagnostic.",
                    "conditions": [],
                }
            ],
        },
    )
    suggestion_document = deepcopy(policy_document)
    suggestion_document["rules"][0]["message"] = ""
    suggestion_path = write_json("suggestion-lint-policy.json", suggestion_document)

    clean = _run_cli("lint", str(clean_path))
    dangerous = _run_cli("lint", str(dangerous_path), "--format", "json")
    report_only = _run_cli("lint", str(dangerous_path), "--fail-on", "none")
    suggestion_default = _run_cli("lint", str(suggestion_path))
    suggestion_strict = _run_cli("lint", str(suggestion_path), "--fail-on", "suggestion")

    assert clean.returncode == 0
    assert "No findings." in clean.stdout
    assert dangerous.returncode == 1
    payload = json.loads(dangerous.stdout)
    assert [finding["code"] for finding in payload["findings"]] == ["SAE001", "SAE002"]
    assert payload["security_warnings"] == 2
    assert payload["blocking_findings"] == 2
    assert payload["passed"] is False
    assert report_only.returncode == 0
    assert "Summary: passed" in report_only.stdout
    assert suggestion_default.returncode == 0
    assert "SUGGESTION SAE202 rule deny-delete" in suggestion_default.stdout
    assert suggestion_strict.returncode == 1
    assert "Summary: FAILED" in suggestion_strict.stdout


def test_coverage_command_reports_uncovered_rules_and_enforces_threshold(
    write_json: Any, policy_document: dict[str, Any]
) -> None:
    policy_path = write_json("coverage-policy.json", policy_document)
    suite_path = write_json(
        "coverage.tests.json",
        {
            "schema_version": 1,
            "name": "coverage",
            "cases": [
                {
                    "name": "read only",
                    "input": {
                        "action": {"operation": "read"},
                        "secret": "never-print-coverage-input",
                    },
                    "expected_outcome": "allow",
                }
            ],
        },
    )

    passing = _run_cli(
        "coverage",
        "--policy",
        str(policy_path),
        str(suite_path),
        "--threshold",
        "50",
        "--format",
        "json",
    )
    default_threshold = _run_cli(
        "coverage",
        "--policy",
        str(policy_path),
        str(suite_path),
        "--format",
        "json",
    )
    failing = _run_cli(
        "coverage",
        "--policy",
        str(policy_path),
        str(suite_path),
        "--threshold",
        "100",
    )
    invalid = _run_cli(
        "coverage",
        "--policy",
        str(policy_path),
        str(suite_path),
        "--threshold",
        "101",
    )
    non_integer = _run_cli(
        "coverage",
        "--policy",
        str(policy_path),
        str(suite_path),
        "--threshold",
        "not-a-number",
    )

    assert passing.returncode == 0
    payload = json.loads(passing.stdout)
    assert payload["coverage_percent"] == 50.0
    assert payload["threshold_met"] is True
    assert payload["covered_rule_ids"] == ["allow-read"]
    assert payload["uncovered_rule_ids"] == ["deny-delete"]
    assert "never-print-coverage-input" not in passing.stdout
    assert default_threshold.returncode == 0
    assert json.loads(default_threshold.stdout)["required_coverage_percent"] == 0
    assert failing.returncode == 1
    assert "Rules: 1/2 covered (50.00%; required 100%)" in failing.stdout
    assert "  - deny-delete" in failing.stdout
    assert "threshold NOT MET" in failing.stdout
    assert invalid.returncode == 2
    assert "must be an integer from 0 to 100" in invalid.stderr
    assert non_integer.returncode == 2
    assert "must be an integer from 0 to 100" in non_integer.stderr


def test_coverage_command_errors_fail_closed_without_inputs(
    write_json: Any,
) -> None:
    policy_path = write_json(
        "coverage-error-policy.json",
        {
            "schema_version": 1,
            "id": "coverage-errors",
            "version": "1",
            "default_effect": "deny",
            "rules": [
                {
                    "id": "array-only",
                    "effect": "allow",
                    "conditions": [{"field": "roles", "operator": "contains", "value": "admin"}],
                }
            ],
        },
    )
    suite_path = write_json(
        "coverage-errors.tests.json",
        {
            "schema_version": 1,
            "cases": [
                {
                    "name": "wrong shape",
                    "input": {"roles": "never-print-this-value"},
                    "expected_outcome": "deny",
                }
            ],
        },
    )

    result = _run_cli("coverage", "--policy", str(policy_path), str(suite_path))

    assert result.returncode == 1
    assert "Errors:" in result.stdout
    assert "wrong shape: rule 'array-only' failed" in result.stdout
    assert "threshold NOT MET" in result.stdout
    assert "never-print-this-value" not in result.stdout


def test_compare_command_reports_impact_and_uses_ci_exit_code(
    write_json: Any, policy_document: dict[str, Any]
) -> None:
    baseline_path = write_json("baseline.json", policy_document)
    candidate_document = deepcopy(policy_document)
    candidate_document["version"] = "2"
    candidate_document["rules"].extend(
        [
            {
                "id": "deny-read",
                "effect": "deny",
                "conditions": [{"field": "action.operation", "operator": "eq", "value": "read"}],
            },
            {
                "id": "warn-write",
                "effect": "warn",
                "conditions": [{"field": "action.operation", "operator": "eq", "value": "write"}],
            },
        ]
    )
    candidate_path = write_json("candidate.json", candidate_document)
    suite_path = write_json(
        "impact.tests.json",
        {
            "schema_version": 1,
            "name": "impact",
            "cases": [
                {
                    "name": "read authorization",
                    "input": {
                        "action": {"operation": "read"},
                        "secret": "never-print-this",
                    },
                    "expected_outcome": "allow",
                },
                {
                    "name": "write metadata",
                    "input": {"action": {"operation": "write"}},
                    "expected_outcome": "review",
                },
            ],
        },
    )

    identical = _run_cli(
        "compare",
        "--baseline",
        str(baseline_path),
        "--candidate",
        str(baseline_path),
        str(suite_path),
        "--format",
        "json",
    )
    changed = _run_cli(
        "compare",
        "--baseline",
        str(baseline_path),
        "--candidate",
        str(candidate_path),
        str(suite_path),
        "--format",
        "json",
    )
    text_result = _run_cli(
        "compare",
        "--baseline",
        str(baseline_path),
        "--candidate",
        str(candidate_path),
        str(suite_path),
    )

    assert identical.returncode == 0
    assert json.loads(identical.stdout)["identical"] is True
    assert changed.returncode == 1
    changed_payload = json.loads(changed.stdout)
    assert changed_payload["authorization_changes"] == 1
    assert changed_payload["metadata_only_changes"] == 1
    assert changed_payload["results"][0]["changes"] == [
        "outcome",
        "matched_rules",
        "reason_messages",
    ]
    assert "never-print-this" not in changed.stdout
    assert text_result.returncode == 1
    assert "CHANGED read authorization: outcome allow -> deny" in text_result.stdout
    assert "reason messages changed" in text_result.stdout
    assert "CHANGED write metadata: matched rules changed; warnings 0 -> 1" in text_result.stdout
    assert "warning messages changed" in text_result.stdout
    assert "1 authorization" in text_result.stdout


def test_compare_command_reports_evaluation_errors_without_inputs(
    write_json: Any, policy_document: dict[str, Any]
) -> None:
    baseline_path = write_json(
        "error-baseline.json",
        {
            "schema_version": 1,
            "id": "error-policy",
            "version": "1",
            "default_effect": "deny",
            "rules": [
                {
                    "id": "array-only",
                    "effect": "allow",
                    "conditions": [{"field": "roles", "operator": "contains", "value": "admin"}],
                }
            ],
        },
    )
    candidate_path = write_json("safe-candidate.json", policy_document)
    suite_path = write_json(
        "error-impact.tests.json",
        {
            "schema_version": 1,
            "cases": [
                {
                    "name": "bad shape",
                    "input": {"roles": "do-not-report-this"},
                    "expected_outcome": "deny",
                }
            ],
        },
    )

    result = _run_cli(
        "compare",
        "--baseline",
        str(baseline_path),
        "--candidate",
        str(candidate_path),
        str(suite_path),
    )

    assert result.returncode == 1
    assert "ERROR bad shape: baseline error:" in result.stdout
    assert "requires the input field to be an array" in result.stdout
    assert "do-not-report-this" not in result.stdout


def test_shadow_command_keeps_baseline_exit_authoritative_and_omits_input(
    write_json: Any, policy_document: dict[str, Any]
) -> None:
    baseline_path = write_json("shadow-baseline.json", policy_document)
    candidate_document = deepcopy(policy_document)
    candidate_document["version"] = "2-candidate"
    candidate_document["rules"].append(
        {
            "id": "review-read",
            "effect": "review",
            "message": "Candidate review text must not be serialized.",
            "conditions": [{"field": "action.operation", "operator": "eq", "value": "read"}],
        }
    )
    candidate_path = write_json("shadow-candidate.json", candidate_document)

    changed = _run_cli(
        "shadow",
        "--baseline",
        str(baseline_path),
        "--candidate",
        str(candidate_path),
        stdin='{"action":{"operation":"read"},"secret":"never-print-shadow-input"}',
    )
    denied = _run_cli(
        "shadow",
        "--baseline",
        str(baseline_path),
        "--candidate",
        str(candidate_path),
        stdin='{"action":{"operation":"delete"}}',
    )
    review = _run_cli(
        "shadow",
        "--baseline",
        str(baseline_path),
        "--candidate",
        str(candidate_path),
        stdin='{"action":{"operation":"write"}}',
    )
    text_result = _run_cli(
        "shadow",
        "--baseline",
        str(baseline_path),
        "--candidate",
        str(candidate_path),
        "--format",
        "text",
        stdin='{"action":{"operation":"read"}}',
    )

    assert changed.returncode == 0
    payload = json.loads(changed.stdout)
    assert payload["status"] == "changed"
    assert payload["authorization_changed"] is True
    assert payload["authoritative"]["outcome"] == "allow"
    assert payload["candidate"]["outcome"] == "review"
    assert payload["authoritative"]["evaluation_duration_ns"] >= 0
    assert payload["candidate"]["evaluation_duration_ns"] >= 0
    assert "never-print-shadow-input" not in changed.stdout
    assert "Candidate review text" not in changed.stdout
    assert denied.returncode == 3
    assert json.loads(denied.stdout)["authoritative"]["outcome"] == "deny"
    assert review.returncode == 4
    assert json.loads(review.stdout)["authoritative"]["outcome"] == "review"
    assert text_result.returncode == 0
    assert "Authoritative:" in text_result.stdout
    assert "-> ALLOW" in text_result.stdout
    assert "Candidate observation: REVIEW" in text_result.stdout
    assert "Enforce: authoritative baseline decision" in text_result.stdout


def test_shadow_command_candidate_error_does_not_override_baseline_allow(
    write_json: Any, policy_document: dict[str, Any]
) -> None:
    baseline_path = write_json("safe-shadow-baseline.json", policy_document)
    candidate_path = write_json(
        "error-shadow-candidate.json",
        {
            "schema_version": 1,
            "id": "error-shadow-candidate",
            "version": "2",
            "default_effect": "deny",
            "rules": [
                {
                    "id": "array-only",
                    "effect": "allow",
                    "conditions": [
                        {"field": "action.operation", "operator": "contains", "value": "read"}
                    ],
                }
            ],
        },
    )

    result = _run_cli(
        "shadow",
        "--baseline",
        str(baseline_path),
        "--candidate",
        str(candidate_path),
        stdin='{"action":{"operation":"read"},"secret":"candidate-error-secret"}',
    )
    text_result = _run_cli(
        "shadow",
        "--baseline",
        str(baseline_path),
        "--candidate",
        str(candidate_path),
        "--format",
        "text",
        stdin='{"action":{"operation":"read"}}',
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    assert payload["authoritative"]["outcome"] == "allow"
    assert payload["candidate"]["outcome"] is None
    assert "requires the input field to be an array" in payload["candidate"]["error"]
    assert "candidate-error-secret" not in result.stdout
    assert text_result.returncode == 0
    assert "Candidate error after" in text_result.stdout
    assert "Shadow status: ERROR; changes: none" in text_result.stdout


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
