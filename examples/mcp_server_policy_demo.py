"""Run a no-network MCP client/server session through Samsarix policy."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import anyio
from mcp.server.lowlevel import Server
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import Tool

from samsarix_ethics import (
    MCPToolReviewRequest,
    PolicyRuntime,
    ToolCallApproval,
    ToolCatalog,
    ToolGate,
    create_mcp_server_tool_policy,
    load_policy_deployment,
    load_tool_catalog,
)

ROOT = Path(__file__).parent


async def main() -> None:
    deployment = load_policy_deployment(ROOT / "deployment/coding-agent-baseline.deployment.json")
    catalog = load_tool_catalog(ROOT / "catalogs/coding-agent-tools.json")
    read_entry = next(entry for entry in catalog.tools if entry.name == "read_file")
    demo_catalog = ToolCatalog.from_dict(
        {
            "tool_catalog_version": 1,
            "id": "mcp-demo-tools",
            "version": "1",
            "tools": [read_entry.to_dict()],
        }
    )
    tool = Tool(
        name="read_file",
        description="Read one workspace file",
        inputSchema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    )
    bindings = ToolGate(PolicyRuntime.from_deployment(deployment)).bind_catalog(
        demo_catalog,
        registered_tools=["read_file"],
    )
    server: Server[Any] = Server("samsarix-policy-demo")

    async def handler(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return {"executed": name, "path": arguments["path"]}

    async def approve(
        _request_context: Any,
        review: MCPToolReviewRequest,
    ) -> ToolCallApproval:
        return review.approval(approved=True)

    adapter = create_mcp_server_tool_policy(
        bindings,
        [tool],
        handler,
        application_context_provider=lambda: server.request_context,
        actor_provider=lambda _request_context: {"id": "demo-user"},
        context_provider=lambda _request_context: {"workspace_contained": True},
        approval_provider=approve,
    )

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return list(adapter.tools)

    server.call_tool()(adapter.call_tool)
    async with create_connected_server_and_client_session(server) as client:
        result = await client.call_tool("read_file", {"path": "README.md"})
        if result.isError:
            raise AssertionError(f"the policy-protected MCP call must succeed: {result.content}")
        print(result.structuredContent)


if __name__ == "__main__":
    anyio.run(main)
