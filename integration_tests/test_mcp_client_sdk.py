"""Exact MCP 2.1.1 client contract, using real in-memory transports (no API keys)."""

from __future__ import annotations

from typing import Any

import anyio
import pytest
from mcp import Client
from mcp.server import Server
from mcp.shared.exceptions import MCPError
from mcp.types import CallToolResult, InputRequiredResult, ListToolsResult, Tool
from pydantic import ValidationError

from samsarix_ethics import (
    InputValidationError,
    MCPClientIntegrationError,
    Policy,
    ToolCallDeniedError,
    ToolCallReviewRequiredError,
    ToolCatalog,
    ToolGate,
    create_mcp_client_tool_policy,
)


def _bindings(records: list[Any]) -> Any:
    rules = []
    for priority, (field, value, effect) in enumerate(
        [
            ("action.arguments.mode", "delete", "deny"),
            ("context.mcp.request_state", "blocked-continuation", "deny"),
            ("context.mcp.meta.forbidden", True, "deny"),
            ("context.approval.approved", True, "allow"),
            ("action.arguments.mode", "read", "allow"),
            ("action.arguments.mode", "send", "review"),
        ]
    ):
        rules.append(
            {
                "id": f"rule-{priority}",
                "priority": priority,
                "effect": effect,
                "message": "Contract decision.",
                "conditions": [{"field": field, "operator": "eq", "value": value}],
            }
        )
        if effect == "review":
            rules[-1]["conditions"].append({"field": "context.approval", "operator": "not_exists"})
    policy = Policy.from_dict(
        {
            "schema_version": 1,
            "id": "client-test",
            "version": "1",
            "default_effect": "deny",
            "rules": rules,
        }
    )
    catalog = ToolCatalog.from_dict(
        {
            "tool_catalog_version": 1,
            "id": "client-tools",
            "version": "1",
            "tools": [
                {"name": name, "capabilities": ["external:write"]} for name in ("first", "second")
            ],
        }
    )
    return ToolGate(policy, audit_sink=records.append).bind_catalog(
        catalog, registered_tools=catalog.tool_names
    )


class Harness:
    def __init__(self) -> None:
        self.calls: list[Any] = []
        self.cursors: list[Any] = []
        self.definitions = [
            Tool(name=name, description=f"Tool {name}", input_schema={"type": "object"})
            for name in ("first", "second")
        ]
        self.delay = False
        self.list_delay = False
        self.require_input = False
        self.error = False
        self.error_result = False
        self.server: Server[Any] = Server(
            "contract-server", on_list_tools=self.list_tools, on_call_tool=self.call_tool
        )

    async def list_tools(self, _ctx: Any, params: Any) -> ListToolsResult:
        if self.list_delay:
            await anyio.sleep_forever()
        cursor = params.cursor if params else None
        self.cursors.append(cursor)
        if cursor is None:
            return ListToolsResult(tools=self.definitions[:1], next_cursor="page2")
        assert cursor == "page2"
        return ListToolsResult(tools=self.definitions[1:])

    async def call_tool(self, ctx: Any, params: Any) -> Any:
        self.calls.append(params)
        if self.delay:
            await anyio.sleep_forever()
        if self.error:
            raise RuntimeError("server failed")
        if self.error_result:
            return CallToolResult(content=[], is_error=True)
        if self.require_input and params.request_state is None:
            return InputRequiredResult(request_state="continue-once")
        await ctx.session.report_progress(1, 1, "done")
        return CallToolResult(content=[], structured_content={"received": params.arguments})


