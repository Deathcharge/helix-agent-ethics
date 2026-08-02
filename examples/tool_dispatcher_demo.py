"""Bind a coherent deployment to frozen callables and dispatch one allowed call."""

from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import Any

from samsarix_ethics import (
    ToolCallDeniedError,
    ToolDispatcher,
    create_tool_gate_deployment,
    load_policy_deployment,
    load_tool_catalog,
)

ROOT = Path(__file__).parents[1]
executed: list[tuple[str, dict[str, Any]]] = []


def record_tool(tool_name: str, **arguments: Any) -> dict[str, Any]:
    """Stand in for a final framework callback without another registry lookup."""

    detached = dict(arguments)
    executed.append((tool_name, detached))
    return {"tool": tool_name, "arguments": detached}


catalog = load_tool_catalog(ROOT / "examples/catalogs/coding-agent-tools.json")
deployment = create_tool_gate_deployment(
    load_policy_deployment(ROOT / "examples/deployment/coding-agent-baseline.deployment.json"),
    catalog,
)
callbacks = {name: partial(record_tool, name) for name in catalog.tool_names}
dispatcher = ToolDispatcher.bind_deployment(deployment, registered_tools=callbacks)

result = dispatcher.execute(
    "read_file",
    {"path": "README.md"},
    actor={"id": "coding-agent"},
    context={"workspace_contained": True},
)
print(result.decision.outcome.value, result.value)

batch = [
    dispatcher.prepare(
        "read_file",
        {"path": "LICENSE"},
        actor={"id": "coding-agent"},
        context={"workspace_contained": True},
    ),
    dispatcher.prepare(
        "delete_file",
        {"path": "important.txt"},
        actor={"id": "coding-agent"},
        context={"workspace_contained": True},
    ),
]
try:
    dispatcher.execute_many(batch)
except ToolCallDeniedError as exc:
    print("batch blocked", exc.blocking_index, [item.outcome.value for item in exc.decisions])

if [name for name, _arguments in executed] != ["read_file"]:
    raise RuntimeError("blocked batch unexpectedly executed a callback")
