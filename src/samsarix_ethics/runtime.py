# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Atomic in-process activation of complete policy enforcement configurations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Any

from .contracts import ContextContract
from .deployment import DeploymentLock
from .engine import PolicyEngine
from .errors import PolicyActivationError
from .explanation import PolicyExplanation
from .models import Decision, Policy
from .policy_deployment import PolicyDeployment

POLICY_RUNTIME_STATUS_VERSION = 1


@dataclass(frozen=True, slots=True)
class PolicyRuntimeStatus:
    """Input-free metadata for one successfully activated runtime generation."""

    generation: int
    activated_at: str
    policy_id: str
    policy_version: str
    policy_fingerprint: str
    context_contract_id: str | None
    context_contract_version: str | None
    context_contract_fingerprint: str | None
    deployment_lock_verified: bool
    runtime_status_version: int = POLICY_RUNTIME_STATUS_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Return the versioned JSON-compatible operational status."""

        context_contract = (
            None
            if self.context_contract_id is None
            else {
                "id": self.context_contract_id,
                "version": self.context_contract_version,
                "fingerprint": self.context_contract_fingerprint,
            }
        )
        return {
            "runtime_status_version": self.runtime_status_version,
            "generation": self.generation,
            "activated_at": self.activated_at,
            "policy": {
                "id": self.policy_id,
                "version": self.policy_version,
                "fingerprint": self.policy_fingerprint,
            },
            "context_contract": context_contract,
            "deployment_lock_verified": self.deployment_lock_verified,
        }


def _status(engine: PolicyEngine, generation: int) -> PolicyRuntimeStatus:
    contract = engine.context_contract
    return PolicyRuntimeStatus(
        generation=generation,
        activated_at=datetime.now(UTC).isoformat(),
        policy_id=engine.policy.id,
        policy_version=engine.policy.version,
        policy_fingerprint=engine.policy_fingerprint,
        context_contract_id=None if contract is None else contract.id,
        context_contract_version=None if contract is None else contract.version,
        context_contract_fingerprint=engine.context_contract_fingerprint,
        deployment_lock_verified=engine.deployment_lock is not None,
    )


class PolicyRuntime:
    """Serve decisions while atomically activating validated policy generations.

    Candidate engines are completely constructed before the live-state lock is
    acquired. A validation or deployment-lock failure therefore leaves the active
    generation untouched. Each evaluation captures exactly one engine generation;
    a bounded batch captures one generation for the entire batch.
    """

    def __init__(
        self,
        policy: Policy,
        *,
        context_contract: ContextContract | None = None,
        deployment_lock: DeploymentLock | None = None,
    ) -> None:
        engine = PolicyEngine(
            policy,
            context_contract=context_contract,
            deployment_lock=deployment_lock,
        )
        self._lock = Lock()
        self._engine = engine
        self._status = _status(engine, 1)

    @classmethod
    def from_deployment(cls, deployment: PolicyDeployment) -> PolicyRuntime:
        """Construct generation 1 from one internally verified deployment unit."""

        if not isinstance(deployment, PolicyDeployment):
            raise TypeError("deployment must be a PolicyDeployment")
        return cls(
            deployment.policy,
            context_contract=deployment.context_contract,
            deployment_lock=deployment.deployment_lock,
        )

    def _capture(self) -> tuple[PolicyEngine, PolicyRuntimeStatus]:
        with self._lock:
            return self._engine, self._status

    @property
    def status(self) -> PolicyRuntimeStatus:
        """Return one coherent immutable snapshot of the active generation."""

        return self._capture()[1]

    @property
    def policy(self) -> Policy:
        """Return the immutable policy in the current generation."""

        return self._capture()[0].policy

    @property
    def policy_fingerprint(self) -> str:
        """Return the exact current policy fingerprint."""

        return self._capture()[1].policy_fingerprint

    @property
    def context_contract(self) -> ContextContract | None:
        """Return the current application context contract, when configured."""

        return self._capture()[0].context_contract

    @property
    def context_contract_fingerprint(self) -> str | None:
        """Return the exact current context-contract fingerprint, when configured."""

        return self._capture()[1].context_contract_fingerprint

    @property
    def deployment_lock(self) -> DeploymentLock | None:
        """Return the deployment lock verified for the current generation, if any."""

        return self._capture()[0].deployment_lock

    def evaluate(self, context: Mapping[str, Any]) -> Decision:
        """Evaluate one context against the generation active at call capture time."""

        engine, _ = self._capture()
        return engine.evaluate(context)

    def evaluate_many(self, contexts: Iterable[Mapping[str, Any]]) -> tuple[Decision, ...]:
        """Evaluate one bounded batch against a single captured generation."""

        engine, _ = self._capture()
        return engine.evaluate_many(contexts)

    def explain(self, context: Mapping[str, Any]) -> PolicyExplanation:
        """Explain one context against the generation active at call capture time."""

        engine, _ = self._capture()
        return engine.explain(context)

    def activate(
        self,
        policy: Policy,
        *,
        context_contract: ContextContract | None = None,
        deployment_lock: DeploymentLock | None = None,
        expected_generation: int | None = None,
    ) -> PolicyRuntimeStatus:
        """Validate and atomically activate a complete enforcement configuration.

        ``expected_generation`` enables compare-and-swap deployment. A mismatch raises
        :class:`PolicyActivationError` and preserves the current generation.
        """

        if expected_generation is not None and (
            isinstance(expected_generation, bool)
            or not isinstance(expected_generation, int)
            or expected_generation < 1
        ):
            raise ValueError("expected_generation must be a positive integer or None")

        candidate = PolicyEngine(
            policy,
            context_contract=context_contract,
            deployment_lock=deployment_lock,
        )
        with self._lock:
            current_generation = self._status.generation
            if expected_generation is not None and expected_generation != current_generation:
                raise PolicyActivationError(
                    "policy activation generation conflict: "
                    f"expected {expected_generation}, active {current_generation}"
                )
            next_status = _status(candidate, current_generation + 1)
            self._engine = candidate
            self._status = next_status
            return next_status

    def activate_deployment(
        self,
        deployment: PolicyDeployment,
        *,
        expected_generation: int | None = None,
    ) -> PolicyRuntimeStatus:
        """Atomically activate one already parsed and internally verified deployment."""

        if not isinstance(deployment, PolicyDeployment):
            raise TypeError("deployment must be a PolicyDeployment")
        return self.activate(
            deployment.policy,
            context_contract=deployment.context_contract,
            deployment_lock=deployment.deployment_lock,
            expected_generation=expected_generation,
        )
