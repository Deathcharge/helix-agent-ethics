# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Single-file exact policy, context-contract, and deployment-lock units."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import ContextContract, validate_policy_context_contract
from .deployment import DeploymentLock, create_deployment_lock, verify_deployment_lock
from .errors import (
    ContextContractValidationError,
    DeploymentLockValidationError,
    InputValidationError,
    PolicyDeploymentValidationError,
    PolicyValidationError,
)
from .models import Policy
from .validation import validate_json_shape

POLICY_DEPLOYMENT_VERSION = 1


def _check_keys(value: dict[str, Any]) -> None:
    required = {
        "policy_deployment_version",
        "policy",
        "context_contract",
        "deployment_lock",
    }
    missing = sorted(required - value.keys())
    unknown = sorted(value.keys() - required)
    if missing:
        raise PolicyDeploymentValidationError(f"policy deployment is missing: {', '.join(missing)}")
    if unknown:
        raise PolicyDeploymentValidationError(
            f"policy deployment has unknown fields: {', '.join(unknown)}"
        )


@dataclass(frozen=True, slots=True)
class PolicyDeployment:
    """One immutable, internally verified enforcement configuration."""

    policy_deployment_version: int
    policy: Policy
    context_contract: ContextContract | None
    deployment_lock: DeploymentLock

    def __post_init__(self) -> None:
        if (
            isinstance(self.policy_deployment_version, bool)
            or self.policy_deployment_version != POLICY_DEPLOYMENT_VERSION
        ):
            raise PolicyDeploymentValidationError("policy_deployment_version must be 1")
        if not isinstance(self.policy, Policy):
            raise PolicyDeploymentValidationError("policy deployment policy must be a Policy")
        if self.context_contract is not None and not isinstance(
            self.context_contract, ContextContract
        ):
            raise PolicyDeploymentValidationError(
                "policy deployment context_contract must be a ContextContract or None"
            )
        if not isinstance(self.deployment_lock, DeploymentLock):
            raise PolicyDeploymentValidationError(
                "policy deployment deployment_lock must be a DeploymentLock"
            )
        if self.context_contract is not None:
            try:
                validate_policy_context_contract(self.policy, self.context_contract)
            except ContextContractValidationError as exc:
                raise PolicyDeploymentValidationError(
                    f"policy deployment contract compatibility failed: {exc}"
                ) from exc
        try:
            verify_deployment_lock(
                self.deployment_lock,
                self.policy,
                self.context_contract,
            )
        except DeploymentLockValidationError as exc:
            raise PolicyDeploymentValidationError(
                f"policy deployment lock verification failed: {exc}"
            ) from exc

    @classmethod
    def from_dict(cls, value: Any) -> PolicyDeployment:
        """Strictly parse and internally verify one deployment JSON object."""

        try:
            validate_json_shape(value, label="policy deployment")
        except InputValidationError as exc:
            raise PolicyDeploymentValidationError(str(exc)) from exc
        if not isinstance(value, dict):
            raise PolicyDeploymentValidationError("policy deployment must be a JSON object")
        _check_keys(value)
        if (
            isinstance(value["policy_deployment_version"], bool)
            or value["policy_deployment_version"] != POLICY_DEPLOYMENT_VERSION
        ):
            raise PolicyDeploymentValidationError("policy_deployment_version must be 1")
        try:
            policy = Policy.from_dict(value["policy"])
        except PolicyValidationError as exc:
            raise PolicyDeploymentValidationError(
                f"policy deployment contains an invalid policy: {exc}"
            ) from exc
        context_value = value["context_contract"]
        try:
            context_contract = (
                None if context_value is None else ContextContract.from_dict(context_value)
            )
        except ContextContractValidationError as exc:
            raise PolicyDeploymentValidationError(
                f"policy deployment contains an invalid context contract: {exc}"
            ) from exc
        try:
            deployment_lock = DeploymentLock.from_dict(value["deployment_lock"])
        except DeploymentLockValidationError as exc:
            raise PolicyDeploymentValidationError(
                f"policy deployment contains an invalid deployment lock: {exc}"
            ) from exc
        return cls(
            policy_deployment_version=POLICY_DEPLOYMENT_VERSION,
            policy=policy,
            context_contract=context_contract,
            deployment_lock=deployment_lock,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a fresh JSON-compatible deployment representation."""

        return {
            "policy_deployment_version": self.policy_deployment_version,
            "policy": self.policy.to_dict(),
            "context_contract": (
                None if self.context_contract is None else self.context_contract.to_dict()
            ),
            "deployment_lock": self.deployment_lock.to_dict(),
        }


def create_policy_deployment(
    policy: Policy,
    context_contract: ContextContract | None = None,
) -> PolicyDeployment:
    """Create a deterministic deployment with a mandatory exact-content lock."""

    if not isinstance(policy, Policy):
        raise TypeError("policy must be a Policy")
    if context_contract is not None and not isinstance(context_contract, ContextContract):
        raise TypeError("context_contract must be a ContextContract or None")
    return PolicyDeployment(
        policy_deployment_version=POLICY_DEPLOYMENT_VERSION,
        policy=policy,
        context_contract=context_contract,
        deployment_lock=create_deployment_lock(policy, context_contract),
    )
