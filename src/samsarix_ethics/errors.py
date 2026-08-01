# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Domain errors exposed by the package."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Decision


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


class ToolCallBlockedError(SamsarixEthicsError):
    """Base error for a valid tool call that policy did not authorize."""

    def __init__(self, message: str, decision: Decision) -> None:
        super().__init__(message)
        self.decision = decision


class ToolCallDeniedError(ToolCallBlockedError):
    """Raised when policy denies a proposed tool call."""

    def __init__(self, decision: Decision) -> None:
        super().__init__(
            f"tool call denied by policy {decision.policy_id!r} (decision {decision.decision_id})",
            decision,
        )


class ToolCallReviewRequiredError(ToolCallBlockedError):
    """Raised when a proposed tool call requires human review."""

    def __init__(self, decision: Decision) -> None:
        super().__init__(
            f"tool call requires review under policy {decision.policy_id!r} "
            f"(decision {decision.decision_id})",
            decision,
        )
