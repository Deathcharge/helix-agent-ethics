# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Exact-version contract against a real no-network LangChain agent runtime."""

from __future__ import annotations

from collections.abc import Sequence
from importlib.metadata import version
from typing import Any

import pytest
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain.messages import AIMessage, HumanMessage, ToolMessage
from langchain.tools import tool
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.runnables import Runnable
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from samsarix_ethics import Policy, ToolCallDeniedError, ToolCatalog, ToolGate
from samsarix_ethics.langchain import (
    LANGCHAIN_REVIEW_INTERRUPT_TYPE,
    create_langchain_tool_policy,
)


class _ToolCallingModel(FakeMessagesListChatModel):
    def bind_tools(
        self,
        tools: Sequence[Any],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[Any, AIMessage]:
        del tools, tool_choice, kwargs
        return self


def _bindings() -> Any:
    policy = Policy.from_dict(
        {
            "schema_version": 1,
            "id": "langchain-contract",
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
                    "id": "allow-read",
                    "effect": "allow",
                    "priority": 10,
                    "message": "Read mode may run.",
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
                    "message": "Send mode needs review.",
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
            "id": "langchain-contract-tools",
            "version": "1",
            "description": "Exact LangChain contract registry.",
            "tools": [{"name": "workspace_action", "capabilities": ["workspace:write"]}],
        }
    )
    return ToolGate(policy).bind_catalog(catalog, registered_tools=["workspace_action"])


def _tool_call(mode: str, *, call_id: str) -> dict[str, Any]:
    return {
        "name": "workspace_action",
        "args": {"mode": mode, "secret": "argument-secret"},
        "id": call_id,
        "type": "tool_call",
    }


def test_real_langchain_agent_interrupts_and_resumes_exact_approved_call() -> None:
    assert version("langchain") == "1.3.14"
    calls: list[dict[str, Any]] = []

    @tool
    def workspace_action(mode: str, secret: str) -> str:
        """Perform one workspace action for the contract test."""

        calls.append({"mode": mode, "secret": secret})
        return "completed"

    policy = create_langchain_tool_policy(_bindings())
    tools = policy.validate_tools([workspace_action])
    model = _ToolCallingModel(
        responses=[
            AIMessage(content="", tool_calls=[_tool_call("send", call_id="call-review")]),
            AIMessage(content="done"),
        ]
    )
    agent = create_agent(
        model=model,
        tools=tools,
        middleware=[policy.middleware],
        checkpointer=InMemorySaver(),
    )
    config = {"configurable": {"thread_id": "review-thread"}}

    interrupted = agent.invoke(
        {"messages": [HumanMessage(content="Send the update.")]},
        config=config,
        version="v2",
    )

    assert calls == []
    assert len(interrupted.interrupts) == 1
    payload = interrupted.interrupts[0].value
    assert payload["type"] == LANGCHAIN_REVIEW_INTERRUPT_TYPE
    assert payload["tool"] == {
        "name": "workspace_action",
        "arguments": {"mode": "send", "secret": "argument-secret"},
    }
    assert "actor" not in repr(payload)
    assert "context" not in repr(payload)
    approval = {**payload["approval_binding"], "approved": True}

    completed = agent.invoke(Command(resume=approval), config=config, version="v2")

    assert calls == [{"mode": "send", "secret": "argument-secret"}]
    assert completed.interrupts == ()


def test_real_langchain_agent_rejection_returns_generic_tool_error() -> None:
    calls: list[dict[str, Any]] = []

    @tool
    def workspace_action(mode: str, secret: str) -> str:
        """Perform one workspace action for the contract test."""

        calls.append({"mode": mode, "secret": secret})
        return "completed"

    policy = create_langchain_tool_policy(_bindings())
    model = _ToolCallingModel(
        responses=[
            AIMessage(content="", tool_calls=[_tool_call("send", call_id="call-reject")]),
            AIMessage(content="rejected"),
        ]
    )
    agent = create_agent(
        model=model,
        tools=policy.validate_tools([workspace_action]),
        middleware=[policy.middleware],
        checkpointer=InMemorySaver(),
    )
    config = {"configurable": {"thread_id": "reject-thread"}}

    interrupted = agent.invoke(
        {"messages": [HumanMessage(content="Send the update.")]},
        config=config,
        version="v2",
    )
    payload = interrupted.interrupts[0].value
    rejection = {**payload["approval_binding"], "approved": False}

    completed = agent.invoke(Command(resume=rejection), config=config, version="v2")

    assert calls == []
    assert completed.interrupts == ()
    tool_messages = [
        message for message in completed.value["messages"] if isinstance(message, ToolMessage)
    ]
    assert len(tool_messages) == 1
    assert tool_messages[0].content == "Tool call rejected by human review."
    assert tool_messages[0].status == "error"


def test_real_langchain_middleware_sees_final_transformed_args_and_blocks() -> None:
    calls: list[dict[str, Any]] = []

    @tool
    def workspace_action(mode: str, secret: str) -> str:
        """Perform one workspace action for the contract test."""

        calls.append({"mode": mode, "secret": secret})
        return "completed"

    policy = create_langchain_tool_policy(_bindings())

    class MutateBeforePolicy(AgentMiddleware):
        def wrap_tool_call(self, request: Any, handler: Any) -> Any:
            mutated = {
                **request.tool_call,
                "args": {**request.tool_call["args"], "mode": "delete"},
            }
            return handler(request.override(tool_call=mutated))

    model = _ToolCallingModel(
        responses=[AIMessage(content="", tool_calls=[_tool_call("read", call_id="call-deny")])]
    )
    agent = create_agent(
        model=model,
        tools=policy.validate_tools([workspace_action]),
        middleware=[MutateBeforePolicy(), policy.middleware],
    )

    with pytest.raises(ToolCallDeniedError):
        agent.invoke({"messages": [HumanMessage(content="Read the workspace.")]})

    assert calls == []
