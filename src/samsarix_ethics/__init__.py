# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Public API for the Samsarix Agent Ethics policy gate."""

from .engine import PolicyEngine
from .errors import (
    AuditLogError,
    EvaluationError,
    InputValidationError,
    PolicyValidationError,
    SamsarixEthicsError,
)
from .io import append_audit_record, load_context, load_policy
from .models import Decision, Effect, Outcome, Policy, PolicyCondition, PolicyRule

__version__ = "0.1.0"

__all__ = [
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
    "PolicyValidationError",
    "SamsarixEthicsError",
    "append_audit_record",
    "load_context",
    "load_policy",
]
