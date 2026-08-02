"""Immutable framework-neutral tool dispatch bindings."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from samsarix_ethics import (
    AuditRecord,
    InputValidationError,
    Outcome,
    Policy,
    ToolCallDeniedError,
    ToolCatalog,
    ToolCatalogEntry,
    ToolCatalogValidationError,
    ToolDispatcher,
    ToolGate,
    create_tool_gate_deployment,
    load_policy_deployment,
    load_tool_catalog,
)

_ROOT = Path(__file__).parents[1]


def _policy() -> Policy:
    return Policy.from_dict(
        {
            "schema_version": 1,
            "id": "dispatcher-test",
            "version": "1",
            "default_effect": "deny",
            "rules": [
                {
                    "id": "allow-reads",
                    "effect": "allow",
                    "conditions": [
                        {
                            "field": "action.capabilities",
                            "operator": "contains",
                            "value": "resource:read",
                        }
                    ],
                }
            ],
        }
    )


def _catalog() -> ToolCatalog:
    return ToolCatalog(
        tool_catalog_version=1,
        id="dispatcher-tools",
        version="1",
        description="Dispatcher test tools",
        tools=(
            ToolCatalogEntry("delete_file", ("destructive",)),
            ToolCatalogEntry("read_file", ("resource:read",)),
            ToolCatalogEntry("read_ticket", ("resource:read",)),
        ),
    )


def _callbacks(events: list[str]) -> dict[str, Any]:
    return {
        "delete_file": lambda **arguments: events.append(f"delete:{arguments['path']}"),
        "read_file": lambda **arguments: f"file:{arguments['path']}",
        "read_ticket": lambda **arguments: f"ticket:{arguments['ticket_id']}",
    }


def test_dispatcher_snapshots_callbacks_and_executes_with_keyword_arguments() -> None:
    events: list[str] = []
    callbacks = _callbacks(events)
    dispatcher = ToolDispatcher.bind_catalog(
        ToolGate(_policy()),
        _catalog(),
        registered_tools=callbacks,
    )
    callbacks["read_file"] = lambda **arguments: f"replaced:{arguments['path']}"

    result = dispatcher.execute("read_file", {"path": "README.md"})

    assert result.decision.outcome is Outcome.ALLOW
    assert result.value == "file:README.md"
    assert dispatcher.tool_names == ("delete_file", "read_file", "read_ticket")
    assert dispatcher.catalog_fingerprint.startswith("v1:sha256:")
    assert "resource:read" not in repr(dispatcher)
    assert "lambda" not in repr(dispatcher)


def test_dispatcher_fails_closed_for_unknown_denied_and_invalid_registries() -> None:
    events: list[str] = []
    gate = ToolGate(_policy())
    with pytest.raises(TypeError, match="created by bind_catalog"):
        ToolDispatcher()
    with pytest.raises(TypeError, match="gate must be a ToolGate"):
        ToolDispatcher.bind_catalog(object(), _catalog(), registered_tools=_callbacks(events))  # type: ignore[arg-type]
    with pytest.raises(ToolCatalogValidationError, match="mapping of names to callables"):
        ToolDispatcher.bind_catalog(gate, _catalog(), registered_tools=["read_file"])  # type: ignore[arg-type]
    with pytest.raises(ToolCatalogValidationError, match=r"registered tools\[0\]"):
        ToolDispatcher.bind_catalog(
            gate,
            _catalog(),
            registered_tools={1: lambda **arguments: arguments},  # type: ignore[dict-item]
        )
    with pytest.raises(ToolCatalogValidationError, match="exceed the limit"):
        ToolDispatcher.bind_catalog(
            gate,
            _catalog(),
            registered_tools={
                f"tool-{index}": (lambda **arguments: arguments) for index in range(257)
            },
        )
    bad_callbacks = _callbacks(events)
    bad_callbacks["read_file"] = None
    with pytest.raises(ToolCatalogValidationError, match="must be callable"):
        ToolDispatcher.bind_catalog(gate, _catalog(), registered_tools=bad_callbacks)
    with pytest.raises(ToolCatalogValidationError, match="missing from registry"):
        ToolDispatcher.bind_catalog(
            gate,
            _catalog(),
            registered_tools={"read_file": lambda **arguments: arguments},
        )

    dispatcher = ToolDispatcher.bind_catalog(
        gate,
        _catalog(),
        registered_tools=_callbacks(events),
    )
    with pytest.raises(InputValidationError, match="not registered"):
        dispatcher.execute("unknown", {})
    with pytest.raises(ToolCallDeniedError):
        dispatcher.execute("delete_file", {"path": "important.txt"})
    assert events == []


def test_dispatcher_binds_a_coherent_deployment() -> None:
    catalog = load_tool_catalog(_ROOT / "examples/catalogs/coding-agent-tools.json")
    deployment = create_tool_gate_deployment(
        load_policy_deployment(_ROOT / "examples/deployment/coding-agent-baseline.deployment.json"),
        catalog,
    )
    callbacks = {name: (lambda **arguments: arguments) for name in catalog.tool_names}

    dispatcher = ToolDispatcher.bind_deployment(deployment, registered_tools=callbacks)
    result = dispatcher.execute(
        "read_file",
        {"path": "README.md"},
        context={"workspace_contained": True},
    )

    assert result.value == {"path": "README.md"}
    assert dispatcher.catalog is deployment.tool_catalog
    assert dispatcher.catalog_fingerprint == deployment.tool_catalog_fingerprint


def test_dispatcher_preflights_entire_batch_before_ordered_execution() -> None:
    events: list[str] = []
    records: list[AuditRecord] = []
    dispatcher = ToolDispatcher.bind_catalog(
        ToolGate(_policy(), audit_sink=records.append),
        _catalog(),
        registered_tools=_callbacks(events),
    )
    blocked = [
        dispatcher.prepare("read_file", {"path": "README.md"}),
        dispatcher.prepare("delete_file", {"path": "important.txt"}),
    ]

    with pytest.raises(ToolCallDeniedError) as caught:
        dispatcher.execute_many(blocked)

    assert caught.value.blocking_index == 1
    assert [record.outcome for record in records] == [Outcome.ALLOW, Outcome.DENY]
    assert events == []

    records.clear()
    allowed = [
        dispatcher.prepare("read_file", {"path": "README.md"}),
        dispatcher.prepare("read_ticket", {"ticket_id": "T-100"}),
    ]
    results = dispatcher.execute_many(allowed)
    assert [result.value for result in results] == ["file:README.md", "ticket:T-100"]
    assert all(result.decision.outcome is Outcome.ALLOW for result in results)
    assert len(records) == 2


def test_dispatcher_rejects_foreign_repeated_and_unbound_batches() -> None:
    records: list[AuditRecord] = []
    dispatcher = ToolDispatcher.bind_catalog(
        ToolGate(_policy(), audit_sink=records.append),
        _catalog(),
        registered_tools=_callbacks([]),
    )
    foreign = ToolGate(_policy()).prepare(
        "read_file", {"path": "README.md"}, capabilities=["resource:read"]
    )
    call = dispatcher.prepare("read_file", {"path": "README.md"})
    uncataloged = dispatcher.bindings.gate.prepare(
        "uncataloged", {"path": "README.md"}, capabilities=["resource:read"]
    )
    relabeled = dispatcher.bindings.gate.prepare(
        "read_file", {"path": "README.md"}, capabilities=["destructive"]
    )

    with pytest.raises(InputValidationError, match="different ToolGate"):
        dispatcher.execute_many([foreign])
    with pytest.raises(InputValidationError, match="repeats a PreparedToolCall"):
        dispatcher.execute_many([call, call])
    with pytest.raises(InputValidationError, match="not registered in this dispatcher"):
        dispatcher.execute_many([uncataloged])
    with pytest.raises(InputValidationError, match="does not match dispatcher capabilities"):
        dispatcher.execute_many([relabeled])
    with pytest.raises(InputValidationError, match="batch must be iterable"):
        dispatcher.execute_many(None)  # type: ignore[arg-type]
    with pytest.raises(InputValidationError, match="batch must be iterable"):
        dispatcher.execute_many("not-a-batch")  # type: ignore[arg-type]
    with pytest.raises(InputValidationError, match="must be a PreparedToolCall"):
        dispatcher.execute_many([object()])  # type: ignore[list-item]
    with pytest.raises(InputValidationError, match="exceeds the limit"):
        dispatcher.execute_many(object() for _index in range(1_001))  # type: ignore[arg-type]
    assert records == []


def test_dispatcher_detects_awaitables_on_sync_path() -> None:
    async def read_file(*, path: str) -> str:
        return path

    callbacks = _callbacks([])
    callbacks["read_file"] = read_file
    dispatcher = ToolDispatcher.bind_catalog(
        ToolGate(_policy()),
        _catalog(),
        registered_tools=callbacks,
    )

    with pytest.raises(TypeError, match="returned an awaitable"):
        dispatcher.execute("read_file", {"path": "README.md"})


def test_dispatcher_executes_async_calls_and_batches() -> None:
    events: list[str] = []

    async def read_file(*, path: str) -> str:
        await asyncio.sleep(0)
        events.append(path)
        return f"file:{path}"

    async def read_ticket(*, ticket_id: str) -> str:
        await asyncio.sleep(0)
        events.append(ticket_id)
        return f"ticket:{ticket_id}"

    callbacks = _callbacks(events)
    callbacks["read_file"] = read_file
    callbacks["read_ticket"] = read_ticket
    dispatcher = ToolDispatcher.bind_catalog(
        ToolGate(_policy()),
        _catalog(),
        registered_tools=callbacks,
    )

    single = asyncio.run(dispatcher.execute_async("read_file", {"path": "README.md"}))
    batch = asyncio.run(
        dispatcher.execute_many_async(
            [
                dispatcher.prepare("read_file", {"path": "LICENSE"}),
                dispatcher.prepare("read_ticket", {"ticket_id": "T-200"}),
            ]
        )
    )

    assert single.value == "file:README.md"
    assert [result.value for result in batch] == ["file:LICENSE", "ticket:T-200"]
    assert events == ["README.md", "LICENSE", "T-200"]


def test_async_path_rejects_plain_return_values() -> None:
    dispatcher = ToolDispatcher.bind_catalog(
        ToolGate(_policy()),
        _catalog(),
        registered_tools=_callbacks([]),
    )

    with pytest.raises(TypeError, match="must return an awaitable"):
        asyncio.run(dispatcher.execute_async("read_file", {"path": "README.md"}))
