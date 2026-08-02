# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Run a no-network Pydantic AI policy review and exact approved resume."""

from __future__ import annotations

from pydantic_ai import Agent, DeferredToolRequests, FunctionToolset
from pydantic_ai.models.test import TestModel

from samsarix_ethics import (
    PYDANTIC_AI_REVIEW_METADATA_KEY,
    Policy,
    ToolCatalog,
    ToolGate,
    create_pydantic_ai_tool_policy,
)


def main() -> None:
    """Review and execute one exact Pydantic AI tool call without a model API."""

    policy = Policy.from_dict(
        {
            "schema_version": 1,
            "id": "pydantic-ai-demo",
            "version": "1",
            "default_effect": "deny",
            "rules": [
                {
                    "id": "allow-approved",
                    "effect": "allow",
                    "priority": 0,
                    "message": "An exact approved call may run.",
                    "conditions": [
                        {
                            "field": "context.approval.approved",
                            "operator": "eq",
                            "value": True,
                        }
                    ],
                },
                {
                    "id": "review-message",
                    "effect": "review",
                    "priority": 10,
                    "message": "External messages need review.",
                    "conditions": [
                        {"field": "action.operation", "operator": "eq", "value": "send_message"},
                        {"field": "context.approval", "operator": "not_exists"},
                    ],
                },
            ],
        }
    )
    catalog = ToolCatalog.from_dict(
        {
            "tool_catalog_version": 1,
            "id": "pydantic-ai-demo-tools",
            "version": "1",
            "description": "No-network Pydantic AI demo registry.",
            "tools": [{"name": "send_message", "capabilities": ["external:write"]}],
        }
    )
    bindings = ToolGate(policy).bind_catalog(catalog, registered_tools=["send_message"])
    tools = FunctionToolset()
    executed: list[str] = []

    @tools.tool_plain
    def send_message(recipient: str) -> str:
        """Send one demonstration message."""

        executed.append(recipient)
        return "sent"

    tool_policy = create_pydantic_ai_tool_policy(bindings, tools)
    agent = Agent(
        TestModel(call_tools=["send_message"]),
        toolsets=[tool_policy.toolset],
        output_type=[str, DeferredToolRequests],
    )
    first = agent.run_sync("Send the demonstration message.", conversation_id="demo")
    if not isinstance(first.output, DeferredToolRequests):
        raise RuntimeError("expected one deferred tool review")
    pending = first.output.approvals[0]
    review = first.output.metadata[pending.tool_call_id][PYDANTIC_AI_REVIEW_METADATA_KEY]
    print(f"{review['type']}: {review['tool']['name']}")

    # Authenticate and authorize the reviewer before making this application-owned decision.
    results = tool_policy.build_results(first.output, {pending.tool_call_id: True})
    agent.run_sync(
        "Continue.",
        message_history=first.all_messages(),
        deferred_tool_results=results,
        conversation_id="demo",
    )
    print(f"send_message: {executed[0]}")


if __name__ == "__main__":
    main()
