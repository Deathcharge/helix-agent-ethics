# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Fail-closed LangChain middleware behavior without an optional dependency."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

import samsarix_ethics.langchain as adapter_module
from samsarix_ethics.catalog import ToolCatalog
from samsarix_ethics.errors import (
    InputValidationError,
    ToolCallDeniedError,
    ToolCatalogValidationError,
)
from samsarix_ethics.gate import BoundToolCatalog, ToolGate
from samsarix_ethics.langchain import (
    LANGCHAIN_ADAPTER_VERSION,
    LANGCHAIN_REVIEW_INTERRUPT_TYPE,
    LangChainIntegrationError,
    create_langchain_tool_policy,
)
from samsarix_ethics.models import Outcome, Policy


class _AgentMiddleware:
    pass


@dataclass
class _BaseTool:
    name: Any


@dataclass
class _ToolCallRequest:
    tool_call: Any
    tool: Any
    state: Any
    runtime: Any


@dataclass
class _ToolMessage:
    content: str
    tool_call_id: str
    name: str
    status: str


class _Interrupted(Exception):
    pass


class _InterruptController:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []
        self.responses: list[Any] = []

    def interrupt(self, payload: dict[str, Any]) -> Any:
        self.payloads.append(payload)
        if not self.responses:
            raise _Interrupted
        return self.responses.pop(0)


@pytest.fixture
def fake_langchain(monkeypatch: pytest.MonkeyPatch) -> _InterruptController:
    controller = _InterruptController()
    modules = {
        "langchain.agents.middleware": SimpleNamespace(
            AgentMiddleware=_AgentMiddleware,
            ToolCallRequest=_ToolCallRequest,
        ),
        "langchain.messages": SimpleNamespace(ToolMessage=_ToolMessage),
        "langchain.tools": SimpleNamespace(BaseTool=_BaseTool),
        "langgraph.types": SimpleNamespace(interrupt=controller.interrupt),
    }

    def fake_import(name: str) -> Any:
        try:
            return modules[name]
        except KeyError as exc:
            raise ImportError(name) from exc

    monkeypatch.setattr(adapter_module, "import_module", fake_import)
    return controller


@pytest.fixture
def bindings() -> BoundToolCatalog:
    policy = Policy.from_dict(
        {
            "schema_version": 1,
            "id": "langchain-test",
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
            "id": "langchain-tools",
            "version": "1",
            "description": "Trusted LangChain test tools.",
            "tools": [
                {"name": "read_file", "capabilities": ["workspace:read"]},
                {"name": "send_message", "capabilities": ["external:write"]},
            ],
        }
    )
    return ToolGate(policy).bind_catalog(
        catalog,
        registered_tools=["read_file", "send_message"],
    )


def _request(
    *,
    name: str = "send_message",
    arguments: Any = None,
    call_id: Any = "call-1",
    tool: Any = None,
    application_context: Any = None,
) -> _ToolCallRequest:
    selected_arguments = {"mode": "read"} if arguments is None else arguments
    selected_tool = _BaseTool(name) if tool is None else tool
    return _ToolCallRequest(
        tool_call={
            "name": name,
            "args": selected_arguments,
            "id": call_id,
            "type": "tool_call",
        },
        tool=selected_tool,
        state={},
        runtime=SimpleNamespace(context=application_context),
    )


def _resume(payload: dict[str, Any], *, approved: bool) -> dict[str, Any]:
    return {**payload["approval_binding"], "approved": approved}


