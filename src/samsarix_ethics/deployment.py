# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Exact-content deployment locks for policy and context-contract activation."""

from __future__ import annotations

import hmac
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .contracts import ContextContract
from .errors import DeploymentLockValidationError, InputValidationError
from .models import Policy
from .provenance import (
    _is_context_contract_fingerprint,
    _is_policy_fingerprint,
    fingerprint_context_contract,
    fingerprint_policy,
)
from .validation import validate_json_shape

DEPLOYMENT_LOCK_VERSION = 1
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


def _check_keys(
    data: dict[str, Any], *, required: set[str], optional: set[str], location: str
) -> None:
    missing = sorted(required - data.keys())
    unknown = sorted(data.keys() - required - optional)
    if missing:
        raise DeploymentLockValidationError(f"{location} is missing: {', '.join(missing)}")
    if unknown:
        raise DeploymentLockValidationError(f"{location} has unknown fields: {', '.join(unknown)}")


def _artifact(
    value: Any,
    *,
    location: str,
    fingerprint_validator: Callable[[object], bool],
) -> DeploymentLockArtifact:
    if not isinstance(value, dict):
        raise DeploymentLockValidationError(f"{location} must be a JSON object")
    _check_keys(
        value,
        required={"id", "version", "fingerprint"},
        optional=set(),
        location=location,
    )
    for key in ("id", "version"):
        item = value[key]
        if not isinstance(item, str) or not _IDENTIFIER.fullmatch(item):
            raise DeploymentLockValidationError(
                f"{location}.{key} must be a 1-128 character identifier"
            )
    if not fingerprint_validator(value["fingerprint"]):
        raise DeploymentLockValidationError(
            f"{location}.fingerprint must use the v1 SHA-256 fingerprint format"
        )
    return DeploymentLockArtifact(
        id=value["id"],
        version=value["version"],
        fingerprint=value["fingerprint"],
    )


@dataclass(frozen=True, slots=True)
class DeploymentLockArtifact:
    """Identity labels and exact canonical fingerprint for one locked artifact."""

    id: str
    version: str
    fingerprint: str

    def __post_init__(self) -> None:
        for name in ("id", "version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
                raise DeploymentLockValidationError(
                    f"deployment lock artifact {name} must be a 1-128 character identifier"
                )
        if not _is_policy_fingerprint(self.fingerprint):
            raise DeploymentLockValidationError(
                "deployment lock artifact fingerprint must use the v1 SHA-256 fingerprint format"
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "version": self.version,
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True, slots=True)
class DeploymentLock:
    """A versioned lock binding one policy and optional context contract by exact content."""

    deployment_lock_version: int
    policy: DeploymentLockArtifact
    context_contract: DeploymentLockArtifact | None

    def __post_init__(self) -> None:
        if (
            isinstance(self.deployment_lock_version, bool)
            or self.deployment_lock_version != DEPLOYMENT_LOCK_VERSION
        ):
            raise DeploymentLockValidationError("deployment_lock_version must be 1")
        if not isinstance(self.policy, DeploymentLockArtifact):
            raise DeploymentLockValidationError("deployment lock policy must be an artifact")
        if self.context_contract is not None and not isinstance(
            self.context_contract, DeploymentLockArtifact
        ):
            raise DeploymentLockValidationError(
                "deployment lock context_contract must be an artifact or null"
            )

    @classmethod
    def from_dict(cls, value: Any) -> DeploymentLock:
        try:
            validate_json_shape(value, label="deployment lock")
        except InputValidationError as exc:
            raise DeploymentLockValidationError(str(exc)) from exc
        if not isinstance(value, dict):
            raise DeploymentLockValidationError("deployment lock must be a JSON object")
        _check_keys(
            value,
            required={"deployment_lock_version", "policy", "context_contract"},
            optional=set(),
            location="deployment lock",
        )
        if (
            isinstance(value["deployment_lock_version"], bool)
            or value["deployment_lock_version"] != DEPLOYMENT_LOCK_VERSION
        ):
            raise DeploymentLockValidationError("deployment_lock_version must be 1")
        policy = _artifact(
            value["policy"],
            location="deployment lock.policy",
            fingerprint_validator=_is_policy_fingerprint,
        )
        context_value = value["context_contract"]
        context_contract = (
            None
            if context_value is None
            else _artifact(
                context_value,
                location="deployment lock.context_contract",
                fingerprint_validator=_is_context_contract_fingerprint,
            )
        )
        return cls(
            deployment_lock_version=DEPLOYMENT_LOCK_VERSION,
            policy=policy,
            context_contract=context_contract,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "deployment_lock_version": self.deployment_lock_version,
            "policy": self.policy.to_dict(),
            "context_contract": (
                None if self.context_contract is None else self.context_contract.to_dict()
            ),
        }


def create_deployment_lock(
    policy: Policy,
    context_contract: ContextContract | None = None,
) -> DeploymentLock:
    """Create an immutable exact-content lock for one enforcement configuration."""

    if not isinstance(policy, Policy):
        raise TypeError("policy must be a Policy")
    if context_contract is not None and not isinstance(context_contract, ContextContract):
        raise TypeError("context_contract must be a ContextContract or None")
    contract_artifact = (
        None
        if context_contract is None
        else DeploymentLockArtifact(
            id=context_contract.id,
            version=context_contract.version,
            fingerprint=fingerprint_context_contract(context_contract),
        )
    )
    return DeploymentLock(
        deployment_lock_version=DEPLOYMENT_LOCK_VERSION,
        policy=DeploymentLockArtifact(
            id=policy.id,
            version=policy.version,
            fingerprint=fingerprint_policy(policy),
        ),
        context_contract=contract_artifact,
    )


def verify_deployment_lock(
    lock: DeploymentLock,
    policy: Policy,
    context_contract: ContextContract | None = None,
) -> None:
    """Reject any policy or context contract that differs from an exact-content lock."""

    if not isinstance(lock, DeploymentLock):
        raise TypeError("lock must be a DeploymentLock")
    expected = create_deployment_lock(policy, context_contract)
    if (
        lock.policy.id != expected.policy.id
        or lock.policy.version != expected.policy.version
        or not hmac.compare_digest(lock.policy.fingerprint, expected.policy.fingerprint)
    ):
        raise DeploymentLockValidationError("deployment lock does not match the policy")
    if (lock.context_contract is None) != (expected.context_contract is None):
        raise DeploymentLockValidationError(
            "deployment lock context-contract presence does not match"
        )
    locked_contract = lock.context_contract
    expected_contract = expected.context_contract
    if (
        locked_contract is not None
        and expected_contract is not None
        and (
            locked_contract.id != expected_contract.id
            or locked_contract.version != expected_contract.version
            or not hmac.compare_digest(
                locked_contract.fingerprint,
                expected_contract.fingerprint,
            )
        )
    ):
        raise DeploymentLockValidationError("deployment lock does not match the context contract")
