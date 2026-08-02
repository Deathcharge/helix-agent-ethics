# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Fail-closed Pydantic AI toolset behavior without an optional dependency."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

import samsarix_ethics.pydantic_ai as adapter_module
from samsarix_ethics.catalog import ToolCatalog
from samsarix_ethics.errors import (
    InputValidationError,
    ToolCallDeniedError,
    ToolCatalogValidationError,
)
from samsarix_ethics.gate import BoundToolCatalog, ToolGate
from samsarix_ethics.models import Policy
from samsarix_ethics.pydantic_ai import (
    PYDANTIC_AI_ADAPTER_VERSION,
    PYDANTIC_AI_APPROVAL_METADATA_KEY,
    PYDANTIC_AI_REVIEW_METADATA_KEY,
    PydanticAIIntegrationError,
    create_pydantic_ai_tool_policy,
)


class _AbstractToolset:
    async def for_run(self, _ctx: Any) -> _AbstractToolset:
        return self


class _WrapperToolset(_AbstractToolset):
    def __init__(self, wrapped: _AbstractToolset) -> None:
        self.wrapped = wrapped


@dataclass
class _ToolDefinition:
    name: Any


@dataclass
class _ToolsetTool:
    toolset: Any
    tool_def: Any


@dataclass
class _RunContext:
    deps: Any = None
    tool_call_id: Any = "call-1"
    tool_call_approved: Any = False
    tool_call_metadata: Any = None


class _ApprovalRequired(Exception):
    def __init__(self, metadata: dict[str, Any] | None = None) -> None:
        self.metadata = metadata


@dataclass
class _DeferredCall:
    tool_name: Any
    args: Any
    tool_call_id: Any

    def args_as_dict(self) -> Any:
        if isinstance(self.args, str):
            return json.loads(self.args)
        return self.args


@dataclass
class _ToolDenied:
    message: str


@dataclass
class _DeferredToolResults:
    approvals: dict[str, Any]
    metadata: dict[str, dict[str, Any]]


@dataclass
class _DeferredToolRequests:
    approvals: list[Any] = field(default_factory=list)
    metadata: Any = field(default_factory=dict)

    def build_results(
        self,
        *,
        approvals: dict[str, Any],
        metadata: dict[str, dict[str, Any]],
    ) -> _DeferredToolResults:
        return _DeferredToolResults(approvals=approvals, metadata=metadata)


class _InnerToolset(_AbstractToolset):
    def __init__(self, names: tuple[str, ...] = ("read_file", "send_message")) -> None:
        self.names = names
        self.calls: list[tuple[str, dict[str, Any], Any]] = []

    async def get_tools(self, _ctx: Any) -> dict[str, _ToolsetTool]:
        return {
            name: _ToolsetTool(toolset=self, tool_def=_ToolDefinition(name)) for name in self.names
        }

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        _ctx: Any,
        tool: Any,
    ) -> str:
        self.calls.append((name, arguments, tool))
        return "executed"


