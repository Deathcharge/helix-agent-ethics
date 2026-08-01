"""Application context contract parsing and enforcement tests."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, ValidationError  # type: ignore[import-untyped]

from samsarix_ethics import (
    CONTEXT_CONTRACT_VERSION,
    MAX_CONTEXT_CONTRACT_BYTES,
    MAX_CONTEXT_CONTRACT_FIELDS,
    ContextContract,
    ContextContractValidationError,
    ContextFieldType,
    InputValidationError,
    Outcome,
    Policy,
    PolicyEngine,
    ToolGate,
    get_context_contract_schema,
    load_context_contract,
    load_policy,
    validate_context_against_contract,
    validate_policy_context_contract,
)


def _contract_document() -> dict[str, Any]:
    return {
        "context_contract_version": 1,
        "id": "agent-action",
        "version": "1.0.0",
        "description": "Facts exposed to an agent action policy.",
        "fields": {
            "action": {"type": "object"},
            "action.operation": {"type": "string"},
            "action.capabilities": {"type": "array", "items": "string"},
            "action.risk_score": {"type": "number", "required": False},
            "context": {"type": "object"},
            "context.approved": {"type": "boolean", "required": False},
        },
    }


def _policy(*conditions: dict[str, Any]) -> Policy:
    return Policy.from_dict(
        {
            "schema_version": 1,
            "id": "contract-policy",
            "version": "1",
            "default_effect": "deny",
            "rules": [
                {
                    "id": "allow",
                    "effect": "allow",
                    "conditions": list(conditions),
                }
            ],
        }
    )


def test_contract_is_versioned_immutable_and_round_trips() -> None:
    contract = ContextContract.from_dict(_contract_document())

    assert contract.context_contract_version == CONTEXT_CONTRACT_VERSION == 1
    assert contract.fields["action.operation"].type is ContextFieldType.STRING
    assert contract.fields["action.operation"].required is True
    assert contract.fields["action.capabilities"].items is ContextFieldType.STRING
    serialized = contract.to_dict()
    assert serialized["id"] == "agent-action"
    assert serialized["fields"]["action.operation"] == {
        "type": "string",
        "required": True,
    }
    assert ContextContract.from_dict(serialized) == contract
    with pytest.raises(TypeError):
        contract.fields["new"] = contract.fields["action"]  # type: ignore[index]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda value: value.update(extra=True), "unknown fields"),
        (lambda value: value.update(context_contract_version=True), "must be 1"),
        (lambda value: value.update(id="bad id"), "context contract.id"),
        (lambda value: value.update(version=""), "context contract.version"),
        (lambda value: value.update(description=1), "description"),
        (lambda value: value.update(fields=[]), "fields must be a JSON object"),
        (
            lambda value: value["fields"].update({"bad path": {"type": "string"}}),
            "invalid dotted field path",
        ),
        (
            lambda value: value["fields"].update({"unknown": {"type": "mystery"}}),
            "must be one of",
        ),
        (
            lambda value: value["fields"].update({"unknown": {"type": "string", "x": 1}}),
            "unknown fields",
        ),
        (
            lambda value: value["fields"].update(
                {"unknown": {"type": "string", "required": "yes"}}
            ),
            "required must be a boolean",
        ),
        (
            lambda value: value["fields"].update(
                {"unknown": {"type": "string", "items": "string"}}
            ),
            "items is allowed only",
        ),
        (
            lambda value: value["fields"].update({"unknown": {"type": "array", "items": 1}}),
            "items must be one of",
        ),
        (
            lambda value: value["fields"].update({"orphan.child": {"type": "string"}}),
            "requires parent field 'orphan'",
        ),
        (
            lambda value: value["fields"].update(
                {"scalar": {"type": "string"}, "scalar.child": {"type": "string"}}
            ),
            "has non-object parent 'scalar'",
        ),
        (
            lambda value: value["fields"].update(
                {
                    "optional": {"type": "object", "required": False},
                    "optional.child": {"type": "string"},
                }
            ),
            "required context contract field 'optional.child' has optional parent 'optional'",
        ),
    ],
)
def test_contract_rejects_malformed_documents(mutate: Any, message: str) -> None:
    document = _contract_document()
    mutate(document)

    with pytest.raises(ContextContractValidationError, match=message):
        ContextContract.from_dict(document)


def test_contract_rejects_non_json_and_field_limit() -> None:
    document = _contract_document()
    document["fields"] = {
        f"field_{index}": {"type": "string"} for index in range(MAX_CONTEXT_CONTRACT_FIELDS + 1)
    }
    with pytest.raises(ContextContractValidationError, match="exceeds the limit"):
        ContextContract.from_dict(document)
    with pytest.raises(ContextContractValidationError, match="non-JSON value"):
        ContextContract.from_dict({**_contract_document(), "description": object()})
    with pytest.raises(ContextContractValidationError, match="must be a JSON object"):
        ContextContract.from_dict([])


def test_schema_accepts_contract_and_rejects_items_on_scalar() -> None:
    validator = Draft202012Validator(get_context_contract_schema())
    validator.validate(_contract_document())
    invalid = _contract_document()
    invalid["fields"]["action.operation"]["items"] = "string"

    with pytest.raises(ValidationError):
        validator.validate(invalid)


def test_runtime_contract_accepts_extra_fields_and_optional_absence() -> None:
    contract = ContextContract.from_dict(_contract_document())
    context = {
        "action": {"operation": "read", "capabilities": ["filesystem.read"], "extra": 1},
        "context": {},
        "application_extra": {"trace": "kept"},
    }

    validated = validate_context_against_contract(context, contract)

    assert validated["application_extra"]["trace"] == "kept"
    assert validated is context


@pytest.mark.parametrize(
    ("context", "message"),
    [
        (
            {"action": {"capabilities": []}, "context": {}},
            "missing required contract field 'action.operation'",
        ),
        (
            {"action": {"operation": 1, "capabilities": []}, "context": {}},
            "'action.operation' must have type 'string'",
        ),
        (
            {"action": {"operation": "read", "capabilities": [1]}, "context": {}},
            "'action.capabilities'\\[0\\] must have type 'string'",
        ),
        (
            {
                "action": {"operation": "read", "capabilities": [], "risk_score": True},
                "context": {},
            },
            "'action.risk_score' must have type 'number'",
        ),
    ],
)
def test_runtime_contract_rejects_missing_or_mistyped_facts(
    context: dict[str, Any], message: str
) -> None:
    with pytest.raises(InputValidationError, match=message):
        validate_context_against_contract(context, ContextContract.from_dict(_contract_document()))


def test_runtime_contract_type_argument_is_checked() -> None:
    with pytest.raises(TypeError, match="contract must be"):
        validate_context_against_contract({}, object())  # type: ignore[arg-type]


def test_policy_contract_accepts_supported_operator_types() -> None:
    contract = ContextContract.from_dict(_contract_document())
    policy = _policy(
        {"field": "action.operation", "operator": "starts_with", "value": "read"},
        {"field": "action.operation", "operator": "in", "value": ["read_file", "list"]},
        {"field": "action.capabilities", "operator": "contains", "value": "filesystem.read"},
        {
            "field": "action.capabilities",
            "operator": "subset_of",
            "value": ["filesystem.read", "network.read"],
        },
        {"field": "action.risk_score", "operator": "gte", "value": 1},
        {"field": "context.approved", "operator": "exists"},
    )

    validate_policy_context_contract(policy, contract)
    engine = PolicyEngine(policy, context_contract=contract)
    decision = engine.evaluate(
        {
            "action": {
                "operation": "read_file",
                "capabilities": ["filesystem.read"],
                "risk_score": 1.5,
            },
            "context": {"approved": True},
        }
    )
    assert decision.outcome is Outcome.ALLOW


@pytest.mark.parametrize(
    ("condition", "message"),
    [
        ({"field": "action.typo", "operator": "eq", "value": "read"}, "not declared"),
        (
            {
                "field": "action.operation",
                "operator": "eq",
                "value": {"$ref": "context.typo"},
            },
            "not declared",
        ),
        ({"field": "action.operation", "operator": "starts_with", "value": 1}, "string value"),
        ({"field": "context.approved", "operator": "ends_with", "value": "x"}, "string field"),
        ({"field": "context.approved", "operator": "gt", "value": 1}, "two numbers"),
        ({"field": "action.risk_score", "operator": "lte", "value": "high"}, "two numbers"),
        ({"field": "action.operation", "operator": "contains", "value": "read"}, "array field"),
        (
            {"field": "action.capabilities", "operator": "contains", "value": 1},
            "does not match array item",
        ),
        (
            {
                "field": "action.capabilities",
                "operator": "subset_of",
                "value": {"$ref": "context.approved"},
            },
            "requires an array value",
        ),
        ({"field": "context.approved", "operator": "in", "value": [1]}, "does not match"),
        ({"field": "context.approved", "operator": "eq", "value": "yes"}, "types do not match"),
        (
            {"field": "action.capabilities", "operator": "eq", "value": [1]},
            "does not match array item",
        ),
    ],
)
def test_policy_contract_rejects_incompatible_conditions(
    condition: dict[str, Any], message: str
) -> None:
    with pytest.raises(ContextContractValidationError, match=message):
        validate_policy_context_contract(
            _policy(condition), ContextContract.from_dict(_contract_document())
        )


def test_cross_field_references_validate_container_and_item_types() -> None:
    document = _contract_document()
    document["fields"].update(
        {
            "limits": {"type": "object"},
            "limits.minimum": {"type": "integer"},
            "limits.allowed": {"type": "array", "items": "string"},
            "limits.approved": {"type": "boolean"},
        }
    )
    contract = ContextContract.from_dict(document)

    validate_policy_context_contract(
        _policy(
            {
                "field": "action.risk_score",
                "operator": "gte",
                "value": {"$ref": "limits.minimum"},
            },
            {
                "field": "action.operation",
                "operator": "in",
                "value": {"$ref": "limits.allowed"},
            },
        ),
        contract,
    )
    with pytest.raises(ContextContractValidationError, match="requires an array value"):
        validate_policy_context_contract(
            _policy(
                {
                    "field": "action.operation",
                    "operator": "in",
                    "value": {"$ref": "limits.approved"},
                }
            ),
            contract,
        )


def test_engine_and_tool_gate_enforce_contract_at_the_boundary() -> None:
    contract = ContextContract.from_dict(_contract_document())
    policy = _policy({"field": "action.operation", "operator": "eq", "value": "read"})
    gate = ToolGate(policy, context_contract=contract)

    assert gate.context_contract is contract
    assert gate.bind("read").context_contract is contract
    decision = gate.evaluate("read", {}, context={})
    assert decision.outcome is Outcome.ALLOW
    with pytest.raises(ContextContractValidationError, match="not declared"):
        PolicyEngine(
            _policy({"field": "action.typo", "operator": "eq", "value": "read"}),
            context_contract=contract,
        )
    with pytest.raises(TypeError, match="context_contract"):
        PolicyEngine(policy, context_contract=object())  # type: ignore[arg-type]


def test_contract_loader_bounds_and_wraps_file_errors(tmp_path: Path, write_json: Any) -> None:
    path = write_json("context-contract.json", _contract_document())
    assert load_context_contract(path).id == "agent-action"

    oversized = tmp_path / "oversized-contract.json"
    oversized.write_bytes(b"{" + b" " * MAX_CONTEXT_CONTRACT_BYTES + b"}")
    with pytest.raises(ContextContractValidationError, match="exceeds the byte limit"):
        load_context_contract(oversized)
    with pytest.raises(ContextContractValidationError, match="cannot read context contract"):
        load_context_contract(tmp_path / "missing.json")


def test_schema_accessor_returns_a_fresh_value() -> None:
    changed = get_context_contract_schema()
    changed["title"] = "changed"

    assert get_context_contract_schema()["title"] != "changed"


def test_contract_input_document_is_not_mutated() -> None:
    document = _contract_document()
    original = deepcopy(document)

    ContextContract.from_dict(document)

    assert document == original


def test_bundled_tool_contract_validates_real_policy_and_gate() -> None:
    root = Path(__file__).parents[1]
    contract = load_context_contract(root / "examples/contracts/tool-call-context.json")
    policy = load_policy(root / "examples/policies/tool-call-baseline.json")
    gate = ToolGate(policy, context_contract=contract)

    decision = gate.evaluate("read_ticket", {}, capabilities=("resource:read",))

    assert decision.outcome is Outcome.ALLOW