def test_factory_is_optional_and_validates_contract(
    fake_langchain: _InterruptController,
    bindings: BoundToolCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = create_langchain_tool_policy(bindings)
    assert adapter.bindings is bindings
    assert isinstance(adapter.middleware, _AgentMiddleware)
    assert LANGCHAIN_ADAPTER_VERSION == 1
    assert LANGCHAIN_REVIEW_INTERRUPT_TYPE == "samsarix.tool_call.review"

    with pytest.raises(TypeError, match="BoundToolCatalog"):
        create_langchain_tool_policy(object())  # type: ignore[arg-type]

    async def async_provider(_context: Any) -> dict[str, Any]:
        return {}

    with pytest.raises(TypeError, match="synchronous callable"):
        create_langchain_tool_policy(bindings, actor_provider=async_provider)

    monkeypatch.setattr(
        adapter_module,
        "import_module",
        lambda _name: (_ for _ in ()).throw(ImportError("missing")),
    )
    with pytest.raises(LangChainIntegrationError, match=r"\[langchain\]"):
        create_langchain_tool_policy(bindings)


def test_validate_tools_requires_exact_base_tool_registry(
    fake_langchain: _InterruptController,
    bindings: BoundToolCatalog,
) -> None:
    adapter = create_langchain_tool_policy(bindings)
    tools = (_BaseTool("send_message"), _BaseTool("read_file"))

    assert adapter.validate_tools(iter(tools)) == tools

    with pytest.raises(TypeError, match="BaseTool"):
        adapter.validate_tools([object()])
    with pytest.raises(ToolCatalogValidationError, match="missing from registry"):
        adapter.validate_tools([_BaseTool("send_message")])
    with pytest.raises(ToolCatalogValidationError, match="missing from catalog"):
        adapter.validate_tools([*tools, _BaseTool("other")])
    with pytest.raises(ToolCatalogValidationError, match="duplicate"):
        adapter.validate_tools([_BaseTool("send_message"), _BaseTool("send_message")])


def test_allow_executes_once_and_deny_never_calls_handler(
    fake_langchain: _InterruptController,
    bindings: BoundToolCatalog,
) -> None:
    adapter = create_langchain_tool_policy(bindings)
    calls: list[Any] = []
    expected = object()

    def handler(request: Any) -> Any:
        calls.append(request)
        return expected

    allowed_request = _request(arguments={"mode": "read"})
    assert adapter.middleware.wrap_tool_call(allowed_request, handler) is expected
    assert calls == [allowed_request]
    assert fake_langchain.payloads == []

    with pytest.raises(ToolCallDeniedError):
        adapter.middleware.wrap_tool_call(_request(arguments={"mode": "delete"}), handler)
    assert calls == [allowed_request]


def test_review_interrupt_approval_and_rejection_are_exact_call_bound(
    fake_langchain: _InterruptController,
    bindings: BoundToolCatalog,
) -> None:
    adapter = create_langchain_tool_policy(bindings)
    request = _request(arguments={"mode": "send", "recipient": "person@example.com"})
    calls: list[Any] = []

    with pytest.raises(_Interrupted):
        adapter.middleware.wrap_tool_call(request, lambda value: calls.append(value))

    payload = fake_langchain.payloads[-1]
    assert payload == {
        "type": "samsarix.tool_call.review",
        "adapter_version": 1,
        "approval_binding": {
            "approval_version": 1,
            "tool_call_id": "call-1",
            "tool_call_fingerprint": adapter.approval_for(
                request, approved=True
            ).tool_call_fingerprint,
        },
        "tool": {
            "name": "send_message",
            "arguments": {"mode": "send", "recipient": "person@example.com"},
        },
        "policy": {
            "id": "langchain-test",
            "version": "1",
            "fingerprint": bindings.gate.policy_fingerprint,
            "decisive_rule_ids": ["review-send"],
        },
    }
    fake_langchain.responses.append(_resume(payload, approved=True))
    result = object()
    assert (
        adapter.middleware.wrap_tool_call(request, lambda value: calls.append(value) or result)
        is result
    )
    assert calls == [request]

    rejected_request = _request(arguments={"mode": "send"}, call_id="call-2")
    with pytest.raises(_Interrupted):
        adapter.middleware.wrap_tool_call(rejected_request, lambda value: calls.append(value))
    rejected_payload = fake_langchain.payloads[-1]
    fake_langchain.responses.append(_resume(rejected_payload, approved=False))
    rejected = adapter.middleware.wrap_tool_call(
        rejected_request, lambda value: calls.append(value)
    )
    assert rejected == _ToolMessage(
        content="Tool call rejected by human review.",
        tool_call_id="call-2",
        name="send_message",
        status="error",
    )
    assert calls == [request]


def test_review_resume_cannot_authorize_mutated_arguments_or_actor(
    fake_langchain: _InterruptController,
    bindings: BoundToolCatalog,
) -> None:
    def actor_provider(context: Any) -> dict[str, Any]:
        return {"id": context["actor_id"]}

    adapter = create_langchain_tool_policy(bindings, actor_provider=actor_provider)
    application_context = {"actor_id": "reviewed-actor"}
    original = _request(
        arguments={"mode": "send", "recipient": "original@example.com"},
        application_context=application_context,
    )
    with pytest.raises(_Interrupted):
        adapter.middleware.wrap_tool_call(original, lambda _request: None)
    response = _resume(fake_langchain.payloads[-1], approved=True)

    mutated = _request(
        arguments={"mode": "send", "recipient": "changed@example.com"},
        application_context=application_context,
    )
    fake_langchain.responses.append(response)
    with pytest.raises(LangChainIntegrationError, match="does not match"):
        adapter.middleware.wrap_tool_call(mutated, lambda _request: pytest.fail("executed"))

    application_context["actor_id"] = "changed-actor"
    fake_langchain.responses.append(response)
    with pytest.raises(LangChainIntegrationError, match="does not match"):
        adapter.middleware.wrap_tool_call(original, lambda _request: pytest.fail("executed"))


def test_review_response_and_request_shapes_fail_closed(
    fake_langchain: _InterruptController,
    bindings: BoundToolCatalog,
) -> None:
    adapter = create_langchain_tool_policy(bindings)
    request = _request(arguments={"mode": "send"})
    fake_langchain.responses.append({"approved": True})
    with pytest.raises(InputValidationError, match="missing"):
        adapter.middleware.wrap_tool_call(request, lambda _request: pytest.fail("executed"))

    invalid_requests = [
        object(),
        _ToolCallRequest([], _BaseTool("send_message"), {}, SimpleNamespace(context=None)),
        _request(name="other"),
        _request(call_id=object()),
        _request(arguments=[]),
        _request(tool=object()),
        _request(tool=_BaseTool("read_file")),
        _ToolCallRequest(
            {"name": "send_message", "args": {"mode": "read"}, "id": "call-1"},
            _BaseTool("send_message"),
            {},
            object(),
        ),
        _request(arguments={"mode": object()}),
    ]
    for invalid in invalid_requests:
        with pytest.raises((TypeError, LangChainIntegrationError, InputValidationError)):
            adapter.middleware.wrap_tool_call(invalid, lambda _request: pytest.fail("executed"))


def test_facts_are_fresh_and_provider_errors_are_not_hidden(
    fake_langchain: _InterruptController,
    bindings: BoundToolCatalog,
) -> None:
    seen: list[Any] = []

    def context_provider(application_context: Any) -> dict[str, Any]:
        seen.append(application_context)
        return {"tenant": application_context["tenant"]}

    adapter = create_langchain_tool_policy(bindings, context_provider=context_provider)
    application_context = {"tenant": "acme"}
    request = _request(application_context=application_context)
    assert adapter.explain(request).outcome is Outcome.ALLOW
    assert adapter.middleware.wrap_tool_call(request, lambda _request: "ok") == "ok"
    assert seen == [application_context, application_context]

    bad_return = create_langchain_tool_policy(
        bindings,
        context_provider=lambda _context: [],  # type: ignore[arg-type,return-value]
    )
    with pytest.raises(LangChainIntegrationError, match="mapping or None"):
        bad_return.middleware.wrap_tool_call(request, lambda _request: pytest.fail("executed"))

    def broken(_context: Any) -> dict[str, Any]:
        raise RuntimeError("application bug")

    broken_adapter = create_langchain_tool_policy(bindings, context_provider=broken)
    with pytest.raises(RuntimeError, match="application bug"):
        broken_adapter.middleware.wrap_tool_call(request, lambda _request: pytest.fail("executed"))


def test_async_middleware_authorizes_before_awaiting_handler(
    fake_langchain: _InterruptController,
    bindings: BoundToolCatalog,
) -> None:
    adapter = create_langchain_tool_policy(bindings)
    calls: list[Any] = []
    request = _request(arguments={"mode": "read"})

    async def handler(value: Any) -> str:
        calls.append(value)
        return "done"

    assert asyncio.run(adapter.middleware.awrap_tool_call(request, handler)) == "done"
    assert calls == [request]

    review = _request(arguments={"mode": "send"})
    fake_langchain.responses.append(adapter.approval_for(review, approved=True).to_dict())
    assert asyncio.run(adapter.middleware.awrap_tool_call(review, handler)) == "done"
    assert calls == [request, review]
