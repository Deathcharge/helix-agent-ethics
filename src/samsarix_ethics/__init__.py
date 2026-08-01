# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Public API for the Samsarix Agent Ethics policy gate."""

from .engine import MAX_BATCH_ITEMS, PolicyEngine
from .errors import (
    AuditLogError,
    EvaluationError,
    InputValidationError,
    PolicyTestValidationError,
    PolicyValidationError,
    SamsarixEthicsError,
)
from .io import append_audit_record, load_context, load_policy
from .models import Decision, Effect, Outcome, Policy, PolicyCondition, PolicyRule
from .schema import get_policy_schema, get_policy_test_schema
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
    "MAX_BATCH_ITEMS",
    "MAX_POLICY_TEST_BYTES",
    "AuditLogError",
    "Decision",
    "Effect",
    "EvaluationError",
    "InputValidationError",
    "Outcome",
    "Policy",
    "PolicyCondition",
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
    "append_audit_record",
    "get_policy_schema",
    "get_policy_test_schema",
    "load_context",
    "load_policy",
    "load_policy_test_suite",
    "run_policy_tests",
    "validate_context",
]
