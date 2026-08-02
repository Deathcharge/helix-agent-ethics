# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Fail-closed OpenAI Agents SDK adapter behavior without an optional dependency."""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

import samsarix_ethics.openai_agents as adapter_module
from samsarix_ethics import (
    OPENAI_AGENTS_ADAPTER_VERSION,
    OpenAIAgentsIntegrationError,
    Policy,
    ToolGate,
    create_openai_agents_tool_policy,
)


@dataclass
class _FunctionTool:
    name: str
    strict_json_schema: bool = True
    tool_input_guardrails: list[Any] | None = None
    needs_approval: Any = False
    _is_agent_tool: bool = False
    _tool_namespace: str | None = None


@dataclass
class _Guardrail:
    guardrail_function: Any
    name: str | None = None

    async def run(self, data: Any) -> Any:
        return await self.guardrail_function(data)


@dataclass
class _Output:
    output_info: Any
    behavior: dict[str, str]

    @classmethod
    def allow(cls, output_info: Any = None) -> _Output:
        return cls(output_info, {"type": "allow"})

    @classmethod
    def raise_exception(cls, output_info: Any = None) -> _Output:
        return cls(output_info, {"type": "raise_exception"})


@dataclass
class _RunContext:
    context: Any


@dataclass
class _ToolContext:
    context: Any
    tool_arguments: Any
    tool_call_id: Any = "call-1"
    tool_name: Any = "send_message"
    tool_namespace: str | None = None
    approval_status: Any = None

    def get_approval_status(self, tool_name: str, call_id: str) -> Any:
        assert tool_name == self.tool_name
        assert call_id == self.tool_call_id
        return self.approval_status


@pytest.fixture
def fake_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    agents = ModuleType("agents")
    agents.FunctionTool = _FunctionTool  # type: ignore[attr-defined]
    guardrails = ModuleType("agents.tool_guardrails")
    guardrails.ToolInputGuardrail = _Guardrail  # type: ignore[attr-defined]
    guardrails.ToolGuardrailFunctionOutput = _Output  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "agents", agents)
    monkeypatch.setitem(sys.modules, "agents.tool_guardrails", guardrails)


