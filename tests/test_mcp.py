# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Fail-closed MCP server adapter behavior without an optional dependency."""

from __future__ import annotations

import asyncio
import copy
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

import samsarix_ethics.mcp as adapter_module
from samsarix_ethics.approval import ToolCallApproval
from samsarix_ethics.catalog import MAX_TOOL_CATALOG_TOOLS, ToolCatalog
from samsarix_ethics.errors import (
    InputValidationError,
    ToolCallDeniedError,
    ToolCallReviewRequiredError,
    ToolCatalogValidationError,
)
from samsarix_ethics.gate import BoundToolCatalog, ToolGate
from samsarix_ethics.mcp import (
    MCP_SERVER_ADAPTER_VERSION,
    MCPServerIntegrationError,
    MCPToolReviewRequest,
    create_mcp_server_tool_policy,
)
from samsarix_ethics.models import Policy


@dataclass
class _Tool:
    name: Any
    inputSchema: dict[str, Any] = field(default_factory=dict)
    description: str = ""

    def model_copy(self, *, deep: bool) -> _Tool:
        assert deep is True
        return copy.deepcopy(self)


@pytest.fixture(autouse=True)
def fake_mcp(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = SimpleNamespace(Tool=_Tool)

    def fake_import(name: str) -> Any:
        if name == "mcp.types":
            return runtime
        raise ImportError(name)

    monkeypatch.setattr(adapter_module, "import_module", fake_import)
    monkeypatch.setattr(adapter_module, "token_hex", lambda length: "a" * (length * 2))


@pytest.fixture
def bindings() -> BoundToolCatalog:
    policy = Policy.from_dict(
        {
            "schema_version": 1,
            "id": "mcp-test",
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
            "id": "mcp-tools",
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


def _tools() -> list[_Tool]:
    return [
        _Tool("read_file", {"type": "object"}, "Read one file"),
        _Tool("send_message", {"type": "object"}, "Send one message"),
    ]


async def _handler(_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return arguments


def test_factory_is_optional_and_validates_contract(
    monkeypatch: pytest.MonkeyPatch,
    bindings: BoundToolCatalog,
) -> None:
    with pytest.raises(TypeError, match="BoundToolCatalog"):
        create_mcp_server_tool_policy(object(), _tools(), _handler)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="asynchronous"):
        create_mcp_server_tool_policy(bindings, _tools(), lambda _name, _args: None)  # type: ignore[arg-type]

    async def application_context() -> None:
        return None

    async def actor(_value: Any) -> dict[str, str]:
        return {}

    with pytest.raises(TypeError, match="application_context_provider"):
        create_mcp_server_tool_policy(
            bindings,
            _tools(),
            _handler,
            application_context_provider=application_context,
        )
    with pytest.raises(TypeError, match="actor_provider"):
        create_mcp_server_tool_policy(bindings, _tools(), _handler, actor_provider=actor)
    with pytest.raises(TypeError, match="approval_provider"):
        create_mcp_server_tool_policy(bindings, _tools(), _handler, approval_provider=object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="iterable"):
        create_mcp_server_tool_policy(bindings, "read_file", _handler)
    with pytest.raises(TypeError, match="iterable"):
        create_mcp_server_tool_policy(bindings, 1, _handler)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match=r"tools\[0\]"):
        create_mcp_server_tool_policy(bindings, [object()], _handler)

    invalid_name = _Tool(1)
    with pytest.raises(MCPServerIntegrationError, match="name must be a string"):
        create_mcp_server_tool_policy(bindings, [invalid_name], _handler)
    no_copy = _Tool("read_file")
    no_copy.model_copy = None  # type: ignore[method-assign]
    with pytest.raises(MCPServerIntegrationError, match="model_copy"):
        create_mcp_server_tool_policy(bindings, [no_copy], _handler)
    with pytest.raises(MCPServerIntegrationError, match="exceed"):
        create_mcp_server_tool_policy(
            bindings,
            [_Tool(f"tool_{index}") for index in range(MAX_TOOL_CATALOG_TOOLS + 1)],
            _handler,
        )
    with pytest.raises(ToolCatalogValidationError):
        create_mcp_server_tool_policy(bindings, [_Tool("read_file")], _handler)
    with pytest.raises(ToolCatalogValidationError):
        create_mcp_server_tool_policy(
            bindings,
            [_Tool("read_file"), _Tool("read_file")],
            _handler,
        )

    monkeypatch.setattr(
        adapter_module,
        "import_module",
        lambda _name: (_ for _ in ()).throw(ImportError("missing")),
    )
    with pytest.raises(MCPServerIntegrationError, match=r"\[mcp\]"):
        create_mcp_server_tool_policy(bindings, _tools(), _handler)


def test_tool_definitions_are_exact_snapshots(bindings: BoundToolCatalog) -> None:
    original = _tools()
    adapter = create_mcp_server_tool_policy(bindings, original, _handler)

    original[0].name = "mutated"
    first = adapter.tools
    first[0].description = "mutated copy"
    second = adapter.tools

    assert adapter.tool_names == ("read_file", "send_message")
    assert second[0].name == "read_file"
    assert second[0].description == "Read one file"
    assert adapter.bindings is bindings
    assert MCP_SERVER_ADAPTER_VERSION == 1


def test_allow_executes_once_with_detached_arguments(bindings: BoundToolCatalog) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    async def handler(name: str, arguments: dict[str, Any]) -> str:
        calls.append((name, arguments))
        arguments["nested"][0] = "changed"
        return "read"

    adapter = create_mcp_server_tool_policy(bindings, _tools(), handler)
    arguments = {"mode": "read", "nested": ["original"]}

    result = asyncio.run(adapter.call_tool("read_file", arguments))

    assert result == "read"
    assert calls == [("read_file", {"mode": "read", "nested": ["changed"]})]
    assert arguments == {"mode": "read", "nested": ["original"]}


def test_deny_review_and_invalid_calls_never_execute(bindings: BoundToolCatalog) -> None:
    calls: list[str] = []

    async def handler(name: str, _arguments: dict[str, Any]) -> None:
        calls.append(name)

    adapter = create_mcp_server_tool_policy(bindings, _tools(), handler)

    with pytest.raises(ToolCallDeniedError):
        asyncio.run(adapter.call_tool("send_message", {"mode": "delete"}))
    with pytest.raises(ToolCallReviewRequiredError):
        asyncio.run(adapter.call_tool("send_message", {"mode": "send"}))
    with pytest.raises(MCPServerIntegrationError, match="trusted catalog"):
        asyncio.run(adapter.call_tool("unknown", {}))
    with pytest.raises(MCPServerIntegrationError, match="name must be a string"):
        asyncio.run(adapter.call_tool(1, {}))  # type: ignore[arg-type]
    with pytest.raises(InputValidationError, match="JSON object"):
        asyncio.run(adapter.call_tool("read_file", []))  # type: ignore[arg-type]
    assert calls == []


def test_review_provider_approves_exact_one_shot_call(bindings: BoundToolCatalog) -> None:
    application_context = object()
    reviews: list[MCPToolReviewRequest] = []
    calls: list[dict[str, Any]] = []

    async def approve(context: Any, review: MCPToolReviewRequest) -> ToolCallApproval:
        assert context is application_context
        assert repr(review) == (
            "MCPToolReviewRequest(tool_name='send_message', "
            "tool_call_id='mcp:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', policy_id='mcp-test')"
        )
        assert review.capabilities == ("external:write",)
        assert review.policy_version == "1"
        assert review.policy_fingerprint.startswith("v1:sha256:")
        payload = review.to_dict()
        assert payload["adapter_version"] == 1
        assert payload["tool"]["arguments"] == {"mode": "send", "recipient": "a"}
        payload["tool"]["arguments"]["recipient"] = "mutated"
        reviews.append(review)
        return review.approval(approved=True)

    async def handler(_name: str, arguments: dict[str, Any]) -> str:
        calls.append(arguments)
        return "sent"

    adapter = create_mcp_server_tool_policy(
        bindings,
        _tools(),
        handler,
        application_context_provider=lambda: application_context,
        actor_provider=lambda _context: {"id": "user-1"},
        context_provider=lambda _context: {"tenant": "tenant-1"},
        approval_provider=approve,
    )

    result = asyncio.run(adapter.call_tool("send_message", {"mode": "send", "recipient": "a"}))

    assert result == "sent"
    assert len(reviews) == 1
    assert reviews[0].arguments == {"mode": "send", "recipient": "a"}
    assert calls == [{"mode": "send", "recipient": "a"}]


def test_rejected_or_forged_review_never_executes(bindings: BoundToolCatalog) -> None:
    calls: list[str] = []

    async def handler(name: str, _arguments: dict[str, Any]) -> None:
        calls.append(name)

    async def reject(_context: Any, review: MCPToolReviewRequest) -> ToolCallApproval:
        return review.approval(approved=False)

    rejected = create_mcp_server_tool_policy(
        bindings,
        _tools(),
        handler,
        approval_provider=reject,
    )
    with pytest.raises(ToolCallDeniedError):
        asyncio.run(rejected.call_tool("send_message", {"mode": "send"}))

    async def forge(_context: Any, review: MCPToolReviewRequest) -> ToolCallApproval:
        return ToolCallApproval(
            tool_call_id="mcp:forged",
            approved=True,
            tool_call_fingerprint=review.tool_call_fingerprint,
        )

    forged = create_mcp_server_tool_policy(
        bindings,
        _tools(),
        handler,
        approval_provider=forge,
    )
    with pytest.raises(InputValidationError, match="does not match"):
        asyncio.run(forged.call_tool("send_message", {"mode": "send"}))
    assert calls == []


def test_review_rechecks_actor_before_final_enforcement(bindings: BoundToolCatalog) -> None:
    calls: list[str] = []
    actor = {"id": "original"}
    provider_calls = 0

    async def handler(name: str, _arguments: dict[str, Any]) -> None:
        calls.append(name)

    async def approve(_context: Any, review: MCPToolReviewRequest) -> ToolCallApproval:
        actor["id"] = "changed-during-review"
        return review.approval(approved=True)

    def current_actor(_context: Any) -> dict[str, str]:
        nonlocal provider_calls
        provider_calls += 1
        return dict(actor)

    adapter = create_mcp_server_tool_policy(
        bindings,
        _tools(),
        handler,
        actor_provider=current_actor,
        approval_provider=approve,
    )

    with pytest.raises(InputValidationError, match="approval does not match"):
        asyncio.run(adapter.call_tool("send_message", {"mode": "send"}))
    assert provider_calls == 2
    assert calls == []


def test_provider_contracts_fail_closed(bindings: BoundToolCatalog) -> None:
    async def value() -> None:
        return None

    adapter = create_mcp_server_tool_policy(
        bindings,
        _tools(),
        _handler,
        application_context_provider=lambda: value(),
    )
    with pytest.raises(MCPServerIntegrationError, match="return synchronously"):
        asyncio.run(adapter.call_tool("read_file", {"mode": "read"}))

    adapter = create_mcp_server_tool_policy(
        bindings,
        _tools(),
        _handler,
        actor_provider=lambda _context: value(),  # type: ignore[arg-type,return-value]
    )
    with pytest.raises(MCPServerIntegrationError, match="actor_provider"):
        asyncio.run(adapter.call_tool("read_file", {"mode": "read"}))

    adapter = create_mcp_server_tool_policy(
        bindings,
        _tools(),
        _handler,
        context_provider=lambda _context: "not-a-mapping",  # type: ignore[return-value]
    )
    with pytest.raises(MCPServerIntegrationError, match="context_provider"):
        asyncio.run(adapter.call_tool("read_file", {"mode": "read"}))

    adapter = create_mcp_server_tool_policy(
        bindings,
        _tools(),
        _handler,
        application_context_provider=lambda: (_ for _ in ()).throw(LookupError()),
    )
    with pytest.raises(MCPServerIntegrationError, match="outside a server request"):
        asyncio.run(adapter.call_tool("read_file", {"mode": "read"}))

    adapter = create_mcp_server_tool_policy(
        bindings,
        _tools(),
        _handler,
        approval_provider=lambda _context, _review: None,  # type: ignore[arg-type,return-value]
    )
    with pytest.raises(MCPServerIntegrationError, match="awaitable"):
        asyncio.run(adapter.call_tool("send_message", {"mode": "send"}))

    async def invalid_approval(_context: Any, _review: MCPToolReviewRequest) -> bool:
        return True

    adapter = create_mcp_server_tool_policy(
        bindings,
        _tools(),
        _handler,
        approval_provider=invalid_approval,  # type: ignore[arg-type]
    )
    with pytest.raises(MCPServerIntegrationError, match="ToolCallApproval or None"):
        asyncio.run(adapter.call_tool("send_message", {"mode": "send"}))


def test_review_provider_is_not_called_for_allow_or_deny(bindings: BoundToolCatalog) -> None:
    review_calls = 0

    async def approve(_context: Any, review: MCPToolReviewRequest) -> ToolCallApproval:
        nonlocal review_calls
        review_calls += 1
        return review.approval(approved=True)

    adapter = create_mcp_server_tool_policy(
        bindings,
        _tools(),
        _handler,
        approval_provider=approve,
    )

    assert asyncio.run(adapter.call_tool("read_file", {"mode": "read"})) == {"mode": "read"}
    with pytest.raises(ToolCallDeniedError):
        asyncio.run(adapter.call_tool("send_message", {"mode": "delete"}))
    assert review_calls == 0
