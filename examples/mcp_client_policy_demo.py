# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Protect outbound MCP v2 calls without network access or an LLM API key.

Install the mcp-client extra in its own environment, then run this file.
"""

from __future__ import annotations

import asyncio

from mcp import Client
from mcp.server import MCPServer

from samsarix_ethics import (
    MCPClientReviewRequest,
    Policy,
    ToolCallApproval,
    ToolCallDeniedError,
    ToolCatalog,
    ToolGate,
    create_mcp_client_tool_policy,
)


async def main() -> None:
    server = MCPServer("example-support-service")
    sent: list[str] = []

    @server.tool()
    async def get_ticket(ticket_id: str) -> str:
        return f"{ticket_id}: Customer requests a delivery update."

    @server.tool()
    async def send_reply(body: str) -> str:
        sent.append(body)
        return "reply queued"

    @server.tool()
    async def delete_ticket(ticket_id: str) -> str:
        raise RuntimeError(f"Policy should prevent deleting {ticket_id}")

    policy = Policy.from_dict(
        {
            "schema_version": 1,
            "id": "mcp-support",
            "version": "1",
            "default_effect": "deny",
            "rules": [
                {
                    "id": "deny-delete",
                    "effect": "deny",
                    "message": "Deletion is forbidden.",
                    "conditions": [
                        {
                            "field": "action.capabilities",
                            "operator": "contains",
                            "value": "destructive",
                        }
                    ],
                },
                {
                    "id": "allow-read",
                    "effect": "allow",
                    "message": "Ticket reads are allowed.",
                    "conditions": [
                        {
                            "field": "action.capabilities",
                            "operator": "contains",
                            "value": "resource:read",
                        }
                    ],
                },
                {
                    "id": "review-reply",
                    "effect": "review",
                    "message": "Review external replies.",
                    "conditions": [
                        {
                            "field": "action.capabilities",
                            "operator": "contains",
                            "value": "external:write",
                        },
                        {"field": "context.approval", "operator": "not_exists"},
                    ],
                },
                {
                    "id": "allow-approved-reply",
                    "effect": "allow",
                    "message": "This reply was reviewed.",
                    "conditions": [
                        {
                            "field": "action.capabilities",
                            "operator": "contains",
                            "value": "external:write",
                        },
                        {"field": "context.approval.approved", "operator": "eq", "value": True},
                    ],
                },
            ],
        }
    )
    # Application-authored labels. Never derive these from remote annotations or the model.
    catalog = ToolCatalog.from_dict(
        {
            "tool_catalog_version": 1,
            "id": "support-tools",
            "version": "1",
            "tools": [
                {"name": "get_ticket", "capabilities": ["resource:read"]},
                {"name": "send_reply", "capabilities": ["external:write"]},
                {"name": "delete_ticket", "capabilities": ["destructive"]},
            ],
        }
    )
    bindings = ToolGate(policy).bind_catalog(catalog, registered_tools=catalog.tool_names)

    async def review(request: MCPClientReviewRequest) -> ToolCallApproval:
        # DEMO ONLY: a fixed simulated reviewer, not authenticated human approval.
        # A real UI must authenticate the reviewer and display the complete sensitive payload.
        print(f"review requested: {request.tool_name}")
        return request.approval(approved=True)

    async with Client(server) as client:
        protected = await create_mcp_client_tool_policy(
            bindings,
            client,
            server_id="support-primary",
            actor_provider=lambda: {"id": "demo-user"},
            approval_provider=review,
        )
        print(f"pinned {len(protected.tools)} tool definitions")
        await protected.call_tool("get_ticket", {"ticket_id": "T-100"})
        print("ticket read allowed")
        await protected.call_tool("send_reply", {"body": "Your package arrives tomorrow."})
        print(f"approved replies dispatched: {len(sent)}")
        try:
            await protected.call_tool("delete_ticket", {"ticket_id": "T-100"})
        except ToolCallDeniedError:
            print("ticket deletion blocked before dispatch")
        else:
            raise RuntimeError("Deletion unexpectedly passed policy")


if __name__ == "__main__":
    asyncio.run(main())
