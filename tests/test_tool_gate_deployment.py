"""Coherent tool-gate deployment validation and binding."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from samsarix_ethics import (
    MAX_TOOL_GATE_DEPLOYMENT_BYTES,
    Outcome,
    ToolCallDeniedError,
    ToolCatalogValidationError,
    ToolGate,
    ToolGateDeployment,
    ToolGateDeploymentValidationError,
    create_tool_gate_deployment,
    get_tool_gate_deployment_schema,
    load_policy_deployment,
    load_tool_catalog,
    load_tool_gate_deployment,
    write_tool_gate_deployment,
)

_ROOT = Path(__file__).parents[1]
_POLICY_DEPLOYMENT = _ROOT / "examples/deployment/coding-agent-baseline.deployment.json"
_CATALOG = _ROOT / "examples/catalogs/coding-agent-tools.json"
_REGISTERED = {
    "delete_file",
    "fetch_url",
    "read_file",
    "read_secret",
    "run_command",
    "send_message",
    "write_file",
}


def _deployment() -> ToolGateDeployment:
    return create_tool_gate_deployment(
        load_policy_deployment(_POLICY_DEPLOYMENT),
        load_tool_catalog(_CATALOG),
    )


def test_deployment_round_trip_is_detached_and_exactly_pinned() -> None:
    deployment = _deployment()
    value = deployment.to_dict()
    parsed = ToolGateDeployment.from_dict(value)
    value["tool_catalog"]["id"] = "changed"

    assert parsed == deployment
    assert parsed.tool_catalog.id == "coding-agent-tools"
    assert parsed.tool_catalog_fingerprint.startswith("v1:sha256:")
    assert "capabilities" not in repr(parsed)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda value: value.update(tool_gate_deployment_version=True), "version must be 1"),
        (lambda value: value.update(tool_gate_deployment_version=1.0), "version must be 1"),
        (lambda value: value.pop("tool_catalog"), "is missing: tool_catalog"),
        (lambda value: value.update(extra=True), "unknown fields: extra"),
        (
            lambda value: value.update(tool_catalog_fingerprint="v1:sha256:" + "0" * 64),
            "fingerprint does not match",
        ),
        (
            lambda value: value["tool_catalog"].update(id="bad id"),
            "invalid tool catalog",
        ),
        (
            lambda value: value["policy_deployment"].update(policy_deployment_version=2),
            "invalid policy deployment",
        ),
    ],
)
def test_deployment_rejects_malformed_or_mixed_artifacts(mutate: Any, message: str) -> None:
    value = _deployment().to_dict()
    mutate(value)

    with pytest.raises(ToolGateDeploymentValidationError, match=message):
        ToolGateDeployment.from_dict(value)


def test_direct_constructor_and_factory_reject_unvalidated_types() -> None:
    deployment = _deployment()
    with pytest.raises(ToolGateDeploymentValidationError, match="PolicyDeployment"):
        ToolGateDeployment(
            1,
            object(),  # type: ignore[arg-type]
            deployment.tool_catalog,
            deployment.tool_catalog_fingerprint,
        )
    with pytest.raises(TypeError, match="policy_deployment"):
        create_tool_gate_deployment(object(), deployment.tool_catalog)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="tool_catalog"):
        create_tool_gate_deployment(deployment.policy_deployment, object())  # type: ignore[arg-type]


def test_bind_deployment_requires_complete_registry_and_enforces_catalog() -> None:
    deployment = _deployment()
    bindings = ToolGate.bind_deployment(deployment, registered_tools=_REGISTERED)

    assert bindings.catalog is deployment.tool_catalog
    assert bindings.catalog_fingerprint == deployment.tool_catalog_fingerprint
    trusted_context = {"workspace_contained": True}
    actor = {"id": "coding-agent"}
    assert (
        bindings["read_file"]
        .enforce({"path": "README.md"}, actor=actor, context=trusted_context)
        .outcome
        is Outcome.ALLOW
    )
    with pytest.raises(ToolCallDeniedError):
        bindings["delete_file"].enforce({"path": "old.log"}, actor=actor, context=trusted_context)
    with pytest.raises(TypeError, match="ToolGateDeployment"):
        ToolGate.bind_deployment(object(), registered_tools=_REGISTERED)  # type: ignore[arg-type]
    with pytest.raises(ToolCatalogValidationError, match="missing from registry"):
        ToolGate.bind_deployment(deployment, registered_tools={"read_file"})


def test_bounded_atomic_file_round_trip_and_schema(tmp_path: Path) -> None:
    deployment = _deployment()
    path = tmp_path / "gate.deployment.json"
    assert write_tool_gate_deployment(path, deployment) == path.resolve()
    assert load_tool_gate_deployment(path) == deployment
    with pytest.raises(ToolGateDeploymentValidationError, match="refusing to overwrite"):
        write_tool_gate_deployment(path, deployment)

    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b"{" + b" " * MAX_TOOL_GATE_DEPLOYMENT_BYTES + b"}")
    with pytest.raises(ToolGateDeploymentValidationError, match="byte limit"):
        load_tool_gate_deployment(oversized)

    schema = get_tool_gate_deployment_schema()
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(deployment.to_dict())
    changed = copy.deepcopy(schema)
    changed["$defs"]["tool_catalog"]["title"] = "changed"
    assert get_tool_gate_deployment_schema()["$defs"]["tool_catalog"]["title"] != "changed"


def test_loader_rejects_duplicate_keys(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text(
        json.dumps(_deployment().to_dict())[:-1] + ',"tool_gate_deployment_version":1}',
        encoding="utf-8",
    )
    with pytest.raises(ToolGateDeploymentValidationError, match="duplicate object key"):
        load_tool_gate_deployment(path)
