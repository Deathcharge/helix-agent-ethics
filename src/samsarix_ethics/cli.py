# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Command-line interface for policy authoring, testing, and action checks."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, BinaryIO, TextIO

from . import __version__
from .comparison import (
    PolicyComparisonChange,
    PolicyComparisonReport,
    PolicyComparisonStatus,
    compare_policies,
)
from .composition import MAX_COMPOSED_POLICIES, PolicyComposition, compose_policies
from .contracts import ContextContract
from .coverage import PolicyCoverageReport, measure_policy_coverage
from .deployment import DeploymentLock, create_deployment_lock, verify_deployment_lock
from .diagnostics import PolicyLintReport, PolicyLintSeverity, lint_policy
from .engine import PolicyEngine
from .errors import InputValidationError, PolicyCompositionError, SamsarixEthicsError
from .explanation import PolicyExplanation
from .io import (
    append_audit_record,
    load_context,
    load_context_contract,
    load_deployment_lock,
    load_policy,
    load_policy_deployment,
    load_tool_catalog,
    write_policy,
    write_policy_deployment,
    write_sample_policy,
)
from .models import Decision, Outcome
from .policy_deployment import PolicyDeployment, create_policy_deployment
from .provenance import fingerprint_policy, fingerprint_tool_catalog
from .schema import (
    get_audit_record_schema,
    get_context_contract_schema,
    get_deployment_lock_schema,
    get_policy_comparison_schema,
    get_policy_composition_schema,
    get_policy_coverage_schema,
    get_policy_deployment_schema,
    get_policy_explanation_schema,
    get_policy_lint_schema,
    get_policy_runtime_status_schema,
    get_policy_schema,
    get_policy_shadow_schema,
    get_policy_test_schema,
    get_tool_approval_schema,
    get_tool_catalog_schema,
    get_tool_context_schema,
)
from .shadow import PolicyShadowEvaluation, PolicyShadowEvaluator
from .testing import PolicyTestReport, load_policy_test_suite, run_policy_tests

EXIT_ALLOWED = 0
EXIT_TEST_FAILED = 1
EXIT_ERROR = 2
EXIT_DENIED = 3
EXIT_REVIEW = 4