@pytest.mark.parametrize("mode", ["auto", "legacy"])
def test_real_client_allow_deny_review_pagination_and_audit(mode: str) -> None:
    harness, records, reviews = Harness(), [], []

    async def approve(review: Any) -> Any:
        reviews.append(review)
        return review.approval(approved=True)

    async def scenario() -> None:
        async with Client(harness.server, mode=mode) as client:
            adapter = await create_mcp_client_tool_policy(
                _bindings(records), client, server_id="support-primary", approval_provider=approve
            )
            assert [tool.name for tool in adapter.tools] == ["first", "second"]
            result = await adapter.call_tool("first", {"mode": "read", "nested": [1]})
            assert result.structured_content == {"received": {"mode": "read", "nested": [1]}}
            with pytest.raises(ToolCallDeniedError):
                await adapter.call_tool("second", {"mode": "delete"})
            with pytest.raises(MCPClientIntegrationError, match="trusted catalog"):
                await adapter.call_tool("unknown", {})
            await adapter.call_tool("second", {"mode": "send"}, meta={"tenant": "one"})

    anyio.run(scenario)
    assert len(harness.calls) == 2
    assert [r.outcome for r in records] == ["allow", "deny", "allow"]
    assert len(reviews) == 1
    assert reviews[0].request["meta"] == {"tenant": "one"}
    assert harness.cursors == [None, "page2"] * 5


@pytest.mark.parametrize("approval", [None, False])
def test_real_client_unapproved_review_never_sends(approval: Any) -> None:
    harness = Harness()

    async def reject(review: Any) -> Any:
        return review.approval(approved=False)

    async def scenario() -> None:
        async with Client(harness.server) as client:
            adapter = await create_mcp_client_tool_policy(
                _bindings([]),
                client,
                server_id="support",
                approval_provider=reject if approval is False else None,
            )
            expected = (
                MCPClientIntegrationError if approval is False else ToolCallReviewRequiredError
            )
            with pytest.raises(expected):
                await adapter.call_tool("second", {"mode": "send"})

    anyio.run(scenario)
    assert harness.calls == []


@pytest.mark.parametrize("during_review", [False, True])
def test_real_client_definition_drift_never_sends(during_review: bool) -> None:
    harness = Harness()

    def change() -> None:
        harness.definitions[1].description = "Different implementation contract"

    async def approve(review: Any) -> Any:
        change()
        return review.approval(approved=True)

    async def scenario() -> None:
        async with Client(harness.server) as client:
            adapter = await create_mcp_client_tool_policy(
                _bindings([]), client, server_id="support", approval_provider=approve
            )
            if not during_review:
                change()
            with pytest.raises(MCPClientIntegrationError, match="definitions changed"):
                await adapter.call_tool("second", {"mode": "send" if during_review else "read"})

    anyio.run(scenario)
    assert harness.calls == []


def test_real_client_continuation_is_one_round_and_reauthorized() -> None:
    harness = Harness()
    harness.require_input = True
    records: list[Any] = []

    async def scenario() -> None:
        async with Client(harness.server) as client:
            adapter = await create_mcp_client_tool_policy(
                _bindings(records), client, server_id="support"
            )
            first = await adapter.call_tool("first", {"mode": "read"})
            assert isinstance(first, InputRequiredResult)
            assert len(harness.calls) == 1
            with pytest.raises(ToolCallDeniedError):
                await adapter.call_tool(
                    "first", {"mode": "read"}, request_state="blocked-continuation"
                )
            result = await adapter.call_tool(
                "first",
                {"mode": "read"},
                request_state=first.request_state,
                input_responses={"ask": {"action": "accept", "content": {"choice": "yes"}}},
            )
            assert isinstance(result, CallToolResult)

    anyio.run(scenario)
    assert len(harness.calls) == 2
    assert harness.calls[1].input_responses["ask"].action == "accept"
    assert [r.outcome for r in records] == ["allow", "deny", "allow"]


def test_real_client_metadata_and_progress() -> None:
    harness, progress = Harness(), []

    async def on_progress(current: Any, total: Any, message: Any) -> None:
        progress.append((current, total, message))

    async def scenario() -> None:
        async with Client(harness.server) as client:
            adapter = await create_mcp_client_tool_policy(
                _bindings([]), client, server_id="support"
            )
            with pytest.raises(ToolCallDeniedError):
                await adapter.call_tool("first", {"mode": "read"}, meta={"forbidden": True})
            await adapter.call_tool(
                "first",
                {"mode": "read"},
                meta={"tenant": "one"},
                progress_callback=on_progress,
                read_timeout_seconds=5,
            )

    anyio.run(scenario)
    assert len(harness.calls) == 1
    assert harness.calls[0].meta["tenant"] == "one"
    assert progress == [(1, 1, "done")]


