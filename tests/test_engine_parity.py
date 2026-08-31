"""Authorization-semantic regression checks for the exact-built-in fast paths."""

from __future__ import annotations

from collections import UserDict
from collections.abc import Mapping, Sequence
from itertools import product
from types import MappingProxyType
from typing import Any

import pytest

import samsarix_ethics.engine as implementation
from samsarix_ethics import EvaluationError, Outcome, Policy, PolicyEngine
from samsarix_ethics.validation import freeze_json_value


def _baseline_equal(left: Any, right: Any) -> bool:
    # Frozen pre-optimization algorithm from a4f0707; do not optimize this test oracle.
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return bool(left == right)
    left_array = isinstance(left, Sequence) and not isinstance(left, (str, bytes, bytearray))
    right_array = isinstance(right, Sequence) and not isinstance(right, (str, bytes, bytearray))
    if left_array or right_array:
        if not (left_array and right_array):
            return False
        return len(left) == len(right) and all(
            _baseline_equal(a, b) for a, b in zip(left, right, strict=True)
        )
    if isinstance(left, Mapping) or isinstance(right, Mapping):
        if not (isinstance(left, Mapping) and isinstance(right, Mapping)):
            return False
        return left.keys() == right.keys() and all(
            _baseline_equal(left[key], right[key]) for key in left
        )
    if type(left) is not type(right):
        return False
    return bool(left == right)


def _baseline_field(context: Mapping[str, Any], path: str) -> Any:
    value: Any = context
    for part in path.split("."):
        if not isinstance(value, Mapping) or part not in value:
            return implementation._MISSING
        value = value[part]
    return value


class Label(str):
    pass


class UnequalLabel(str):
    def __eq__(self, other: object) -> bool:
        return False


class ObservedDict(dict):
    def __init__(self, value: dict) -> None:
        super().__init__(value)
        self.events: list[tuple[str, Any]] = []

    def __contains__(self, key: object) -> bool:
        self.events.append(("contains", key))
        return super().__contains__(key)

    def __getitem__(self, key: str) -> Any:
        self.events.append(("getitem", key))
        return super().__getitem__(key)


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ("read", "read", True),
        ("read", "write", False),
        ("", "", True),
        ("é", "e\u0301", False),
        ("\U0001f642\0", "\U0001f642\0", True),
        ("x" * 65_536, "x" * 65_535 + "y", False),
        (True, 1, False),
        (False, 0.0, False),
        (1, 1.0, True),
        (None, "None", False),
        (Label("read"), "read", False),
        ("read", Label("read"), False),
        (Label("read"), Label("read"), True),
        (UnequalLabel("read"), UnequalLabel("read"), False),
        (["read", {"approved": True}], ("read", MappingProxyType({"approved": True})), True),
        (["read", {"approved": True}], ("read", MappingProxyType({"approved": 1})), False),
        ({"role": "read"}, {"role": "write"}, False),
        ({"role": "read"}, UserDict({"role": "read"}), True),
    ],
    ids=[
        "equal",
        "different",
        "empty",
        "no-unicode-normalization",
        "unicode-nul",
        "max-length",
        "bool-int",
        "bool-float",
        "numeric-equivalence",
        "null-string",
        "subclass-left",
        "subclass-right",
        "same-subclass",
        "custom-equality",
        "frozen-nested",
        "nested-bool-number",
        "different-object",
        "custom-mapping",
    ],
)
def test_equality_golden_contract(left: Any, right: Any, expected: bool) -> None:
    assert implementation._json_equal(left, right) is expected
    assert _baseline_equal(left, right) is expected


def test_bounded_generated_json_equality_matches_baseline() -> None:
    scalars = [None, False, True, 0, 1, -1, 1.0, 1.5, "", "read", "é", "e\u0301"]
    values = scalars + [[value] for value in scalars]
    values += [{"nested": [value, {"label": "read"}]} for value in scalars]
    # 36 x 36 pairs, including the immutable policy-container form on either side.
    for left, right in product(values, repeat=2):
        for actual, expected in (
            (left, right),
            (left, freeze_json_value(right)),
            (freeze_json_value(left), right),
        ):
            assert implementation._json_equal(actual, expected) is _baseline_equal(actual, expected)


