"""Real no-network contract tests for the stable MCP Python SDK."""

from __future__ import annotations

from typing import Any

import anyio
import pytest
from mcp.server.lowlevel import Server
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import Tool

from samsarix_ethics import (
    MCPToolReviewRequest,
    Policy,
    ToolCallApproval,
    ToolCatalog,
    ToolCatalogValidationError,
    ToolGate,
    create_mcp_server_tool_policy,
)


def _bindings() -> Any:
    policy = Policy.from_dict(
        {
            "schema_version": 1,
            "id": "mcp-contract",
            "version": "1",
            "default_effect": "deny",
            "rules": [
                {
                    "id": "deny-delete",
                    "effect": "deny",
                    "priority": 0,
                    "message": "Delete is forbidden.",
                    "conditions": [
                        {
                            "field": "action.arguments.mode",
                            "operator": "eq",
                            "value": "delete",
                        }
                    ],
                },
                {
                    "id": "allow-approved",
                    "effect": "allow",
                    "priority": 1,
                    "message": "An approved exact call may run.",
                    "conditions": [
                        {
                            "field": "context.approval.approved",
                            "operator": "eq",
                            "value": True,
                        }
                    ],
                },
                {
                    "id": "allow-read",
                    "effect": "allow",
                    "priority": 10,
                    "message": "Read mode is allowed.",
                    "conditions": [
                        {
                            "field": "action.arguments.mode",
                            "operator": "eq",
                            "value": "read",
                        }
                    ],
                },
                {
                    "id": "review-send",
                    "effect": "review",
                    "priority": 20,
                    "message": "Sending requires review.",
                    "conditions": [
                        {
                            "field": "action.arguments.mode",
                            "operator": "eq",
                            "value": "send",
                        },
                        {
                            "field": "context.approval",
                            "operator": "not_exists",
                        },
                    ],
                },
            ],
        }
    )
    catalog = ToolCatalog.from_dict(
        {
            "tool_catalog_version": 1,
            "id": "mcp-contract-tools",
            "version": "1",
            "tools": [
                {"name": "read_file", "capabilities": ["resource:read"]},
                {"name": "send_message", "capabilities": ["external:write"]},
            ],
        }
    )
    return ToolGate(policy).bind_catalog(
        catalog,
        registered_tools=["read_file", "send_message"],
    )


def _tools() -> list[Tool]:
    schema = {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["read", "send", "delete"]},
            "value": {"type": "string"},
        },
        "required": ["mode"],
        "additionalProperties": False,
    }
    return [
        Tool(name="read_file", description="Read a file", inputSchema=schema),
        Tool(name="send_message", description="Send a message", inputSchema=schema),
    ]


def _server(*, approve_review: bool | None) -> tuple[Server[Any], list[Any], list[Any]]:
    server: Server[Any] = Server("samsarix-mcp-contract")
    calls: list[tuple[str, dict[str, Any]]] = []
    reviews: list[MCPToolReviewRequest] = []

    async def handler(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        calls.append((name, arguments))
        return {"tool": name, "value": arguments.get("value")}

    async def approval_provider(
        request_context: Any,
        review: MCPToolReviewRequest,
    ) -> ToolCallApproval:
        assert request_context is server.request_context
        reviews.append(review)
        return review.approval(approved=bool(approve_review))

    adapter = create_mcp_server_tool_policy(
        _bindings(),
        _tools(),
        handler,
        application_context_provider=lambda: server.request_context,
        actor_provider=lambda _request_context: {"id": "mcp-user"},
        context_provider=lambda _request_context: {"tenant": "contract"},
        approval_provider=approval_provider if approve_review is not None else None,
    )

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return list(adapter.tools)

    server.call_tool()(adapter.call_tool)
    return server, calls, reviews


def test_real_server_enforces_allow_deny_review_schema_and_registry() -> None:
    server, calls, reviews = _server(approve_review=True)

    async def scenario() -> None:
        async with create_connected_server_and_client_session(server) as client:
            listed = await client.list_tools()
            assert [tool.name for tool in listed.tools] == ["read_file", "send_message"]

            allowed = await client.call_tool("read_file", {"mode": "read", "value": "a"})
            assert allowed.isError is False
            assert allowed.structuredContent == {"tool": "read_file", "value": "a"}

            denied = await client.call_tool("send_message", {"mode": "delete"})
            assert denied.isError is True

            approved = await client.call_tool("send_message", {"mode": "send", "value": "b"})
            assert approved.isError is False
            assert approved.structuredContent == {"tool": "send_message", "value": "b"}

            invalid = await client.call_tool("read_file", {"value": "missing-mode"})
            assert invalid.isError is True

            unknown = await client.call_tool("not_registered", {})
            assert unknown.isError is True

    anyio.run(scenario)
    assert calls == [
        ("read_file", {"mode": "read", "value": "a"}),
        ("send_message", {"mode": "send", "value": "b"}),
    ]
    assert len(reviews) == 1
    assert reviews[0].arguments == {"mode": "send", "value": "b"}


def test_real_server_review_without_provider_fails_closed() -> None:
    server, calls, reviews = _server(approve_review=None)

    async def scenario() -> None:
        async with create_connected_server_and_client_session(server) as client:
            result = await client.call_tool("send_message", {"mode": "send"})
            assert result.isError is True

    anyio.run(scenario)
    assert calls == []
    assert reviews == []


def test_real_server_rejected_review_fails_closed() -> None:
    server, calls, reviews = _server(approve_review=False)

    async def scenario() -> None:
        async with create_connected_server_and_client_session(server) as client:
            result = await client.call_tool("send_message", {"mode": "send"})
            assert result.isError is True

    anyio.run(scenario)
    assert calls == []
    assert len(reviews) == 1


def test_real_sdk_registry_drift_is_rejected_before_server_start() -> None:
    async def handler(_name: str, _arguments: dict[str, Any]) -> dict[str, Any]:
        return {}

    with pytest.raises(ToolCatalogValidationError):
        create_mcp_server_tool_policy(
            _bindings(),
            _tools()[:1],
            handler,
        )
