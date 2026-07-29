"""Domain errors exposed by the package."""


class HelixEthicsError(Exception):
    """Base class for user-correctable policy-gate errors."""


class PolicyValidationError(HelixEthicsError):
    """Raised when a policy document is malformed or internally inconsistent."""


class InputValidationError(HelixEthicsError):
    """Raised when an evaluation input cannot be safely parsed or validated."""


class EvaluationError(HelixEthicsError):
    """Raised when a valid policy cannot be evaluated against the supplied input."""


class AuditLogError(HelixEthicsError):
    """Raised when a requested audit record cannot be durably appended."""
