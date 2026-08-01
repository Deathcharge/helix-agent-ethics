"""Deterministic layered policy composition."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from samsarix_ethics import (
    MAX_COMPOSED_POLICIES,
    POLICY_COMPOSITION_VERSION,
    Outcome,
    Policy,
    PolicyCompositionError,
    PolicyEngine,
    compose_policies,
    fingerprint_policy,
)


def _policy(
    policy_id: str,
    *rules: dict[str, Any],
    default_effect: str = "deny",
    version: str = "1",
) -> Policy:
    return Policy.from_dict(
        {
            "schema_version": 1,
            "id": policy_id,
            "version": version,
            "description": f"Description for {policy_id} with private detail.",
            "default_effect": default_effect,
            "rules": list(rules),
        }
    )


def _rule(rule_id: str, effect: str = "allow", value: str = "read") -> dict[str, Any]:
    return {
        "id": rule_id,
        "effect": effect,
        "message": f"Message for {rule_id} with private detail.",
        "conditions": [{"field": "action.operation", "operator": "eq", "value": value}],
    }


def test_compose_policies_preserves_order_semantics_and_minimized_provenance() -> None:
    guardrails = _policy("organization-guardrails", _rule("deny-delete", "deny", "delete"))
    permissions = _policy(
        "support-permissions",
        _rule("allow-read"),
        _rule("review-email", "review", "send_email"),
    )

    composition = compose_policies(
        [guardrails, permissions],
        policy_id="support-agent",
        policy_version="2026-08-01",
        description="Organization guardrails plus support permissions.",
    )
    policy = composition.policy
    report = composition.to_dict()
    engine = PolicyEngine(policy)

    assert composition.composition_version == POLICY_COMPOSITION_VERSION == 1
    assert [rule.id for rule in policy.rules] == ["deny-delete", "allow-read", "review-email"]
    assert policy.default_effect is Outcome.DENY
    assert engine.evaluate({"action": {"operation": "read"}}).outcome is Outcome.ALLOW
    assert engine.evaluate({"action": {"operation": "delete"}}).outcome is Outcome.DENY
    assert engine.evaluate({"action": {"operation": "send_email"}}).outcome is Outcome.REVIEW
    assert engine.evaluate({"action": {"operation": "unknown"}}).outcome is Outcome.DENY
    assert report["policy_fingerprint"] == fingerprint_policy(policy)
    assert report["source_count"] == 2
    assert report["total_rules"] == 3
    assert [source["policy_id"] for source in report["sources"]] == [
        "organization-guardrails",
        "support-permissions",
    ]
    assert report["sources"][0]["policy_fingerprint"] == fingerprint_policy(guardrails)
    serialized = json.dumps(report)
    assert "private detail" not in serialized
    assert "action.operation" not in serialized
    assert '"read"' not in serialized


def test_composition_is_deterministic_frozen_and_serialization_is_detached() -> None:
    first = _policy("first", _rule("allow-read"))
    second = _policy("second", _rule("deny-delete", "deny", "delete"))
    composition = compose_policies((first, second), policy_id="combined", policy_version="1")
    repeated = compose_policies((first, second), policy_id="combined", policy_version="1")
    reversed_composition = compose_policies(
        (second, first), policy_id="combined", policy_version="1"
    )
    report = composition.to_dict()

    assert composition.policy == repeated.policy
    assert composition.to_dict() == repeated.to_dict()
    assert composition.policy_fingerprint != reversed_composition.policy_fingerprint
    report["sources"].clear()
    assert len(composition.sources) == 2
    with pytest.raises(FrozenInstanceError):
        composition.sources = ()  # type: ignore[misc]


def test_compose_policies_rejects_ambiguous_sources() -> None:
    first = _policy("same", _rule("one"))
    duplicate_source = _policy("same", _rule("two"), version="2")
    different_default = _policy("review-default", _rule("three"), default_effect="review")
    duplicate_rule = _policy("other", _rule("one", "deny", "delete"))

    with pytest.raises(PolicyCompositionError, match="at least one"):
        compose_policies([], policy_id="combined", policy_version="1")
    with pytest.raises(PolicyCompositionError, match="duplicate source ids: same"):
        compose_policies([first, duplicate_source], policy_id="combined", policy_version="1")
    with pytest.raises(PolicyCompositionError, match="must share default_effect=deny"):
        compose_policies([first, different_default], policy_id="combined", policy_version="1")
    with pytest.raises(PolicyCompositionError, match=r"duplicate rule ids: one \(same/other\)"):
        compose_policies([first, duplicate_rule], policy_id="combined", policy_version="1")


def test_compose_policies_enforces_source_and_aggregate_rule_limits() -> None:
    source = _policy("source", _rule("allow-read"))
    too_many_sources = (source for _ in range(MAX_COMPOSED_POLICIES + 1))
    first = _policy("first", *(_rule(f"first-{index}") for index in range(600)))
    second = _policy("second", *(_rule(f"second-{index}") for index in range(401)))

    with pytest.raises(PolicyCompositionError, match="limit of 32 sources"):
        compose_policies(too_many_sources, policy_id="combined", policy_version="1")
    with pytest.raises(PolicyCompositionError, match="exceeds the limit of 1000"):
        compose_policies([first, second], policy_id="combined", policy_version="1")


def test_compose_policies_rejects_an_output_the_standard_loader_cannot_read() -> None:
    large_value = "x" * 65_536
    first = _policy(
        "first",
        *(_rule(f"first-{index}", value=large_value) for index in range(9)),
    )
    second = _policy(
        "second",
        *(_rule(f"second-{index}", value=large_value) for index in range(9)),
    )

    with pytest.raises(PolicyCompositionError, match="byte limit of 1048576"):
        compose_policies([first, second], policy_id="combined", policy_version="1")


def test_compose_policies_rejects_wrong_public_types_and_target_metadata() -> None:
    source = _policy("source", _rule("allow-read"))

    with pytest.raises(TypeError, match="iterable of Policy"):
        compose_policies(None, policy_id="combined", policy_version="1")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="iterable of Policy"):
        compose_policies("not-policies", policy_id="combined", policy_version="1")
    with pytest.raises(TypeError, match=r"policies\[0\] must be a Policy"):
        compose_policies([object()], policy_id="combined", policy_version="1")  # type: ignore[list-item]
    with pytest.raises(PolicyCompositionError, match="invalid composed policy metadata"):
        compose_policies([source], policy_id="bad id", policy_version="1")
    with pytest.raises(PolicyCompositionError, match="invalid composed policy metadata"):
        compose_policies([source], policy_id="combined", policy_version="1", description="x" * 1001)
