# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Exact-version contract against a real no-network Pydantic AI agent."""

from __future__ import annotations

from importlib.metadata import version
from typing import Any

import pytest
from pydantic_ai import Agent, DeferredToolRequests, FunctionToolset
from pydantic_ai.messages import ModelMessagesTypeAdapter
from pydantic_ai.models.test import TestModel

from samsarix_ethics import (
    PYDANTIC_AI_REVIEW_METADATA_KEY,
    Policy,
    PydanticAIIntegrationError,
    ToolCallDeniedError,
    ToolCatalog,
    ToolCatalogValidationError,
    ToolGate,
    create_pydantic_ai_tool_policy,
)


def _bindings(*, deny: bool = False) -> Any:
    deny_rules = (
        [
            {
                "id": "deny-recipient",
                "effect": "deny",
                "priority": -1,
                "message": "This recipient is blocked.",
                "conditions": [
                    {
                        "field": "action.arguments.recipient",
                        "operator": "eq",
                        "value": "a",
                    }
                ],
            }
        ]
        if deny
        else []
    )
    policy = Policy.from_dict(
        {
            "schema_version": 1,
            "id": "pydantic-ai-contract",
            "version": "1",
            "default_effect": "deny",
            "rules": [
                *deny_rules,
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
                    "id": "review-send",
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
            "id": "pydantic-ai-contract-tools",
            "version": "1",
            "description": "Exact Pydantic AI contract registry.",
            "tools": [{"name": "send_message", "capabilities": ["external:write"]}],
        }
    )
    return ToolGate(policy).bind_catalog(catalog, registered_tools=["send_message"])


def _agent(calls: list[str], *, deny: bool = False) -> tuple[Agent[Any, Any], Any]:
    tools = FunctionToolset()

    @tools.tool_plain
    def send_message(recipient: str) -> str:
        calls.append(recipient)
        return "sent"

    policy = create_pydantic_ai_tool_policy(_bindings(deny=deny), tools)
    agent = Agent(
        TestModel(call_tools=["send_message"]),
        toolsets=[policy.toolset],
        output_type=[str, DeferredToolRequests],
    )
    return agent, policy


def test_real_agent_approves_exact_deferred_call_once() -> None:
    assert version("pydantic-ai-slim") == "2.22.0"
    calls: list[str] = []
    agent, policy = _agent(calls)

    first = agent.run_sync("Send the update.", conversation_id="approval-contract")

    assert isinstance(first.output, DeferredToolRequests)
    assert calls == []
    assert len(first.output.approvals) == 1
    pending = first.output.approvals[0]
    review = first.output.metadata[pending.tool_call_id][PYDANTIC_AI_REVIEW_METADATA_KEY]
    assert review["tool"] == {
        "name": "send_message",
        "arguments": {"recipient": "a"},
    }
    results = policy.build_results(first.output, {pending.tool_call_id: True})
    serialized_history = ModelMessagesTypeAdapter.dump_json(first.all_messages())
    restored_history = ModelMessagesTypeAdapter.validate_json(serialized_history)

    completed = agent.run_sync(
        "Continue.",
        message_history=restored_history,
        deferred_tool_results=results,
        conversation_id="approval-contract",
    )

    assert not isinstance(completed.output, DeferredToolRequests)
    assert calls == ["a"]

    with pytest.raises(PydanticAIIntegrationError, match="already consumed"):
        agent.run_sync(
            "Continue.",
            message_history=restored_history,
            deferred_tool_results=results,
            conversation_id="approval-contract-replay",
        )
    assert calls == ["a"]


def test_real_agent_deny_never_calls_tool() -> None:
    calls: list[str] = []
    agent, _policy = _agent(calls, deny=True)

    with pytest.raises(ToolCallDeniedError):
        agent.run_sync("Send the blocked update.", conversation_id="deny-contract")

    assert calls == []


def test_real_agent_rejection_never_calls_tool() -> None:
    calls: list[str] = []
    agent, policy = _agent(calls)
    first = agent.run_sync("Send the update.", conversation_id="rejection-contract")
    assert isinstance(first.output, DeferredToolRequests)
    pending = first.output.approvals[0]
    results = policy.build_results(first.output, {pending.tool_call_id: False})

    completed = agent.run_sync(
        "Continue.",
        message_history=first.all_messages(),
        deferred_tool_results=results,
        conversation_id="rejection-contract",
    )

    assert not isinstance(completed.output, DeferredToolRequests)
    assert calls == []


def test_real_agent_rejects_native_approval_without_samsarix_evidence() -> None:
    calls: list[str] = []
    agent, _policy = _agent(calls)
    first = agent.run_sync("Send the update.", conversation_id="forged-contract")
    assert isinstance(first.output, DeferredToolRequests)
    pending = first.output.approvals[0]
    forged = first.output.build_results(approvals={pending.tool_call_id: True})

    with pytest.raises(PydanticAIIntegrationError, match="approval metadata"):
        agent.run_sync(
            "Continue.",
            message_history=first.all_messages(),
            deferred_tool_results=forged,
            conversation_id="forged-contract",
        )
    assert calls == []


def test_real_agent_rejects_registry_added_after_binding() -> None:
    calls: list[str] = []
    tools = FunctionToolset()

    @tools.tool_plain
    def send_message(recipient: str) -> str:
        calls.append(recipient)
        return "sent"

    policy = create_pydantic_ai_tool_policy(_bindings(), tools)

    @tools.tool_plain
    def uncataloged_tool(value: str) -> str:
        return value

    agent = Agent(TestModel(call_tools=["send_message"]), toolsets=[policy.toolset])
    with pytest.raises(ToolCatalogValidationError, match="missing from catalog"):
        agent.run_sync("Send the update.")
    assert calls == []
