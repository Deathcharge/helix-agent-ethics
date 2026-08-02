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


class ContextContractValidationError(SamsarixEthicsError):
    """Raised when a context contract is malformed or incompatible with a policy."""


class DeploymentLockValidationError(SamsarixEthicsError):
    """Raised when a deployment lock is malformed or does not match its artifacts."""


class PolicyActivationError(SamsarixEthicsError):
    """Raised when an atomic policy activation cannot replace the live generation."""


class PolicyDeploymentValidationError(SamsarixEthicsError):
    """Raised when a single-file policy deployment is malformed or inconsistent."""


class PolicyCompositionError(SamsarixEthicsError):
    """Raised when validated policy sources cannot be composed safely."""


class ToolCatalogValidationError(SamsarixEthicsError):
    """Raised when a trusted tool catalog or registry snapshot is invalid."""


class ToolGateDeploymentValidationError(SamsarixEthicsError):
    """Raised when a coherent tool-gate deployment is malformed or inconsistent."""


class InputValidationError(SamsarixEthicsError):
    """Raised when an evaluation input cannot be safely parsed or validated."""


class EvaluationError(SamsarixEthicsError):
    """Raised when a valid policy cannot be evaluated against the supplied input."""


class PolicyTestValidationError(SamsarixEthicsError):
    """Raised when a policy-test suite is malformed or outside safety limits."""


class AuditLogError(SamsarixEthicsError):
    """Raised when a requested audit record cannot be durably appended."""


class AuditChainError(AuditLogError):
    """Raised when a keyed audit chain cannot be written or verified."""


class ToolCallBlockedError(SamsarixEthicsError):
    """A typed block with its selected decision and complete evaluation set."""

    def __init__(
        self,
        message: str,
        decision: Decision,
        *,
        decisions: tuple[Decision, ...] | None = None,
        blocking_index: int = 0,
    ) -> None:
        super().__init__(message)
        self.decision = decision
        self.decisions = (decision,) if decisions is None else decisions
        self.blocking_index = blocking_index


class ToolCallDeniedError(ToolCallBlockedError):
    """Raised when policy denies a proposed tool call."""

    def __init__(
        self,
        decision: Decision,
        *,
        decisions: tuple[Decision, ...] | None = None,
        blocking_index: int = 0,
    ) -> None:
        super().__init__(
            f"tool call denied by policy {decision.policy_id!r} (decision {decision.decision_id})",
            decision,
            decisions=decisions,
            blocking_index=blocking_index,
        )


class ToolCallReviewRequiredError(ToolCallBlockedError):
    """Raised when a proposed tool call requires human review."""

    def __init__(
        self,
        decision: Decision,
        *,
        decisions: tuple[Decision, ...] | None = None,
        blocking_index: int = 0,
    ) -> None:
        super().__init__(
            f"tool call requires review under policy {decision.policy_id!r} "
            f"(decision {decision.decision_id})",
            decision,
            decisions=decisions,
            blocking_index=blocking_index,
        )