@pytest.fixture
def binding() -> Any:
    policy = Policy.from_dict(
        {
            "schema_version": 1,
            "id": "openai-agents-test",
            "version": "1",
            "default_effect": "deny",
            "rules": [
                {
                    "id": "allow-approved",
                    "effect": "allow",
                    "priority": 1,
                    "message": "An approved exact call may run.",
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
    return ToolGate(policy).bind("send_message", capabilities=["external:write"])


def _protected(binding: Any) -> tuple[Any, Any]:
    adapter = create_openai_agents_tool_policy(binding)
    return adapter, adapter.protect(_FunctionTool("send_message"))


def _run_guardrail(tool: Any, context: _ToolContext) -> _Output:
    guardrail = tool.tool_input_guardrails[-1]
    return asyncio.run(guardrail.run(SimpleNamespace(context=context)))


def test_factory_is_optional_and_validates_inputs(
    fake_sdk: None, binding: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = create_openai_agents_tool_policy(binding)
    assert adapter.binding is binding
    assert OPENAI_AGENTS_ADAPTER_VERSION == 1

    with pytest.raises(TypeError, match="BoundToolGate"):
        create_openai_agents_tool_policy(object())  # type: ignore[arg-type]

    async def async_provider(_context: Any) -> dict[str, Any]:
        return {}

    with pytest.raises(TypeError, match="synchronous callable"):
        create_openai_agents_tool_policy(binding, actor_provider=async_provider)
    with pytest.raises(TypeError, match="remember and get"):
        create_openai_agents_tool_policy(binding, approval_store=object())

    def missing_sdk(_name: str) -> Any:
        raise ImportError("missing")

    monkeypatch.setattr(adapter_module, "import_module", missing_sdk)
    with pytest.raises(OpenAIAgentsIntegrationError, match="openai-agents"):
        create_openai_agents_tool_policy(binding)


@pytest.mark.parametrize(
    ("tool", "error"),
    [
        (object(), TypeError),
        (_FunctionTool("other"), OpenAIAgentsIntegrationError),
        (_FunctionTool("send_message", strict_json_schema=False), OpenAIAgentsIntegrationError),
        (_FunctionTool("send_message", _is_agent_tool=True), OpenAIAgentsIntegrationError),
        (_FunctionTool("send_message", _tool_namespace="group"), OpenAIAgentsIntegrationError),
        (_FunctionTool("send_message", tool_input_guardrails=()), OpenAIAgentsIntegrationError),
    ],
)
def test_protect_rejects_unsupported_tool_shapes(
    fake_sdk: None, binding: Any, tool: Any, error: type[Exception]
) -> None:
    adapter = create_openai_agents_tool_policy(binding)
    with pytest.raises(error):
        adapter.protect(tool)


def test_protect_copies_tool_and_preserves_existing_controls(fake_sdk: None, binding: Any) -> None:
    prior_guardrail = object()
    approval_calls: list[str] = []

    async def prior_approval(_context: Any, _arguments: Any, call_id: str) -> bool:
        approval_calls.append(call_id)
        return False

    original = _FunctionTool(
        "send_message",
        tool_input_guardrails=[prior_guardrail],
        needs_approval=prior_approval,
    )
    adapter = create_openai_agents_tool_policy(binding)
    protected = adapter.protect(original)

    assert protected is not original
    assert original.tool_input_guardrails == [prior_guardrail]
    assert protected.tool_input_guardrails[0] is prior_guardrail
    assert protected.tool_input_guardrails[-1].name == "samsarix_agent_ethics_v1"
    assert asyncio.run(protected.needs_approval(_RunContext({}), {"mode": "send"}, "call-1"))
    assert approval_calls == ["call-1"]
    with pytest.raises(OpenAIAgentsIntegrationError, match="already protected"):
        adapter.protect(protected)


def test_review_routes_to_approval_but_allow_and_deny_do_not(fake_sdk: None, binding: Any) -> None:
    _adapter, protected = _protected(binding)
    context = _RunContext({})

    assert asyncio.run(protected.needs_approval(context, {"mode": "send"}, "call-1"))
    assert not asyncio.run(protected.needs_approval(context, {"mode": "read"}, "call-1"))
    assert not asyncio.run(protected.needs_approval(context, {"mode": "delete"}, "call-1"))
    assert not asyncio.run(protected.needs_approval(context, {"bad": object()}, "call-1"))


def test_guardrail_allows_read_and_approved_exact_review(fake_sdk: None, binding: Any) -> None:
    _adapter, protected = _protected(binding)

    read = _run_guardrail(protected, _ToolContext({}, '{"mode":"read"}'))
    assert asyncio.run(protected.needs_approval(_RunContext({}), {"mode": "send"}, "call-1"))
    approved = _run_guardrail(
        protected,
        _ToolContext({}, '{"mode":"send"}', approval_status=True),
    )

    assert read.behavior == {"type": "allow"}
    assert approved.behavior == {"type": "allow"}
    assert read.output_info == {
        "adapter": "samsarix-agent-ethics",
        "status": "allowed",
    }


def test_approval_is_bound_before_interruption_and_cannot_authorize_mutation(
    fake_sdk: None, binding: Any
) -> None:
    _adapter, protected = _protected(binding)
    assert asyncio.run(protected.needs_approval(_RunContext({}), {"mode": "send"}, "call-1"))

    mutated = _run_guardrail(
        protected,
        _ToolContext({}, '{"mode":"send","recipient":"changed"}', approval_status=True),
    )
    unrelated = create_openai_agents_tool_policy(binding).protect(
        _FunctionTool("send_message", needs_approval=True)
    )
    unrelated_approval = _run_guardrail(
        unrelated,
        _ToolContext({}, '{"mode":"send"}', approval_status=True),
    )

    assert mutated.behavior == {"type": "raise_exception"}
    assert unrelated_approval.behavior == {"type": "raise_exception"}


def test_application_store_supports_fail_closed_adapter_reconstruction(
    fake_sdk: None, binding: Any
) -> None:
    class Store:
        def __init__(self) -> None:
            self.values: dict[tuple[str, str], str] = {}

        def remember(
            self,
            _application_context: Any,
            tool_name: str,
            tool_call_id: str,
            fingerprint: str,
        ) -> str:
            return self.values.setdefault((tool_name, tool_call_id), fingerprint)

        def get(
            self,
            _application_context: Any,
            tool_name: str,
            tool_call_id: str,
        ) -> str | None:
            return self.values.get((tool_name, tool_call_id))

    store = Store()
    first = create_openai_agents_tool_policy(binding, approval_store=store).protect(
        _FunctionTool("send_message")
    )
    assert asyncio.run(first.needs_approval(_RunContext({}), {"mode": "send"}, "call-1"))

    resumed = create_openai_agents_tool_policy(binding, approval_store=store).protect(
        _FunctionTool("send_message")
    )
    assert _run_guardrail(
        resumed,
        _ToolContext({}, '{"mode":"send"}', approval_status=True),
    ).behavior == {"type": "allow"}


def test_default_approval_store_is_bounded_and_never_evicts(
    fake_sdk: None,
    binding: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(adapter_module, "MAX_PENDING_OPENAI_APPROVALS", 1)
    _adapter, protected = _protected(binding)

    assert asyncio.run(protected.needs_approval(_RunContext({}), {"mode": "send"}, "call-1"))
    assert not asyncio.run(protected.needs_approval(_RunContext({}), {"mode": "send"}, "call-2"))


@pytest.mark.parametrize(
    "context",
    [
        _ToolContext({}, '{"mode":"delete"}'),
        _ToolContext({}, '{"mode":"send"}'),
        _ToolContext({}, '{"mode":"read","mode":"send"}'),
        _ToolContext({}, "[]"),
        _ToolContext({}, '{"mode":NaN}'),
        _ToolContext({}, '{"mode":"read"}', tool_name="other"),
        _ToolContext({}, '{"mode":"read"}', tool_namespace="group"),
        _ToolContext({}, '{"mode":"read"}', approval_status=False),
        _ToolContext({}, '{"mode":"send"}', approval_status="yes"),
        _ToolContext({}, '{"mode":"send"}', tool_call_id=object(), approval_status=True),
    ],
)
def test_guardrail_blocks_policy_and_contract_failures(
    fake_sdk: None, binding: Any, context: _ToolContext
) -> None:
    _adapter, protected = _protected(binding)
    output = _run_guardrail(protected, context)
    assert output.behavior == {"type": "raise_exception"}
    assert output.output_info == {
        "adapter": "samsarix-agent-ethics",
        "status": "blocked",
    }


def test_guardrail_uses_fresh_application_facts_and_propagates_programming_errors(
    fake_sdk: None, binding: Any
) -> None:
    actor_calls: list[Any] = []
    context_calls: list[Any] = []

    def actor_provider(application_context: Any) -> dict[str, Any]:
        actor_calls.append(application_context)
        return {"id": application_context["actor_id"]}

    def context_provider(application_context: Any) -> dict[str, Any]:
        context_calls.append(application_context)
        return {"tenant": application_context["tenant"]}

    adapter = create_openai_agents_tool_policy(
        binding,
        actor_provider=actor_provider,
        context_provider=context_provider,
    )
    protected = adapter.protect(_FunctionTool("send_message", needs_approval=True))
    application_context = {"actor_id": "user-1", "tenant": "acme"}

    assert asyncio.run(
        protected.needs_approval(_RunContext(application_context), {"mode": "read"}, "call-1")
    )
    assert _run_guardrail(
        protected,
        _ToolContext(application_context, '{"mode":"read"}'),
    ).behavior == {"type": "allow"}
    assert actor_calls == [application_context, application_context]
    assert context_calls == [application_context, application_context]

    def broken_provider(_context: Any) -> dict[str, Any]:
        raise RuntimeError("application bug")

    broken = create_openai_agents_tool_policy(binding, context_provider=broken_provider).protect(
        _FunctionTool("send_message")
    )
    with pytest.raises(RuntimeError, match="application bug"):
        _run_guardrail(broken, _ToolContext({}, '{"mode":"read"}'))


def test_guardrail_blocks_missing_sdk_context_contract(fake_sdk: None, binding: Any) -> None:
    _adapter, protected = _protected(binding)
    output = asyncio.run(protected.tool_input_guardrails[-1].run(SimpleNamespace()))
    assert output.behavior == {"type": "raise_exception"}

    no_method = SimpleNamespace(
        context={},
        tool_arguments='{"mode":"send"}',
        tool_call_id="call-1",
        tool_name="send_message",
        tool_namespace=None,
    )
    output = asyncio.run(
        protected.tool_input_guardrails[-1].run(SimpleNamespace(context=no_method))
    )
    assert output.behavior == {"type": "raise_exception"}


def test_guardrail_blocks_oversized_or_non_string_arguments(fake_sdk: None, binding: Any) -> None:
    _adapter, protected = _protected(binding)
    oversized = '{"value":"' + ("x" * 262_145) + '"}'
    for raw in (oversized, b'{"mode":"read"}'):
        output = _run_guardrail(protected, _ToolContext({}, raw))
        assert output.behavior == {"type": "raise_exception"}
