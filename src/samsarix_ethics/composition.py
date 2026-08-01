# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Deterministic central composition of validated policy sources."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from ._policy_payload import serialize_policy_document
from .errors import PolicyCompositionError, PolicyValidationError
from .models import MAX_POLICY_RULES, Policy
from .provenance import fingerprint_policy

POLICY_COMPOSITION_VERSION = 1
MAX_COMPOSED_POLICIES = 32


@dataclass(frozen=True, slots=True)
class PolicyCompositionSource:
    """Value-minimized provenance for one source in declaration order."""

    policy_id: str
    policy_version: str
    policy_fingerprint: str
    rule_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "policy_fingerprint": self.policy_fingerprint,
            "rule_count": self.rule_count,
        }


@dataclass(frozen=True, slots=True)
class PolicyComposition:
    """One composed policy plus a value-minimized provenance report."""

    policy: Policy
    sources: tuple[PolicyCompositionSource, ...]
    composition_version: int = POLICY_COMPOSITION_VERSION

    @property
    def policy_fingerprint(self) -> str:
        return fingerprint_policy(self.policy)

    def to_dict(self) -> dict[str, Any]:
        """Return source provenance without copying rules, conditions, or messages."""

        return {
            "composition_version": self.composition_version,
            "policy_id": self.policy.id,
            "policy_version": self.policy.version,
            "policy_fingerprint": self.policy_fingerprint,
            "default_effect": self.policy.default_effect.value,
            "source_count": len(self.sources),
            "total_rules": len(self.policy.rules),
            "sources": [source.to_dict() for source in self.sources],
        }


def compose_policies(
    policies: Iterable[Policy],
    *,
    policy_id: str,
    policy_version: str,
    description: str = "",
) -> PolicyComposition:
    """Compose ordered policy sources that share one default and unique rule IDs.

    Source order is preserved. Existing engine precedence applies across the resulting
    rule set, so any matching deny overrides review and allow. All sources must share
    one default effect because applying independent defaults during aggregation would
    change the meaning of their rules.
    """

    if isinstance(policies, (str, bytes, bytearray)):
        raise TypeError("policies must be an iterable of Policy values")
    try:
        iterator = iter(policies)
    except TypeError as exc:
        raise TypeError("policies must be an iterable of Policy values") from exc

    sources: list[Policy] = []
    for index, policy in enumerate(iterator):
        if index >= MAX_COMPOSED_POLICIES:
            raise PolicyCompositionError(
                f"policy composition exceeds the limit of {MAX_COMPOSED_POLICIES} sources"
            )
        if not isinstance(policy, Policy):
            raise TypeError(f"policies[{index}] must be a Policy")
        sources.append(policy)
    if not sources:
        raise PolicyCompositionError("policy composition requires at least one source")

    source_ids = [source.id for source in sources]
    duplicate_source_ids = sorted(
        {source_id for source_id in source_ids if source_ids.count(source_id) > 1}
    )
    if duplicate_source_ids:
        raise PolicyCompositionError(
            "policy composition has duplicate source ids: " + ", ".join(duplicate_source_ids)
        )

    default_effect = sources[0].default_effect
    mismatched_defaults = [
        f"{source.id}@{source.version}={source.default_effect.value}"
        for source in sources
        if source.default_effect is not default_effect
    ]
    if mismatched_defaults:
        raise PolicyCompositionError(
            f"policy sources must share default_effect={default_effect.value}; mismatched: "
            + ", ".join(mismatched_defaults)
        )

    rule_owners: dict[str, list[str]] = {}
    for source in sources:
        for rule in source.rules:
            rule_owners.setdefault(rule.id, []).append(source.id)
    duplicate_rules = sorted(rule_id for rule_id, owners in rule_owners.items() if len(owners) > 1)
    if duplicate_rules:
        details = ", ".join(
            f"{rule_id} ({'/'.join(rule_owners[rule_id])})" for rule_id in duplicate_rules
        )
        raise PolicyCompositionError(f"policy composition has duplicate rule ids: {details}")

    total_rules = sum(len(source.rules) for source in sources)
    if total_rules > MAX_POLICY_RULES:
        raise PolicyCompositionError(
            f"composed policy.rules exceeds the limit of {MAX_POLICY_RULES}"
        )

    try:
        policy = Policy.from_dict(
            {
                "schema_version": 1,
                "id": policy_id,
                "version": policy_version,
                "description": description,
                "default_effect": default_effect.value,
                "rules": [rule.to_dict() for source in sources for rule in source.rules],
            }
        )
    except (TypeError, PolicyValidationError) as exc:
        raise PolicyCompositionError(f"invalid composed policy metadata: {exc}") from exc

    try:
        serialize_policy_document(policy.to_dict(), label="composed policy")
    except PolicyValidationError as exc:
        raise PolicyCompositionError(str(exc)) from exc

    provenance = tuple(
        PolicyCompositionSource(
            policy_id=source.id,
            policy_version=source.version,
            policy_fingerprint=fingerprint_policy(source),
            rule_count=len(source.rules),
        )
        for source in sources
    )
    return PolicyComposition(policy=policy, sources=provenance)