def _coverage_threshold(value: str) -> int:
    try:
        threshold = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer from 0 to 100") from exc
    if not 0 <= threshold <= 100:
        raise argparse.ArgumentTypeError("must be an integer from 0 to 100")
    return threshold


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="samsarix-ethics",
        description="Evaluate agent actions against local, explicit JSON policies.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="evaluate one JSON action context")
    check_source = check.add_mutually_exclusive_group(required=True)
    check_source.add_argument("--policy", help="path to a JSON policy")
    check_source.add_argument(
        "--deployment", help="path to a verified single-file policy deployment"
    )
    check.add_argument(
        "--context-contract", help="validate policy and input against this application contract"
    )
    check.add_argument(
        "--deployment-lock", help="require the policy and contract to match this exact lock"
    )
    check.add_argument(
        "--input", default="-", help="path to a JSON input object; default: standard input"
    )
    check.add_argument("--audit-log", help="append metadata-only JSONL to this path")
    check.add_argument("--format", choices=("json", "text"), default="json")

    explain = subparsers.add_parser(
        "explain", help="show value-minimized rule and condition evaluation status"
    )
    explain_source = explain.add_mutually_exclusive_group(required=True)
    explain_source.add_argument("--policy", help="path to a JSON policy")
    explain_source.add_argument(
        "--deployment", help="path to a verified single-file policy deployment"
    )
    explain.add_argument(
        "--context-contract", help="validate policy and input against this application contract"
    )
    explain.add_argument(
        "--deployment-lock", help="require the policy and contract to match this exact lock"
    )
    explain.add_argument(
        "--input", default="-", help="path to a JSON input object; default: standard input"
    )
    explain.add_argument("--format", choices=("json", "text"), default="json")

    validate = subparsers.add_parser(
        "validate", help="validate a JSON policy without evaluating it"
    )
    validate.add_argument("policy", help="path to a JSON policy")
    validate.add_argument(
        "--context-contract", help="validate policy references against this application contract"
    )
    validate.add_argument(
        "--deployment-lock", help="require the policy and contract to match this exact lock"
    )
    validate.add_argument("--format", choices=("json", "text"), default="text")

    test_suite = subparsers.add_parser("test", help="run a JSON policy regression suite")
    test_suite.add_argument("--policy", required=True, help="path to a JSON policy")
    test_suite.add_argument(
        "--context-contract", help="validate the policy and suite inputs against this contract"
    )
    test_suite.add_argument("suite", help="path to a JSON policy-test suite")
    test_suite.add_argument("--format", choices=("json", "text"), default="text")

    coverage = subparsers.add_parser(
        "coverage", help="measure rule coverage over a policy regression suite"
    )
    coverage.add_argument("--policy", required=True, help="path to a JSON policy")
    coverage.add_argument(
        "--context-contract", help="validate the policy and suite inputs against this contract"
    )
    coverage.add_argument("suite", help="path to a JSON policy-test suite")
    coverage.add_argument(
        "--threshold",
        type=_coverage_threshold,
        default=0,
        metavar="PERCENT",
        help="minimum integer rule coverage percentage; default: 0",
    )
    coverage.add_argument("--format", choices=("json", "text"), default="text")

    lint = subparsers.add_parser("lint", help="report deterministic policy authoring findings")
    lint.add_argument("policy", help="path to a JSON policy")
    lint.add_argument(
        "--fail-on",
        choices=("none", *(severity.value for severity in PolicyLintSeverity)),
        default=PolicyLintSeverity.SECURITY_WARNING.value,
        help="lowest finding severity that exits 1; default: security-warning",
    )
    lint.add_argument("--format", choices=("json", "text"), default="text")

    compare = subparsers.add_parser(
        "compare", help="compare baseline and candidate behavior over a regression suite"
    )
    compare.add_argument("--baseline", required=True, help="path to the baseline JSON policy")
    compare.add_argument("--candidate", required=True, help="path to the candidate JSON policy")
    compare.add_argument(
        "--context-contract", help="validate both policies and suite inputs against this contract"
    )
    compare.add_argument("suite", help="path to a JSON policy-test suite")
    compare.add_argument("--format", choices=("json", "text"), default="text")

    shadow = subparsers.add_parser(
        "shadow", help="evaluate a candidate without changing the baseline decision"
    )
    shadow.add_argument("--baseline", required=True, help="path to the authoritative JSON policy")
    shadow.add_argument("--candidate", required=True, help="path to the observational JSON policy")
    shadow.add_argument(
        "--context-contract", help="validate both policies and the live input against this contract"
    )
    shadow.add_argument(
        "--input", default="-", help="path to a JSON input object; default: standard input"
    )
    shadow.add_argument("--format", choices=("json", "text"), default="json")

    compose = subparsers.add_parser(
        "compose", help="combine ordered policy sources into one deployable policy"
    )
    compose.add_argument("--id", dest="policy_id", required=True, help="composed policy id")
    compose.add_argument(
        "--version", dest="policy_version", required=True, help="composed policy version"
    )
    compose.add_argument("--description", default="", help="optional composed policy description")
    compose.add_argument(
        "--policy",
        dest="source_policies",
        action="append",
        required=True,
        help="ordered source policy path; repeat for each source",
    )
    compose.add_argument("--output", required=True, help="output path for the composed policy")
    compose.add_argument(
        "--force", action="store_true", help="explicitly replace an existing output file"
    )
    compose.add_argument("--format", choices=("json", "text"), default="text")

    deployment = subparsers.add_parser(
        "deployment", help="create or verify one exact single-file policy deployment"
    )
    deployment_subparsers = deployment.add_subparsers(dest="deployment_command", required=True)
    deployment_create = deployment_subparsers.add_parser(
        "create", help="create an atomically written policy deployment"
    )
    deployment_create.add_argument("--policy", required=True, help="path to a JSON policy")
    deployment_create.add_argument("--context-contract", help="optional application contract path")
    deployment_create.add_argument("--output", required=True, help="output deployment path")
    deployment_create.add_argument(
        "--force", action="store_true", help="explicitly replace an existing output file"
    )
    deployment_create.add_argument("--format", choices=("json", "text"), default="text")
    deployment_verify = deployment_subparsers.add_parser(
        "verify", help="parse and internally verify a policy deployment"
    )
    deployment_verify.add_argument("deployment", help="path to a policy deployment")
    deployment_verify.add_argument("--format", choices=("json", "text"), default="text")

    catalog = subparsers.add_parser(
        "catalog", help="validate and identify a trusted tool-capability catalog"
    )
    catalog.add_argument("catalog", help="path to a JSON tool catalog")
    catalog.add_argument("--format", choices=("json", "text"), default="text")

    lock = subparsers.add_parser("lock", help="create or verify an exact policy deployment lock")
    lock_subparsers = lock.add_subparsers(dest="lock_command", required=True)
    lock_create = lock_subparsers.add_parser("create", help="print a new deployment lock")
    lock_create.add_argument("--policy", required=True, help="path to a JSON policy")
    lock_create.add_argument("--context-contract", help="optional application contract path")
    lock_create.add_argument("--format", choices=("json", "text"), default="json")
    lock_verify = lock_subparsers.add_parser("verify", help="verify an existing deployment lock")
    lock_verify.add_argument("lock", help="path to a JSON deployment lock")
    lock_verify.add_argument("--policy", required=True, help="path to a JSON policy")
    lock_verify.add_argument("--context-contract", help="optional application contract path")
    lock_verify.add_argument("--format", choices=("json", "text"), default="text")

    schema = subparsers.add_parser("schema", help="print a bundled JSON Schema")
    schema.add_argument(
        "kind",
        nargs="?",
        choices=(
            "policy",
            "policy-test",
            "policy-comparison",
            "policy-composition",
            "policy-coverage",
            "policy-explanation",
            "policy-lint",
            "policy-runtime-status",
            "policy-shadow",
            "context-contract",
            "deployment-lock",
            "policy-deployment",
            "tool-context",
            "tool-approval",
            "tool-catalog",
            "audit-record",
        ),
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


def _render_explanation(explanation: PolicyExplanation, output_format: str) -> str:
    """Render one value-minimized explanation without adding evaluation data."""

    if output_format == "json":
        return json.dumps(explanation.to_dict(), indent=2, sort_keys=True)
    lines = [
        f"Outcome: {explanation.outcome.value.upper()}",
        f"Policy: {explanation.policy_id}@{explanation.policy_version}",
        f"Policy fingerprint: {explanation.policy_fingerprint}",
        f"Default applied: {'yes' if explanation.default_applied else 'no'}",
        "Rules:",
    ]
    if explanation.context_contract_fingerprint is not None:
        lines.insert(
            3,
            f"Context contract fingerprint: {explanation.context_contract_fingerprint}",
        )
    for rule in explanation.rules:
        rule_status = "MATCH" if rule.matched else "MISS"
        decisive = ", decisive" if rule.decisive else ""
        lines.append(
            f"  [{rule_status}] {rule.rule_id} ({rule.effect.value}, priority={rule.priority}"
            f"{decisive})"
        )
        for condition in rule.conditions:
            lines.append(
                f"    [{condition.status.value.upper()}] #{condition.index} "
                f"{condition.field} {condition.operator}"
            )
    return "\n".join(lines)


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


def _render_comparison_report(report: PolicyComparisonReport, output_format: str) -> str:
    if output_format == "json":
        return json.dumps(report.to_dict(), indent=2, sort_keys=True)
    lines = [
        f"Baseline: {report.baseline_policy_id}@{report.baseline_policy_version} "
        f"({report.baseline_policy_fingerprint})",
        f"Candidate: {report.candidate_policy_id}@{report.candidate_policy_version} "
        f"({report.candidate_policy_fingerprint})",
    ]
    for result in report.results:
        details: list[str] = []
        if result.status is PolicyComparisonStatus.ERROR:
            if result.baseline.error is not None:
                details.append(f"baseline error: {result.baseline.error}")
            if result.candidate.error is not None:
                details.append(f"candidate error: {result.candidate.error}")
        else:
            if PolicyComparisonChange.OUTCOME in result.changes:
                baseline_outcome = result.baseline.outcome
                candidate_outcome = result.candidate.outcome
                baseline_value = baseline_outcome.value if baseline_outcome is not None else "error"
                candidate_value = (
                    candidate_outcome.value if candidate_outcome is not None else "error"
                )
                details.append(f"outcome {baseline_value} -> {candidate_value}")
            if PolicyComparisonChange.MATCHED_RULES in result.changes:
                details.append("matched rules changed")
            if PolicyComparisonChange.WARNING_COUNT in result.changes:
                details.append(
                    f"warnings {result.baseline.warning_count} -> {result.candidate.warning_count}"
                )
            if PolicyComparisonChange.REASON_MESSAGES in result.changes:
                details.append("reason messages changed")
            if PolicyComparisonChange.WARNING_MESSAGES in result.changes:
                details.append("warning messages changed")
        suffix = f": {'; '.join(details)}" if details else ""
        lines.append(f"{result.status.value.upper()} {result.name}{suffix}")
    lines.append(
        f"Summary: {report.unchanged} unchanged, {report.changed} changed "
        f"({report.authorization_changes} authorization, "
        f"{report.metadata_only_changes} metadata-only), {report.errors} errors, "
        f"{len(report.results)} total"
    )
    return "\n".join(lines)


def _render_shadow_evaluation(
    evaluation: PolicyShadowEvaluation,
    output_format: str,
) -> str:
    if output_format == "json":
        return json.dumps(evaluation.to_dict(), indent=2, sort_keys=True)
    authoritative = evaluation.authoritative_decision
    authoritative_snapshot = evaluation.authoritative
    candidate = evaluation.candidate
    lines = [
        f"Authoritative: {authoritative.policy_id}@{authoritative.policy_version} "
        f"({authoritative.policy_fingerprint}) -> {authoritative.outcome.value.upper()} "
        f"(decision {authoritative.decision_id}; "
        f"evaluation {authoritative_snapshot.evaluation_duration_ns} ns)",
        f"Candidate: {candidate.policy_id}@{candidate.policy_version} "
        f"({candidate.policy_fingerprint})",
    ]
    if candidate.error is not None:
        lines.append(
            f"Candidate error after {candidate.evaluation_duration_ns} ns: {candidate.error}"
        )
    elif candidate.outcome is not None:
        lines.append(
            f"Candidate observation: {candidate.outcome.value.upper()} "
            f"(decision {candidate.decision_id}; evaluation {candidate.evaluation_duration_ns} ns)"
        )
    changes = ", ".join(change.value for change in evaluation.changes) or "none"
    lines.append(f"Shadow status: {evaluation.status.value.upper()}; changes: {changes}")
    lines.append("Enforce: authoritative baseline decision")
    return "\n".join(lines)


def _render_coverage_report(report: PolicyCoverageReport, output_format: str) -> str:
    if output_format == "json":
        return json.dumps(report.to_dict(), indent=2, sort_keys=True)
    lines = [
        f"Policy: {report.policy_id}@{report.policy_version} ({report.policy_fingerprint})",
        f"Rules: {report.covered_rules}/{report.total_rules} covered "
        f"({report.coverage_percent:.2f}%; required {report.required_coverage_percent}%)",
        f"Outcomes: {report.allow_cases} allow, {report.deny_cases} deny, "
        f"{report.review_cases} review",
    ]
    if report.uncovered_rule_ids:
        lines.append("Uncovered rules:")
        lines.extend(f"  - {rule_id}" for rule_id in report.uncovered_rule_ids)
    else:
        lines.append("Uncovered rules: none")
    if report.error_cases:
        lines.append("Errors:")
        lines.extend(f"  - {error.name}: {error.error}" for error in report.error_cases)
    status = "met" if report.threshold_met else "NOT MET"
    lines.append(
        f"Summary: threshold {status}; {report.evaluated_cases}/{report.total_cases} cases "
        f"evaluated, {report.errors} errors"
    )
    return "\n".join(lines)


def _render_lint_report(report: PolicyLintReport, output_format: str) -> str:
    if output_format == "json":
        return json.dumps(report.to_dict(), indent=2, sort_keys=True)
    lines = [f"Policy: {report.policy_id}@{report.policy_version} ({report.policy_fingerprint})"]
    for finding in report.findings:
        location = "policy"
        if finding.rule_id is not None:
            location = f"rule {finding.rule_id}"
            if finding.condition_indices:
                indices = ",".join(str(index) for index in finding.condition_indices)
                location += f" conditions[{indices}]"
        lines.append(
            f"{finding.severity.value.upper()} {finding.code.value} {location}: {finding.message}"
        )
    if not report.findings:
        lines.append("No findings.")
    status = "passed" if report.passed else "FAILED"
    lines.append(
        f"Summary: {status}; {report.security_warnings} security warnings, "
        f"{report.warnings} warnings, {report.suggestions} suggestions, "
        f"{report.blocking_findings} blocking"
    )
    return "\n".join(lines)


def _render_composition_report(
    composition: PolicyComposition,
    output_path: Path,
    output_format: str,
) -> str:
    if output_format == "json":
        return json.dumps(composition.to_dict(), indent=2, sort_keys=True)
    policy = composition.policy
    lines = [
        f"Composed policy: {policy.id}@{policy.version} ({composition.policy_fingerprint})",
        f"Output: {output_path}",
        f"Default: {policy.default_effect.value}",
        f"Rules: {len(policy.rules)} from {len(composition.sources)} sources",
        "Sources:",
    ]
    lines.extend(
        f"  - {source.policy_id}@{source.policy_version}: {source.rule_count} rules "
        f"({source.policy_fingerprint})"
        for source in composition.sources
    )
    return "\n".join(lines)


def _render_policy_deployment(
    deployment: PolicyDeployment,
    *,
    action: str,
    output_path: Path | None = None,
) -> str:
    """Render exact artifact metadata without copying deployment policy content."""

    lock = deployment.deployment_lock
    contract_label = (
        "none"
        if lock.context_contract is None
        else (
            f"{lock.context_contract.id}@{lock.context_contract.version} "
            f"({lock.context_contract.fingerprint})"
        )
    )
    output_label = "" if output_path is None else f"\nOutput: {output_path}"
    return (
        f"{action} policy deployment: policy={lock.policy.id}@{lock.policy.version} "
        f"({lock.policy.fingerprint}), contract={contract_label}, lock=verified"
        f"{output_label}"
    )


def _policy_deployment_summary(
    deployment: PolicyDeployment,
    *,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Return value-minimized deployment identity metadata for JSON output."""

    lock = deployment.deployment_lock
    return {
        "policy": {
            "id": lock.policy.id,
            "version": lock.policy.version,
            "fingerprint": lock.policy.fingerprint,
        },
        "context_contract": (
            None
            if lock.context_contract is None
            else {
                "id": lock.context_contract.id,
                "version": lock.context_contract.version,
                "fingerprint": lock.context_contract.fingerprint,
            }
        ),
        "lock_verified": True,
        "output": None if output_path is None else str(output_path),
    }


def _resolve_contract_and_lock(
    deployment: PolicyDeployment | None,
    *,
    context_contract_path: str | None,
    deployment_lock_path: str | None,
) -> tuple[ContextContract | None, DeploymentLock | None]:
    """Resolve one coherent enforcement contract and lock source."""

    if deployment is not None:
        return deployment.context_contract, deployment.deployment_lock
    context_contract = (
        load_context_contract(context_contract_path) if context_contract_path else None
    )
    deployment_lock = load_deployment_lock(deployment_lock_path) if deployment_lock_path else None
    return context_contract, deployment_lock


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
                "policy-comparison": get_policy_comparison_schema,
                "policy-composition": get_policy_composition_schema,
                "policy-coverage": get_policy_coverage_schema,
                "policy-explanation": get_policy_explanation_schema,
                "policy-lint": get_policy_lint_schema,
                "policy-runtime-status": get_policy_runtime_status_schema,
                "policy-shadow": get_policy_shadow_schema,
                "context-contract": get_context_contract_schema,
                "deployment-lock": get_deployment_lock_schema,
                "policy-deployment": get_policy_deployment_schema,
                "tool-context": get_tool_context_schema,
                "tool-approval": get_tool_approval_schema,
                "tool-catalog": get_tool_catalog_schema,
                "audit-record": get_audit_record_schema,
            }
            schema = schema_loaders[arguments.kind]()
            print(json.dumps(schema, indent=2, sort_keys=True), file=output)
            return EXIT_ALLOWED

        if arguments.command == "catalog":
            tool_catalog = load_tool_catalog(arguments.catalog)
            catalog_fingerprint = fingerprint_tool_catalog(tool_catalog)
            summary = {
                "valid": True,
                "tool_catalog_version": tool_catalog.tool_catalog_version,
                "catalog_id": tool_catalog.id,
                "catalog_version": tool_catalog.version,
                "catalog_fingerprint": catalog_fingerprint,
                "tool_count": len(tool_catalog.tools),
            }
            rendered = (
                json.dumps(summary, indent=2, sort_keys=True)
                if arguments.format == "json"
                else (
                    f"Valid tool catalog {tool_catalog.id}@{tool_catalog.version}: "
                    f"{len(tool_catalog.tools)} tools, fingerprint={catalog_fingerprint}"
                )
            )
            print(rendered, file=output)
            return EXIT_ALLOWED

        if arguments.command == "compose":
            if len(arguments.source_policies) > MAX_COMPOSED_POLICIES:
                raise PolicyCompositionError(
                    f"policy composition exceeds the limit of {MAX_COMPOSED_POLICIES} sources"
                )
            source_policies = [load_policy(path) for path in arguments.source_policies]
            composition = compose_policies(
                source_policies,
                policy_id=arguments.policy_id,
                policy_version=arguments.policy_version,
                description=arguments.description,
            )
            target = write_policy(arguments.output, composition.policy, force=arguments.force)
            print(_render_composition_report(composition, target, arguments.format), file=output)
            return EXIT_ALLOWED

        if arguments.command == "deployment":
            if arguments.deployment_command == "create":
                policy = load_policy(arguments.policy)
                context_contract = (
                    load_context_contract(arguments.context_contract)
                    if arguments.context_contract
                    else None
                )
                policy_deployment = create_policy_deployment(policy, context_contract)
                target = write_policy_deployment(
                    arguments.output,
                    policy_deployment,
                    force=arguments.force,
                )
                rendered = (
                    json.dumps(
                        _policy_deployment_summary(policy_deployment, output_path=target),
                        indent=2,
                        sort_keys=True,
                    )
                    if arguments.format == "json"
                    else _render_policy_deployment(
                        policy_deployment,
                        action="Created",
                        output_path=target,
                    )
                )
                print(rendered, file=output)
            else:
                policy_deployment = load_policy_deployment(arguments.deployment)
                rendered = (
                    json.dumps(
                        _policy_deployment_summary(policy_deployment),
                        indent=2,
                        sort_keys=True,
                    )
                    if arguments.format == "json"
                    else _render_policy_deployment(policy_deployment, action="Verified")
                )
                print(rendered, file=output)
            return EXIT_ALLOWED

        if arguments.command == "lock":
            policy = load_policy(arguments.policy)
            context_contract = (
                load_context_contract(arguments.context_contract)
                if arguments.context_contract
                else None
            )
            if arguments.lock_command == "create":
                lock_value = create_deployment_lock(policy, context_contract)
            else:
                lock_value = load_deployment_lock(arguments.lock)
                verify_deployment_lock(lock_value, policy, context_contract)
            if arguments.format == "json":
                print(
                    json.dumps(lock_value.to_dict(), indent=2, sort_keys=True),
                    file=output,
                )
            else:
                contract_label = (
                    "none"
                    if lock_value.context_contract is None
                    else (
                        f"{lock_value.context_contract.id}@"
                        f"{lock_value.context_contract.version} "
                        f"({lock_value.context_contract.fingerprint})"
                    )
                )
                print(
                    f"{'Created' if arguments.lock_command == 'create' else 'Verified'} "
                    f"deployment lock: policy={lock_value.policy.id}@"
                    f"{lock_value.policy.version} ({lock_value.policy.fingerprint}), "
                    f"contract={contract_label}",
                    file=output,
                )
            return EXIT_ALLOWED

        if arguments.command == "compare":
            baseline = load_policy(arguments.baseline)
            candidate = load_policy(arguments.candidate)
            suite = load_policy_test_suite(arguments.suite)
            context_contract = (
                load_context_contract(arguments.context_contract)
                if arguments.context_contract
                else None
            )
            comparison_report = compare_policies(
                baseline,
                candidate,
                suite,
                context_contract=context_contract,
            )
            print(_render_comparison_report(comparison_report, arguments.format), file=output)
            return EXIT_ALLOWED if comparison_report.identical else EXIT_TEST_FAILED

        if arguments.command == "shadow":
            baseline = load_policy(arguments.baseline)
            candidate = load_policy(arguments.candidate)
            context = load_context(arguments.input, stdin=binary_input)
            context_contract = (
                load_context_contract(arguments.context_contract)
                if arguments.context_contract
                else None
            )
            shadow_evaluation = PolicyShadowEvaluator(
                baseline,
                candidate,
                context_contract=context_contract,
            ).evaluate(context)
            print(_render_shadow_evaluation(shadow_evaluation, arguments.format), file=output)
            return _decision_exit(shadow_evaluation.authoritative_decision.outcome)

        deployment_value: PolicyDeployment | None = None
        if arguments.command in {"check", "explain"} and arguments.deployment is not None:
            if arguments.context_contract is not None or arguments.deployment_lock is not None:
                raise InputValidationError(
                    "--context-contract and --deployment-lock must not be supplied with "
                    "--deployment"
                )
            deployment_value = load_policy_deployment(arguments.deployment)
            policy = deployment_value.policy
        else:
            policy = load_policy(arguments.policy)
        if arguments.command == "lint":
            fail_on = None if arguments.fail_on == "none" else PolicyLintSeverity(arguments.fail_on)
            lint_report = lint_policy(policy, fail_on=fail_on)
            print(_render_lint_report(lint_report, arguments.format), file=output)
            return EXIT_ALLOWED if lint_report.passed else EXIT_TEST_FAILED

        if arguments.command == "coverage":
            suite = load_policy_test_suite(arguments.suite)
            context_contract = (
                load_context_contract(arguments.context_contract)
                if arguments.context_contract
                else None
            )
            coverage_report = measure_policy_coverage(
                policy,
                suite,
                threshold=arguments.threshold,
                context_contract=context_contract,
            )
            print(_render_coverage_report(coverage_report, arguments.format), file=output)
            return EXIT_ALLOWED if coverage_report.threshold_met else EXIT_TEST_FAILED

        if arguments.command == "validate":
            context_contract = (
                load_context_contract(arguments.context_contract)
                if arguments.context_contract
                else None
            )
            deployment_lock = (
                load_deployment_lock(arguments.deployment_lock)
                if arguments.deployment_lock
                else None
            )
            PolicyEngine(
                policy,
                context_contract=context_contract,
                deployment_lock=deployment_lock,
            )
            policy_fingerprint = fingerprint_policy(policy)
            result = {
                "valid": True,
                "policy_id": policy.id,
                "policy_version": policy.version,
                "policy_fingerprint": policy_fingerprint,
                "default_effect": policy.default_effect.value,
                "rule_count": len(policy.rules),
            }
            if context_contract is not None:
                result["context_contract"] = {
                    "format_version": context_contract.context_contract_version,
                    "id": context_contract.id,
                    "version": context_contract.version,
                }
            if deployment_lock is not None:
                result["deployment_lock_verified"] = True
            if arguments.format == "json":
                print(json.dumps(result, indent=2, sort_keys=True), file=output)
            else:
                contract_suffix = (
                    f", contract={context_contract.id}@{context_contract.version}"
                    if context_contract is not None
                    else ""
                )
                lock_suffix = ", deployment-lock=verified" if deployment_lock is not None else ""
                print(
                    f"Valid policy {policy.id}@{policy.version}: "
                    f"{len(policy.rules)} rules, default={policy.default_effect.value}, "
                    f"fingerprint={policy_fingerprint}{contract_suffix}{lock_suffix}",
                    file=output,
                )
            return EXIT_ALLOWED

        if arguments.command == "explain":
            context = load_context(arguments.input, stdin=binary_input)
            context_contract, deployment_lock = _resolve_contract_and_lock(
                deployment_value,
                context_contract_path=arguments.context_contract,
                deployment_lock_path=arguments.deployment_lock,
            )
            explanation = PolicyEngine(
                policy,
                context_contract=context_contract,
                deployment_lock=deployment_lock,
            ).explain(context)
            print(_render_explanation(explanation, arguments.format), file=output)
            return _decision_exit(explanation.outcome)

        if arguments.command == "test":
            suite = load_policy_test_suite(arguments.suite)
            context_contract = (
                load_context_contract(arguments.context_contract)
                if arguments.context_contract
                else None
            )
            test_report = run_policy_tests(
                policy,
                suite,
                context_contract=context_contract,
            )
            print(_render_test_report(test_report, arguments.format), file=output)
            return EXIT_ALLOWED if test_report.successful else EXIT_TEST_FAILED

        context = load_context(arguments.input, stdin=binary_input)
        context_contract, deployment_lock = _resolve_contract_and_lock(
            deployment_value,
            context_contract_path=arguments.context_contract,
            deployment_lock_path=arguments.deployment_lock,
        )
        decision = PolicyEngine(
            policy,
            context_contract=context_contract,
            deployment_lock=deployment_lock,
        ).evaluate(context)
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
