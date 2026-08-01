# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Command-line interface for policy validation and action checks."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import BinaryIO, TextIO

from . import __version__
from .engine import PolicyEngine
from .errors import SamsarixEthicsError
from .io import append_audit_record, load_context, load_policy, write_sample_policy
from .models import Decision, Outcome
from .provenance import fingerprint_policy
from .schema import (
    get_audit_record_schema,
    get_policy_schema,
    get_policy_test_schema,
    get_tool_approval_schema,
    get_tool_context_schema,
)
from .testing import PolicyTestReport, load_policy_test_suite, run_policy_tests

EXIT_ALLOWED = 0
EXIT_TEST_FAILED = 1
EXIT_ERROR = 2
EXIT_DENIED = 3
EXIT_REVIEW = 4


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="samsarix-ethics",
        description="Evaluate agent actions against local, explicit JSON policies.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="evaluate one JSON action context")
    check.add_argument("--policy", required=True, help="path to a JSON policy")
    check.add_argument(
        "--input", default="-", help="path to a JSON input object; default: standard input"
    )
    check.add_argument("--audit-log", help="append metadata-only JSONL to this path")
    check.add_argument("--format", choices=("json", "text"), default="json")

    validate = subparsers.add_parser(
        "validate", help="validate a JSON policy without evaluating it"
    )
    validate.add_argument("policy", help="path to a JSON policy")
    validate.add_argument("--format", choices=("json", "text"), default="text")

    test_suite = subparsers.add_parser("test", help="run a JSON policy regression suite")
    test_suite.add_argument("--policy", required=True, help="path to a JSON policy")
    test_suite.add_argument("suite", help="path to a JSON policy-test suite")
    test_suite.add_argument("--format", choices=("json", "text"), default="text")

    schema = subparsers.add_parser("schema", help="print a bundled JSON Schema")
    schema.add_argument(
        "kind",
        nargs="?",
        choices=("policy", "policy-test", "tool-context", "tool-approval", "audit-record"),
        default="policy",
        help="schema to print; default: policy",
    )

    initialize = subparsers.add_parser("init", help="write a documented sample policy")
    initialize.add_argument("path", help="output path for the sample JSON policy")
    initialize.add_argument(
        "--force", action="store_true", help="explicitly replace an existing file"
    )
    return parser


def _render_decision(decision: Decision, output_format: str) -> str:
    if output_format == "json":
        return json.dumps(decision.to_dict(), indent=2, sort_keys=True)
    lines = [
        f"Outcome: {decision.outcome.value.upper()}",
        f"Allowed: {'yes' if decision.allowed else 'no'}",
        f"Decision ID: {decision.decision_id}",
        f"Policy: {decision.policy_id}@{decision.policy_version}",
        f"Policy fingerprint: {decision.policy_fingerprint}",
        "Reasons:",
    ]
    lines.extend(f"  - {reason}" for reason in decision.reasons)
    if decision.warnings:
        lines.append("Warnings:")
        lines.extend(f"  - {warning}" for warning in decision.warnings)
    return "\n".join(lines)


def _decision_exit(outcome: Outcome) -> int:
    return {
        Outcome.ALLOW: EXIT_ALLOWED,
        Outcome.DENY: EXIT_DENIED,
        Outcome.REVIEW: EXIT_REVIEW,
    }[outcome]


def _render_test_report(report: PolicyTestReport, output_format: str) -> str:
    if output_format == "json":
        return json.dumps(report.to_dict(), indent=2, sort_keys=True)
    lines: list[str] = []
    for result in report.results:
        detail = "; ".join(result.failures) if result.failures else result.error
        suffix = f": {detail}" if detail else ""
        lines.append(f"{result.status.value.upper()} {result.name}{suffix}")
    lines.append(
        f"Summary: {report.passed} passed, {report.failed} failed, "
        f"{report.errors} errors, {len(report.results)} total"
    )
    return "\n".join(lines)


def main(
    argv: Sequence[str] | None = None,
    *,
    stdin: BinaryIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Run the CLI and return a process exit code."""

    arguments = _parser().parse_args(argv)
    output = stdout or sys.stdout
    errors = stderr or sys.stderr
    binary_input = stdin if stdin is not None else sys.stdin.buffer

    try:
        if arguments.command == "init":
            target = write_sample_policy(arguments.path, force=arguments.force)
            print(f"Wrote sample policy: {target}", file=output)
            return EXIT_ALLOWED

        if arguments.command == "schema":
            schema_loaders = {
                "policy": get_policy_schema,
                "policy-test": get_policy_test_schema,
                "tool-context": get_tool_context_schema,
                "tool-approval": get_tool_approval_schema,
                "audit-record": get_audit_record_schema,
            }
            schema = schema_loaders[arguments.kind]()
            print(json.dumps(schema, indent=2, sort_keys=True), file=output)
            return EXIT_ALLOWED

        policy = load_policy(arguments.policy)
        if arguments.command == "validate":
            policy_fingerprint = fingerprint_policy(policy)
            result = {
                "valid": True,
                "policy_id": policy.id,
                "policy_version": policy.version,
                "policy_fingerprint": policy_fingerprint,
                "default_effect": policy.default_effect.value,
                "rule_count": len(policy.rules),
            }
            if arguments.format == "json":
                print(json.dumps(result, indent=2, sort_keys=True), file=output)
            else:
                print(
                    f"Valid policy {policy.id}@{policy.version}: "
                    f"{len(policy.rules)} rules, default={policy.default_effect.value}, "
                    f"fingerprint={policy_fingerprint}",
                    file=output,
                )
            return EXIT_ALLOWED

        if arguments.command == "test":
            suite = load_policy_test_suite(arguments.suite)
            report = run_policy_tests(policy, suite)
            print(_render_test_report(report, arguments.format), file=output)
            return EXIT_ALLOWED if report.successful else EXIT_TEST_FAILED

        context = load_context(arguments.input, stdin=binary_input)
        decision = PolicyEngine(policy).evaluate(context)
        if arguments.audit_log:
            append_audit_record(Path(arguments.audit_log), decision)
        print(_render_decision(decision, arguments.format), file=output)
        return _decision_exit(decision.outcome)
    except SamsarixEthicsError as exc:
        print(f"error: {exc}", file=errors)
        return EXIT_ERROR


def entrypoint() -> None:
    """Console-script entry point."""

    raise SystemExit(main())
