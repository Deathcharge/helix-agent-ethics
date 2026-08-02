# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Exact-version contract test against the real OpenAI Agents SDK."""

from __future__ import annotations

import asyncio

from agents import Agent, FunctionTool, function_tool
from agents.items import ToolApprovalItem
from agents.run_context import RunContextWrapper
from agents.tool_context import ToolContext
from agents.tool_guardrails import ToolInputGuardrailData
from openai.types.responses import ResponseFunctionToolCall

from samsarix_ethics import Policy, ToolGate, create_openai_agents_tool_policy


def test_real_sdk_function_tool_is_protected_before_pydantic_coercion() -> None:
    policy = Policy.from_dict(
        {
            "schema_version": 1,
            "id": "openai-agents-contract",
            "version": "1",
            "default_effect": "deny",
            "rules": [
                {
                    "id": "allow-approved",
                    "effect": "allow",
                    "priority": 1,
                    "message": "An approved exact transfer may run.",
                    "conditions": [
                        {
                            "field": "context.approval.approved",
                            "operator": "eq",
                            "value": True,
                        }
                    ],
                },
                {
                    "id": "review-large-transfer",
                    "effect": "review",
                    "priority": 5,
                    "message": "Large transfers require review.",
                    "conditions": [
                        {
                            "field": "action.arguments.amount",
                            "operator": "gt",
                            "value": 100,
                        },
                        {
                            "field": "context.approval",
                            "operator": "not_exists",
                        },
                    ],
                },
                {
                    "id": "allow-positive-transfer",
                    "effect": "allow",
                    "message": "Positive integer transfers are allowed for this contract test.",
                    "conditions": [
                        {
                            "field": "action.arguments.amount",
                            "operator": "gt",
                            "value": 0,
                        }
                    ],
                },
            ],
        }
    )
    binding = ToolGate(policy).bind("transfer", capabilities=["external:write"])

    @function_tool(strict_mode=True)
    def transfer(amount: int) -> int:
        """Return the amount that reached the function callback."""

        return amount

    adapter = create_openai_agents_tool_policy(binding)
    protected = adapter.protect(transfer)
    assert isinstance(protected, FunctionTool)
    assert protected is not transfer
    assert transfer.tool_input_guardrails is None
    assert protected.tool_input_guardrails is not None

    async def exercise() -> None:
        run_context = ToolContext(
            context={},
            tool_name="transfer",
            tool_call_id="call-1",
            tool_arguments='{"amount":1}',
        )
        data = ToolInputGuardrailData(context=run_context, agent=Agent(name="contract"))
        allowed = await protected.tool_input_guardrails[-1].run(data)
        assert allowed.behavior == {"type": "allow"}
        assert await protected.on_invoke_tool(run_context, '{"amount":1}') == 1

        coercible_context = ToolContext(
            context={},
            tool_name="transfer",
            tool_call_id="call-2",
            tool_arguments='{"amount":"1"}',
        )
        coercible_data = ToolInputGuardrailData(
            context=coercible_context,
            agent=Agent(name="contract"),
        )
        blocked = await protected.tool_input_guardrails[-1].run(coercible_data)
        assert blocked.behavior == {"type": "raise_exception"}
        # The SDK runner enforces the guardrail result. Calling the callback
        # directly bypasses that runner boundary by design.
        assert await protected.on_invoke_tool(coercible_context, '{"amount":"1"}') == 1

        review_call_id = "call-review"
        review_arguments = '{"amount":1000}'
        assert await protected.needs_approval(
            RunContextWrapper(context={}),
            {"amount": 1000},
            review_call_id,
        )
        approval_agent = Agent(name="contract")
        approval_call = ResponseFunctionToolCall(
            arguments=review_arguments,
            call_id=review_call_id,
            name="transfer",
            type="function_call",
        )
        approval_item = ToolApprovalItem(
            agent=approval_agent,
            raw_item=approval_call,
            tool_name="transfer",
        )
        reviewed_context = ToolContext(
            context={},
            tool_name="transfer",
            tool_call_id=review_call_id,
            tool_arguments=review_arguments,
        )
        reviewed_context.approve_tool(approval_item)
        reviewed = await protected.tool_input_guardrails[-1].run(
            ToolInputGuardrailData(context=reviewed_context, agent=approval_agent)
        )
        assert reviewed.behavior == {"type": "allow"}

        mutated_context = ToolContext(
            context={},
            tool_name="transfer",
            tool_call_id=review_call_id,
            tool_arguments='{"amount":2000}',
        )
        mutated_context.approve_tool(approval_item)
        mutated = await protected.tool_input_guardrails[-1].run(
            ToolInputGuardrailData(context=mutated_context, agent=approval_agent)
        )
        assert mutated.behavior == {"type": "raise_exception"}

    asyncio.run(exercise())