@pytest.fixture
def fake_pydantic_ai(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = SimpleNamespace(
        AbstractToolset=_AbstractToolset,
        WrapperToolset=_WrapperToolset,
        ToolsetTool=_ToolsetTool,
        RunContext=_RunContext,
        ApprovalRequired=_ApprovalRequired,
        DeferredToolRequests=_DeferredToolRequests,
        ToolDenied=_ToolDenied,
    )

    def fake_import(name: str) -> Any:
        if name == "pydantic_ai":
            return runtime
        raise ImportError(name)

    monkeypatch.setattr(adapter_module, "import_module", fake_import)


@pytest.fixture
def bindings() -> BoundToolCatalog:
    policy = Policy.from_dict(
        {
            "schema_version": 1,
            "id": "pydantic-ai-test",
            "version": "1",
            "default_effect": "deny",
            "rules": [
                {
                    "id": "deny-delete",
                    "effect": "deny",
                    "priority": 0,
                    "message": "Delete is forbidden.",
                    "conditions": [
                        {"field": "action.arguments.mode", "operator": "eq", "value": "delete"}
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
                        {"field": "action.arguments.mode", "operator": "eq", "value": "read"}
                    ],
                },
                {
                    "id": "review-send",
                    "effect": "review",
                    "priority": 20,
                    "message": "Send mode needs review.",
                    "conditions": [
                        {"field": "action.arguments.mode", "operator": "eq", "value": "send"},
                        {"field": "context.approval", "operator": "not_exists"},
                    ],
                },
            ],
        }
    )
    catalog = ToolCatalog.from_dict(
        {
            "tool_catalog_version": 1,
            "id": "pydantic-ai-tools",
            "version": "1",
            "description": "Trusted Pydantic AI test tools.",
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


async def _run_wrapper(adapter: Any, ctx: _RunContext) -> tuple[Any, dict[str, Any]]:
    wrapper = await adapter.toolset.for_run(ctx)
    return wrapper, await wrapper.get_tools(ctx)


def _request_from_error(
    error: _ApprovalRequired,
    *,
    arguments: dict[str, Any],
    name: str = "send_message",
    call_id: str = "call-1",
) -> _DeferredToolRequests:
    assert error.metadata is not None
    return _DeferredToolRequests(
        approvals=[_DeferredCall(name, arguments, call_id)],
        metadata={call_id: error.metadata},
    )


def test_factory_is_optional_and_validates_runtime(
    fake_pydantic_ai: None,
    bindings: BoundToolCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inner = _InnerToolset()
    adapter = create_pydantic_ai_tool_policy(bindings, inner)
    assert adapter.bindings is bindings
    assert isinstance(adapter.toolset, _WrapperToolset)
    assert adapter.toolset.wrapped is inner
    assert PYDANTIC_AI_ADAPTER_VERSION == 1
    assert PYDANTIC_AI_REVIEW_METADATA_KEY == "samsarix.tool_call.review"
    assert PYDANTIC_AI_APPROVAL_METADATA_KEY == "samsarix.tool_call.approval"

    with pytest.raises(TypeError, match="BoundToolCatalog"):
        create_pydantic_ai_tool_policy(object(), inner)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="AbstractToolset"):
        create_pydantic_ai_tool_policy(bindings, object())

    async def async_provider(_context: Any) -> dict[str, Any]:
        return {}

    with pytest.raises(TypeError, match="synchronous callable"):
        create_pydantic_ai_tool_policy(bindings, inner, actor_provider=async_provider)
    with pytest.raises(TypeError, match="remember and consume"):
        create_pydantic_ai_tool_policy(bindings, inner, approval_store=object())

    monkeypatch.setattr(
        adapter_module,
        "import_module",
        lambda _name: (_ for _ in ()).throw(ImportError("missing")),
    )
    with pytest.raises(PydanticAIIntegrationError, match=r"\[pydantic-ai\]"):
        create_pydantic_ai_tool_policy(bindings, inner)


def test_registry_is_exact_and_snapshotted_per_run_step(
    fake_pydantic_ai: None,
    bindings: BoundToolCatalog,
) -> None:
    inner = _InnerToolset()
    adapter = create_pydantic_ai_tool_policy(bindings, inner)
    ctx = _RunContext()
    wrapper, tools = asyncio.run(_run_wrapper(adapter, ctx))
    assert wrapper is not adapter.toolset
    assert set(tools) == {"read_file", "send_message"}

    different = _ToolsetTool(inner, _ToolDefinition("read_file"))
    with pytest.raises(PydanticAIIntegrationError, match="verified run-step"):
        asyncio.run(wrapper.call_tool("read_file", {"mode": "read"}, ctx, different))

    inner.names = ("read_file",)
    with pytest.raises(ToolCatalogValidationError, match="missing from registry"):
        asyncio.run(wrapper.get_tools(ctx))


def test_allow_executes_detached_arguments_once_and_deny_never_executes(
    fake_pydantic_ai: None,
    bindings: BoundToolCatalog,
) -> None:
    inner = _InnerToolset()
    adapter = create_pydantic_ai_tool_policy(bindings, inner)
    ctx = _RunContext()
    wrapper, tools = asyncio.run(_run_wrapper(adapter, ctx))
    arguments = {"mode": "read", "nested": {"value": 1}}

    assert (
        asyncio.run(wrapper.call_tool("read_file", arguments, ctx, tools["read_file"]))
        == "executed"
    )
    executed = inner.calls[0][1]
    assert executed == arguments
    assert executed is not arguments
    assert executed["nested"] is not arguments["nested"]

    with pytest.raises(ToolCallDeniedError):
        asyncio.run(
            wrapper.call_tool("send_message", {"mode": "delete"}, ctx, tools["send_message"])
        )
    assert len(inner.calls) == 1


def test_review_builds_exact_results_and_resumes_or_rejects(
    fake_pydantic_ai: None,
    bindings: BoundToolCatalog,
) -> None:
    inner = _InnerToolset()
    adapter = create_pydantic_ai_tool_policy(bindings, inner)
    arguments = {"mode": "send", "recipient": "person@example.com"}
    initial_ctx = _RunContext()
    wrapper, tools = asyncio.run(_run_wrapper(adapter, initial_ctx))

    with pytest.raises(_ApprovalRequired) as captured:
        asyncio.run(
            wrapper.call_tool("send_message", arguments, initial_ctx, tools["send_message"])
        )
    request = _request_from_error(captured.value, arguments=arguments)
    payload = request.metadata["call-1"][PYDANTIC_AI_REVIEW_METADATA_KEY]
    assert payload == {
        "type": "samsarix.tool_call.review",
        "adapter_version": 1,
        "approval_binding": {
            "approval_version": 1,
            "tool_call_id": "call-1",
            "tool_call_fingerprint": bindings["send_message"].fingerprint("call-1", arguments),
        },
        "tool": {"name": "send_message", "arguments": arguments},
        "policy": {
            "id": "pydantic-ai-test",
            "version": "1",
            "fingerprint": bindings.gate.policy_fingerprint,
            "decisive_rule_ids": ["review-send"],
        },
    }
    assert inner.calls == []

    approved = adapter.build_results(request, {"call-1": True})
    assert approved.approvals == {"call-1": True}
    resumed_ctx = _RunContext(
        tool_call_approved=True,
        tool_call_metadata=approved.metadata["call-1"],
    )
    resumed_wrapper, resumed_tools = asyncio.run(_run_wrapper(adapter, resumed_ctx))
    assert (
        asyncio.run(
            resumed_wrapper.call_tool(
                "send_message", arguments, resumed_ctx, resumed_tools["send_message"]
            )
        )
        == "executed"
    )
    assert len(inner.calls) == 1

    replay_wrapper, replay_tools = asyncio.run(_run_wrapper(adapter, resumed_ctx))
    with pytest.raises(PydanticAIIntegrationError, match="already consumed"):
        asyncio.run(
            replay_wrapper.call_tool(
                "send_message", arguments, resumed_ctx, replay_tools["send_message"]
            )
        )
    assert len(inner.calls) == 1

    rejected = adapter.build_results(request, {"call-1": False})
    assert rejected.approvals == {"call-1": _ToolDenied("Tool call rejected by human review.")}
    assert rejected.metadata == {}


def test_approved_resume_rejects_mutated_arguments_actor_and_evidence(
    fake_pydantic_ai: None,
    bindings: BoundToolCatalog,
) -> None:
    def actor_provider(deps: Any) -> dict[str, Any]:
        return {"id": deps["actor_id"]}

    inner = _InnerToolset()
    adapter = create_pydantic_ai_tool_policy(bindings, inner, actor_provider=actor_provider)
    deps = {"actor_id": "reviewed"}
    arguments = {"mode": "send", "recipient": "original@example.com"}
    initial_ctx = _RunContext(deps=deps)
    wrapper, tools = asyncio.run(_run_wrapper(adapter, initial_ctx))
    with pytest.raises(_ApprovalRequired) as captured:
        asyncio.run(
            wrapper.call_tool("send_message", arguments, initial_ctx, tools["send_message"])
        )
    request = _request_from_error(captured.value, arguments=arguments)
    result = adapter.build_results(request, {"call-1": True})
    resumed_ctx = _RunContext(
        deps=deps,
        tool_call_approved=True,
        tool_call_metadata=result.metadata["call-1"],
    )
    resumed_wrapper, resumed_tools = asyncio.run(_run_wrapper(adapter, resumed_ctx))

    with pytest.raises(PydanticAIIntegrationError, match="does not match"):
        asyncio.run(
            resumed_wrapper.call_tool(
                "send_message",
                {"mode": "send", "recipient": "changed@example.com"},
                resumed_ctx,
                resumed_tools["send_message"],
            )
        )
    deps["actor_id"] = "changed"
    with pytest.raises(PydanticAIIntegrationError, match="does not match"):
        asyncio.run(
            resumed_wrapper.call_tool(
                "send_message", arguments, resumed_ctx, resumed_tools["send_message"]
            )
        )

    invalid_evidence = (
        (None, PydanticAIIntegrationError),
        ({}, InputValidationError),
        ({PYDANTIC_AI_APPROVAL_METADATA_KEY: {"approved": True}}, InputValidationError),
    )
    for metadata, error_type in invalid_evidence:
        missing_ctx = _RunContext(
            deps={"actor_id": "reviewed"},
            tool_call_approved=True,
            tool_call_metadata=metadata,
        )
        missing_wrapper, missing_tools = asyncio.run(_run_wrapper(adapter, missing_ctx))
        with pytest.raises(error_type):
            asyncio.run(
                missing_wrapper.call_tool(
                    "send_message", arguments, missing_ctx, missing_tools["send_message"]
                )
            )
    assert inner.calls == []


@pytest.mark.parametrize(
    ("decisions", "match"),
    [
        ({"other": True}, "pending approval"),
        ({"call-1": 1}, "must be a boolean"),
        ({1: True}, "ID must be a string"),
    ],
    ids=["unknown", "non-boolean", "non-string-id"],
)
def test_build_results_validates_decisions(
    fake_pydantic_ai: None,
    bindings: BoundToolCatalog,
    decisions: Any,
    match: str,
) -> None:
    adapter = create_pydantic_ai_tool_policy(bindings, _InnerToolset())
    request = _valid_deferred_request()
    with pytest.raises(PydanticAIIntegrationError, match=match):
        adapter.build_results(request, decisions)


def test_build_results_bounds_deferred_approvals(
    fake_pydantic_ai: None,
    bindings: BoundToolCatalog,
) -> None:
    adapter = create_pydantic_ai_tool_policy(bindings, _InnerToolset())
    malformed = _DeferredToolRequests()
    malformed.approvals = None  # type: ignore[assignment]
    with pytest.raises(PydanticAIIntegrationError, match="must be a list"):
        adapter.build_results(malformed, {})

    oversized = _DeferredToolRequests(
        approvals=[_DeferredCall("send_message", {}, f"call-{index}") for index in range(257)]
    )
    with pytest.raises(PydanticAIIntegrationError, match="exceed the limit"):
        adapter.build_results(oversized, {})


def _valid_deferred_request() -> _DeferredToolRequests:
    arguments = {"mode": "send"}
    return _DeferredToolRequests(
        approvals=[_DeferredCall("send_message", arguments, "call-1")],
        metadata={
            "call-1": {
                PYDANTIC_AI_REVIEW_METADATA_KEY: {
                    "type": PYDANTIC_AI_REVIEW_METADATA_KEY,
                    "adapter_version": 1,
                    "approval_binding": {
                        "approval_version": 1,
                        "tool_call_id": "call-1",
                        "tool_call_fingerprint": "v1:sha256:" + "0" * 64,
                    },
                    "tool": {"name": "send_message", "arguments": arguments},
                }
            }
        },
    )


@pytest.mark.parametrize(
    "pending_arguments",
    [{"mode": "send"}, '{"mode":"send"}'],
    ids=["mapping", "json-string"],
)
def test_build_results_normalizes_pending_arguments(
    fake_pydantic_ai: None,
    bindings: BoundToolCatalog,
    pending_arguments: Any,
) -> None:
    adapter = create_pydantic_ai_tool_policy(bindings, _InnerToolset())
    request = _valid_deferred_request()
    request.approvals[0].args = pending_arguments

    results = adapter.build_results(request, {"call-1": True})

    assert results.approvals == {"call-1": True}
    assert PYDANTIC_AI_APPROVAL_METADATA_KEY in results.metadata["call-1"]


def test_build_results_rejects_mutated_request_metadata(
    fake_pydantic_ai: None,
    bindings: BoundToolCatalog,
) -> None:
    adapter = create_pydantic_ai_tool_policy(bindings, _InnerToolset())
    request = _valid_deferred_request()
    valid_payload = request.metadata["call-1"][PYDANTIC_AI_REVIEW_METADATA_KEY]
    mutations = (
        (None, PydanticAIIntegrationError),
        ({}, PydanticAIIntegrationError),
        ({**valid_payload, "type": "other"}, PydanticAIIntegrationError),
        ({**valid_payload, "adapter_version": 2}, PydanticAIIntegrationError),
        ({**valid_payload, "approval_binding": {}}, PydanticAIIntegrationError),
        (
            {
                **valid_payload,
                "tool": {"name": "read_file", "arguments": {"mode": "send"}},
            },
            PydanticAIIntegrationError,
        ),
        (
            {
                **valid_payload,
                "tool": {"name": "send_message", "arguments": {"mode": "changed"}},
            },
            PydanticAIIntegrationError,
        ),
    )
    for payload, error_type in mutations:
        request.metadata["call-1"][PYDANTIC_AI_REVIEW_METADATA_KEY] = payload
        with pytest.raises(error_type):
            adapter.build_results(request, {"call-1": True})


def test_facts_are_fresh_and_programming_errors_propagate(
    fake_pydantic_ai: None,
    bindings: BoundToolCatalog,
) -> None:
    seen: list[Any] = []

    def context_provider(deps: Any) -> dict[str, Any]:
        seen.append(deps)
        return {"tenant": deps["tenant"]}

    inner = _InnerToolset()
    adapter = create_pydantic_ai_tool_policy(bindings, inner, context_provider=context_provider)
    deps = {"tenant": "acme"}
    ctx = _RunContext(deps=deps)
    wrapper, tools = asyncio.run(_run_wrapper(adapter, ctx))
    assert (
        asyncio.run(wrapper.call_tool("read_file", {"mode": "read"}, ctx, tools["read_file"]))
        == "executed"
    )
    assert seen == [deps]

    malformed = create_pydantic_ai_tool_policy(
        bindings,
        _InnerToolset(),
        context_provider=lambda _deps: [],  # type: ignore[arg-type,return-value]
    )
    malformed_ctx = _RunContext()
    malformed_wrapper, malformed_tools = asyncio.run(_run_wrapper(malformed, malformed_ctx))
    with pytest.raises(PydanticAIIntegrationError, match="mapping or None"):
        asyncio.run(
            malformed_wrapper.call_tool(
                "read_file",
                {"mode": "read"},
                malformed_ctx,
                malformed_tools["read_file"],
            )
        )

    def broken(_deps: Any) -> dict[str, Any]:
        raise RuntimeError("application bug")

    broken_adapter = create_pydantic_ai_tool_policy(
        bindings, _InnerToolset(), context_provider=broken
    )
    broken_ctx = _RunContext()
    broken_wrapper, broken_tools = asyncio.run(_run_wrapper(broken_adapter, broken_ctx))
    with pytest.raises(RuntimeError, match="application bug"):
        asyncio.run(
            broken_wrapper.call_tool(
                "read_file", {"mode": "read"}, broken_ctx, broken_tools["read_file"]
            )
        )


def test_non_json_arguments_and_inner_errors_are_not_hidden(
    fake_pydantic_ai: None,
    bindings: BoundToolCatalog,
) -> None:
    class BrokenInner(_InnerToolset):
        async def call_tool(self, *args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("callback failed")

    inner = BrokenInner()
    adapter = create_pydantic_ai_tool_policy(bindings, inner)
    ctx = _RunContext()
    wrapper, tools = asyncio.run(_run_wrapper(adapter, ctx))
    with pytest.raises(InputValidationError, match="non-JSON"):
        asyncio.run(
            wrapper.call_tool(
                "read_file",
                {"mode": "read", "value": object()},
                ctx,
                tools["read_file"],
            )
        )
    with pytest.raises(RuntimeError, match="callback failed"):
        asyncio.run(wrapper.call_tool("read_file", {"mode": "read"}, ctx, tools["read_file"]))
