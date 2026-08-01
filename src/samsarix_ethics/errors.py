# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Domain errors exposed by the package."""


class SamsarixEthicsError(Exception):
    """Base class for user-correctable policy-gate errors."""


class PolicyValidationError(SamsarixEthicsError):
    """Raised when a policy document is malformed or internally inconsistent."""


class InputValidationError(SamsarixEthicsError):
    """Raised when an evaluation input cannot be safely parsed or validated."""


class EvaluationError(SamsarixEthicsError):
    """Raised when a valid policy cannot be evaluated against the supplied input."""


class PolicyTestValidationError(SamsarixEthicsError):
    """Raised when a policy-test suite is malformed or outside safety limits."""


class AuditLogError(SamsarixEthicsError):
    """Raised when a requested audit record cannot be durably appended."""
