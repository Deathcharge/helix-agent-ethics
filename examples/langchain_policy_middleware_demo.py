# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Run a no-network LangChain review interrupt with exact-call approval."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain.agents import create_agent
from langchain.messages import AIMessage, HumanMessage
from langchain.tools import tool
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.runnables import Runnable
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from samsarix_ethics import (
    Policy,
    ToolCatalog,
    ToolGate,
    create_langchain_tool_policy,
)


class _NoNetworkToolModel(FakeMessagesListChatModel):
    def bind_tools(
        self,
        tools: Sequence[Any],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[Any, AIMessage]:
        del tools, tool_choice, kwargs
        return self


policy = Policy.from_dict(
    {
        "schema_version": 1,
        "id": "langchain-demo",
        "version": "1",
        "default_effect": "deny",
        "rules": [
            {
                "id": "allow-approved-send",
                "effect": "allow",
                "priority": 1,
                "message": "An exact approved send may run.",
                "conditions": [
                    {
                        "field": "context.approval.approved",
                        "operator": "eq",
                        "value": True,
                    }
                ],
            },
            {
                "id": "review-send",
                "effect": "review",
                "priority": 10,
                "message": "Unapproved messages require review.",
                "conditions": [
                    {
                        "field": "action.arguments.operation",
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
        "id": "langchain-demo-tools",
        "version": "1",
        "description": "Trusted tools for the LangChain demo.",
        "tools": [{"name": "send_message", "capabilities": ["external:write"]}],
    }
)
bindings = ToolGate(policy).bind_catalog(catalog, registered_tools=["send_message"])
tool_policy = create_langchain_tool_policy(bindings)


@tool
def send_message(operation: str, recipient: str) -> str:
    """Send one reviewed message."""

    print(f"send_message: {operation} to {recipient}")
    return "sent"


model = _NoNetworkToolModel(
    responses=[
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "send_message",
                    "args": {"operation": "send", "recipient": "customer@example.com"},
                    "id": "call-demo-1",
                    "type": "tool_call",
                }
            ],
        ),
        AIMessage(content="done"),
    ]
)
agent = create_agent(
    model=model,
    tools=tool_policy.validate_tools([send_message]),
    middleware=[tool_policy.middleware],
    checkpointer=InMemorySaver(),
)
config = {"configurable": {"thread_id": "langchain-demo"}}
interrupted = agent.invoke(
    {"messages": [HumanMessage(content="Send the customer update.")]},
    config=config,
    version="v2",
)
payload = interrupted.interrupts[0].value
print(f"{payload['type']}: {payload['tool']['name']}")
approval = {**payload["approval_binding"], "approved": True}
agent.invoke(Command(resume=approval), config=config, version="v2")
