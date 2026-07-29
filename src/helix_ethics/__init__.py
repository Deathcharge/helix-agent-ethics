"""Public API for the Helix Agent Ethics policy gate."""

from .engine import PolicyEngine
from .errors import AuditLogError, EvaluationError, InputValidationError, PolicyValidationError
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
    "append_audit_record",
    "load_context",
    "load_policy",
]