def test_real_client_actor_change_invalidates_review() -> None:
    harness, actor = Harness(), {"id": "one"}

    async def approve(review: Any) -> Any:
        actor["id"] = "two"
        return review.approval(approved=True)

    async def scenario() -> None:
        async with Client(harness.server) as client:
            adapter = await create_mcp_client_tool_policy(
                _bindings([]),
                client,
                server_id="support",
                actor_provider=lambda: actor,
                approval_provider=approve,
            )
            with pytest.raises(InputValidationError, match="does not match"):
                await adapter.call_tool("second", {"mode": "send"})

    anyio.run(scenario)
    assert harness.calls == []


def test_real_client_dispatch_timeout_does_not_retry() -> None:
    harness = Harness()
    harness.delay = True

    async def scenario() -> None:
        async with Client(harness.server) as client:
            adapter = await create_mcp_client_tool_policy(
                _bindings([]), client, server_id="support"
            )
            with pytest.raises(TimeoutError):
                await adapter.call_tool("first", {"mode": "read"}, read_timeout_seconds=0.05)

    anyio.run(scenario)
    assert len(harness.calls) == 1


def test_real_client_server_error_is_not_retried_or_converted_to_allow() -> None:
    harness = Harness()
    harness.error = True

    async def scenario() -> None:
        async with Client(harness.server) as client:
            adapter = await create_mcp_client_tool_policy(
                _bindings([]), client, server_id="support"
            )
            with pytest.raises(MCPError, match="Internal server error"):
                await adapter.call_tool("first", {"mode": "read"})

    anyio.run(scenario)
    assert len(harness.calls) == 1


@pytest.mark.parametrize(
    "extra",
    [
        {"arguments": []},
        {"request_state": 12},
        {"input_responses": {"ask": {"action": "wrong"}}},
    ],
)
def test_real_request_field_validation_happens_before_discovery_and_send(extra: Any) -> None:
    harness = Harness()

    async def scenario() -> None:
        async with Client(harness.server) as client:
            adapter = await create_mcp_client_tool_policy(
                _bindings([]), client, server_id="support"
            )
            before = len(harness.cursors)
            with pytest.raises(ValidationError):
                await adapter.call_tool("first", **extra)
            assert len(harness.cursors) == before

    anyio.run(scenario)
    assert harness.calls == []


def test_real_review_timeout_and_cancellation_never_send() -> None:
    harness = Harness()

    async def pending(_review: Any) -> Any:
        await anyio.sleep_forever()

    async def scenario() -> None:
        async with Client(harness.server) as client:
            adapter = await create_mcp_client_tool_policy(
                _bindings([]),
                client,
                server_id="support",
                approval_provider=pending,
                review_timeout_seconds=0.03,
            )
            with pytest.raises(TimeoutError):
                await adapter.call_tool("second", {"mode": "send"})
            with anyio.move_on_after(0.01) as scope:
                await adapter.call_tool("second", {"mode": "send"})
            assert scope.cancel_called

    anyio.run(scenario)
    assert harness.calls == []


def test_real_discovery_timeout_prevents_call_and_factory_binding() -> None:
    harness = Harness()

    async def scenario() -> None:
        async with Client(harness.server) as client:
            adapter = await create_mcp_client_tool_policy(
                _bindings([]), client, server_id="support", timeout_seconds=0.1
            )
            harness.list_delay = True
            with pytest.raises(TimeoutError):
                await adapter.call_tool("first", {"mode": "read"})
            with pytest.raises(TimeoutError):
                await create_mcp_client_tool_policy(
                    _bindings([]), client, server_id="support", timeout_seconds=0.03
                )

    anyio.run(scenario)
    assert harness.calls == []


def test_real_error_tool_result_is_returned_unchanged() -> None:
    harness = Harness()
    harness.error_result = True

    async def scenario() -> None:
        async with Client(harness.server) as client:
            adapter = await create_mcp_client_tool_policy(
                _bindings([]), client, server_id="support"
            )
            result = await adapter.call_tool("first", {"mode": "read"})
            assert result.is_error is True

    anyio.run(scenario)
    assert len(harness.calls) == 1
