# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Public API for the Samsarix Agent Ethics policy gate."""

from .approval import (
    MAX_TOOL_CALL_FINGERPRINT_BYTES,
    TOOL_CALL_APPROVAL_VERSION,
    TOOL_CALL_FINGERPRINT_VERSION,
    ToolCallApproval,
)
from .audit import AUDIT_RECORD_VERSION, AuditRecord, AuditSink, JsonlAuditSink
from .comparison import (
    POLICY_COMPARISON_VERSION,
    PolicyComparisonChange,
    PolicyComparisonReport,
    PolicyComparisonResult,
    PolicyComparisonSnapshot,
    PolicyComparisonStatus,
    compare_policies,
)
from .coverage import (
    POLICY_COVERAGE_VERSION,
    PolicyCoverageError,
    PolicyCoverageReport,
    measure_policy_coverage,
)
from .engine import MAX_BATCH_ITEMS, PolicyEngine
from .errors import (
    AuditLogError,
    EvaluationError,
    InputValidationError,
    PolicyTestValidationError,
    PolicyValidationError,
    SamsarixEthicsError,
    ToolCallBlockedError,
    ToolCallDeniedError,
    ToolCallReviewRequiredError,
)
from .gate import (
    MAX_TOOL_CAPABILITIES,
    TOOL_CONTEXT_VERSION,
    BoundToolGate,
    ToolExecutionResult,
    ToolGate,
    build_tool_context,
    fingerprint_tool_call,
)
from .io import append_audit_record, load_context, load_policy
from .models import Decision, Effect, Outcome, Policy, PolicyCondition, PolicyRule
from .provenance import POLICY_FINGERPRINT_VERSION, fingerprint_policy
from .schema import (
    get_audit_record_schema,
    get_policy_comparison_schema,
    get_policy_coverage_schema,
    get_policy_schema,
    get_policy_test_schema,
    get_tool_approval_schema,
    get_tool_context_schema,
)
from .testing import (
    MAX_POLICY_TEST_BYTES,
    PolicyTestCase,
    PolicyTestReport,
    PolicyTestResult,
    PolicyTestStatus,
    PolicyTestSuite,
    load_policy_test_suite,
    run_policy_tests,
)
from .validation import validate_context

__version__ = "0.1.0"

__all__ = [
    "AUDIT_RECORD_VERSION",
    "MAX_BATCH_ITEMS",
    "MAX_POLICY_TEST_BYTES",
    "MAX_TOOL_CALL_FINGERPRINT_BYTES",
    "MAX_TOOL_CAPABILITIES",
    "POLICY_COMPARISON_VERSION",
    "POLICY_COVERAGE_VERSION",
    "POLICY_FINGERPRINT_VERSION",
    "TOOL_CALL_APPROVAL_VERSION",
    "TOOL_CALL_FINGERPRINT_VERSION",
    "TOOL_CONTEXT_VERSION",
    "AuditLogError",
    "AuditRecord",
    "AuditSink",
    "BoundToolGate",
    "Decision",
    "Effect",
    "EvaluationError",
    "InputValidationError",
    "JsonlAuditSink",
    "Outcome",
    "Policy",
    "PolicyComparisonChange",
    "PolicyComparisonReport",
    "PolicyComparisonResult",
    "PolicyComparisonSnapshot",
    "PolicyComparisonStatus",
    "PolicyCondition",
    "PolicyCoverageError",
    "PolicyCoverageReport",
    "PolicyEngine",
    "PolicyRule",
    "PolicyTestCase",
    "PolicyTestReport",
    "PolicyTestResult",
    "PolicyTestStatus",
    "PolicyTestSuite",
    "PolicyTestValidationError",
    "PolicyValidationError",
    "SamsarixEthicsError",
    "ToolCallApproval",
    "ToolCallBlockedError",
    "ToolCallDeniedError",
    "ToolCallReviewRequiredError",
    "ToolExecutionResult",
    "ToolGate",
    "append_audit_record",
    "build_tool_context",
    "compare_policies",
    "fingerprint_policy",
    "fingerprint_tool_call",
    "get_audit_record_schema",
    "get_policy_comparison_schema",
    "get_policy_coverage_schema",
    "get_policy_schema",
    "get_policy_test_schema",
    "get_tool_approval_schema",
    "get_tool_context_schema",
    "load_context",
    "load_policy",
    "load_policy_test_suite",
    "measure_policy_coverage",
    "run_policy_tests",
    "validate_context",
]
