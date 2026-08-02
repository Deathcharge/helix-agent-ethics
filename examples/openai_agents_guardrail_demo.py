# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Configure a guarded OpenAI Agents SDK tool without making a model request."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from agents import Agent, function_tool
from agents.run_context import RunContextWrapper

from samsarix_ethics import ToolGate, create_openai_agents_tool_policy, load_policy


@dataclass(frozen=True)
class ApplicationContext:
    actor: dict[str, Any]
    policy_context: dict[str, Any]


@function_tool(strict_mode=True)
def send_message(recipient: str, subject: str) -> str:
    """Send one external message."""

    return f"sent {subject!r} to {recipient}"


async def main() -> None:
    policy = load_policy("examples/policies/tool-call-baseline.json")
    binding = ToolGate(policy).bind("send_message", capabilities=["external:write"])
    adapter = create_openai_agents_tool_policy(
        binding,
        actor_provider=lambda application: application.actor,
        context_provider=lambda application: application.policy_context,
    )
    protected_tool = adapter.protect(send_message)
    agent = Agent(name="support-agent", tools=[protected_tool])

    application = ApplicationContext(
        actor={"id": "support-agent"},
        policy_context={"tenant": "example"},
    )
    needs_review = await protected_tool.needs_approval(
        RunContextWrapper(context=application),
        {"recipient": "customer@example.com", "subject": "Ticket update"},
        "call-demo",
    )
    if not needs_review:
        raise RuntimeError("expected the external write to require approval")
    print(f"{len(agent.tools)} tool is protected; the example call requires approval")


if __name__ == "__main__":
    asyncio.run(main())