@pytest.mark.parametrize("factory", [dict, UserDict, MappingProxyType, ObservedDict])
@pytest.mark.parametrize("path", ["a.b", "a.absent", "a.b.absent", "absent.b"])
def test_field_lookup_preserves_mapping_and_missing_behavior(factory: Any, path: str) -> None:
    context = factory({"a": factory({"b": "read"})})
    assert implementation._field_value(context, path) is _baseline_field(context, path)


def test_dict_subclass_lookup_observes_contains_before_getitem() -> None:
    for lookup in (implementation._field_value, _baseline_field):
        nested = ObservedDict({"b": "read"})
        context = ObservedDict({"a": nested})
        assert lookup(context, "a.b") == "read"
        assert context.events == [("contains", "a"), ("getitem", "a")]
        assert nested.events == [("contains", "b"), ("getitem", "b")]


def _policy(operator: str, expected: Any) -> Policy:
    return Policy.from_dict(
        {
            "schema_version": 1,
            "id": "hot-path-parity",
            "version": "1",
            "default_effect": "review",
            "rules": [
                {
                    "id": "allow",
                    "effect": "allow",
                    "priority": 20,
                    "conditions": [
                        {"field": "action.value", "operator": operator, "value": expected},
                    ],
                },
                {
                    "id": "deny",
                    "effect": "deny",
                    "priority": 10,
                    "conditions": [
                        {"field": "action.blocked", "operator": "eq", "value": True},
                    ],
                },
                {
                    "id": "warn",
                    "effect": "warn",
                    "conditions": [
                        {"field": "action.value", "operator": "eq", "value": "read"},
                    ],
                },
            ],
        }
    )


@pytest.mark.parametrize(
    "operator", ["eq", "neq", "in", "not_in", "contains", "not_contains", "subset_of"]
)
@pytest.mark.parametrize("blocked", [False, True])
def test_public_decisions_explanations_and_batches_match_baseline(
    operator: str, blocked: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = ["read", "list"] if operator in {"in", "not_in", "subset_of"} else "read"
    actual = ["read"] if operator in {"contains", "not_contains", "subset_of"} else "read"
    engine = PolicyEngine(_policy(operator, expected))
    contexts = [{"action": {"value": actual, "blocked": blocked}}, {"action": {"value": "write"}}]
    if operator in {"contains", "not_contains", "subset_of"}:
        contexts[1]["action"]["value"] = ["write"]

    def snapshot() -> tuple[list[dict], list[dict]]:
        decisions = [d.to_dict() for d in engine.evaluate_many(contexts)]
        for decision in decisions:
            del decision["decision_id"], decision["evaluated_at"]
        return decisions, [engine.explain(context).to_dict() for context in contexts]

    candidate = snapshot()
    assert candidate[0][0]["outcome"] == (
        "deny"
        if blocked
        else ("review" if operator in {"neq", "not_in", "not_contains"} else "allow")
    )
    monkeypatch.setattr(implementation, "_json_equal", _baseline_equal)
    monkeypatch.setattr(implementation, "_field_value", _baseline_field)
    assert snapshot() == candidate


def test_cross_field_reference_observes_mutated_input_each_time() -> None:
    engine = PolicyEngine(_policy("eq", {"$ref": "owner.operation"}))
    context = {"action": {"value": "read"}, "owner": {"operation": "read"}}
    assert engine.evaluate(context).outcome is Outcome.ALLOW
    context["owner"]["operation"] = "write"
    assert engine.evaluate(context).outcome is Outcome.REVIEW
    context["action"]["value"] = "write"
    assert engine.evaluate(context).outcome is Outcome.ALLOW
    del context["owner"]
    with pytest.raises(EvaluationError, match="references missing field"):
        engine.evaluate(context)


@pytest.mark.parametrize("explain", [False, True])
def test_earlier_deny_does_not_hide_later_evaluation_error(explain: bool) -> None:
    data = _policy("eq", "read").to_dict()
    data["rules"].insert(0, {"id": "deny-all", "effect": "deny", "conditions": []})
    data["rules"].append(
        {
            "id": "invalid",
            "effect": "deny",
            "conditions": [
                {"field": "action.value", "operator": "gt", "value": 1},
            ],
        }
    )
    engine = PolicyEngine(Policy.from_dict(data))
    with pytest.raises(EvaluationError, match="two numbers or two strings"):
        (engine.explain if explain else engine.evaluate)({"action": {"value": "read"}})
