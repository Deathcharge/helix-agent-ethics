# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Adversarial client boundaries without installing MCP or AnyIO."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
from contextlib import nullcontext
from dataclasses import dataclass, replace
from types import SimpleNamespace
from typing import Any

import pytest

import samsarix_ethics.mcp_client as module
from samsarix_ethics import (
    AuditLogError,
    InputValidationError,
    MCPClientIntegrationError,
    Policy,
    PolicyRuntime,
    ToolCallApproval,
    ToolCallDeniedError,
    ToolCallReviewRequiredError,
    ToolCatalog,
    ToolCatalogValidationError,
    ToolGate,
    create_mcp_client_tool_policy,
    create_policy_deployment,
)


@dataclass
class Tool:
    name: Any = "operate"
    description: str = "A test tool"

    def model_copy(self, *, deep: bool) -> Tool:
        assert deep
        return copy.deepcopy(self)

    def model_dump(self, **_kwargs: Any) -> dict[str, Any]:
        return {"name": self.name, "description": self.description}


@dataclass
class Page:
    tools: Any
    next_cursor: Any = None


class Params(SimpleNamespace):
    @classmethod
    def model_validate(cls, value: dict[str, Any], *, strict: bool) -> Params:
        assert strict
        return cls(**copy.deepcopy(value))

    def model_dump(self, **_kwargs: Any) -> dict[str, Any]:
        return copy.deepcopy(vars(self))


class Session:
    def __init__(self) -> None:
        self.pages = {None: Page([Tool()])}
        self.calls: list[Any] = []
        self.cursors: list[Any] = []
        self.on_list: Any = None
        self.fail: Any = None

    async def list_tools(self, *, params: Any) -> Any:
        self.cursors.append(params.cursor)
        if self.on_list:
            self.on_list()
        return self.pages[params.cursor]

    async def call_tool(self, name: Any, arguments: Any, **kwargs: Any) -> Any:
        self.calls.append((name, arguments, kwargs))
        if self.fail:
            raise self.fail
        return arguments


class Client:
    def __init__(self) -> None:
        self.session = Session()


@pytest.fixture(autouse=True)
def sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    modules = {
        "mcp": SimpleNamespace(Client=Client),
        "mcp.types": SimpleNamespace(
            Tool=Tool,
            ListToolsResult=Page,
            PaginatedRequestParams=Params,
            CallToolRequestParams=Params,
        ),
        "anyio": SimpleNamespace(fail_after=lambda _seconds: nullcontext()),
    }
    monkeypatch.setattr(module, "import_module", modules.__getitem__)


def policy() -> Policy:
    rules: list[dict[str, Any]] = []
    for index, (field, operator, value, effect) in enumerate(
        [
            ("action.arguments.mode", "eq", "delete", "deny"),
            ("context.revoked", "eq", True, "deny"),
            ("context.approval.approved", "eq", True, "allow"),
            ("action.arguments.mode", "eq", "read", "allow"),
            ("action.arguments.mode", "eq", "send", "review"),
        ]
    ):
        conditions: list[Any] = [{"field": field, "operator": operator, "value": value}]
        if effect == "review":
            conditions.append({"field": "context.approval", "operator": "not_exists"})
        rules.append(
            {
                "id": f"rule-{index}",
                "priority": index,
                "effect": effect,
                "message": "Unit test.",
                "conditions": conditions,
            }
        )
    return Policy.from_dict(
        {
            "schema_version": 1,
            "id": "client",
            "version": "1",
            "default_effect": "deny",
            "rules": rules,
        }
    )


def bindings(
    *, runtime: Any = None, audit_sink: Any = None, names: tuple[str, ...] = ("operate",)
) -> Any:
    catalog = ToolCatalog.from_dict(
        {
            "tool_catalog_version": 1,
            "id": "tools",
            "version": "1",
            "tools": [{"name": name, "capabilities": ["external:write"]} for name in names],
        }
    )
    return ToolGate(runtime or policy(), audit_sink=audit_sink).bind_catalog(
        catalog, registered_tools=names
    )


def create(client: Any = None, **kwargs: Any) -> Any:
    return asyncio.run(
        create_mcp_client_tool_policy(
            bindings(), client or Client(), server_id="test-primary", **kwargs
        )
    )


def test_allow_is_detached_single_round_with_captured_session() -> None:
    client = Client()
    session = client.session
    adapter = create(client)
    client.session = Session()
    arguments = {"mode": "read", "nested": [1]}
    meta = {"tenant": "a"}
    result = asyncio.run(adapter.call_tool("operate", arguments, meta=meta))
    result["nested"].append(2)
    assert arguments["nested"] == [1]
    assert len(session.calls) == 1
    assert client.session.calls == []
    kwargs = session.calls[0][2]
    assert kwargs["allow_input_required"] is True
    assert kwargs["allow_claimed"] is False
    assert kwargs["meta"] == meta
    assert kwargs["read_timeout_seconds"] == 30
    assert adapter.bindings.catalog.tool_names == ("operate",)
    assert "tool_count=1" in repr(adapter)
    adapter.tools[0].description = "mutated copy"
    assert adapter.tools[0].description == "A test tool"


@pytest.mark.parametrize(
    "mode,error",
    [
        ("delete", ToolCallDeniedError),
        ("send", ToolCallReviewRequiredError),
        ("unknown", ToolCallDeniedError),
    ],
)
def test_blocked_call_never_sends(mode: str, error: Any) -> None:
    client = Client()
    adapter = create(client)
    with pytest.raises(error):
        asyncio.run(adapter.call_tool("operate", {"mode": mode}))
    assert client.session.calls == []


@pytest.mark.parametrize("name", [None, 1, "unknown"])
def test_unknown_call_never_discovers_again(name: Any) -> None:
    client = Client()
    adapter = create(client)
    with pytest.raises(MCPClientIntegrationError, match="trusted catalog"):
        asyncio.run(adapter.call_tool(name, {}))
    assert client.session.cursors == [None]


@pytest.mark.parametrize("timeout", [True, None, "30", 0, -1, 3601, float("inf"), float("nan")])
def test_timeout_bounds(timeout: Any) -> None:
    with pytest.raises(ValueError, match="timeout"):
        create(timeout_seconds=timeout)
    with pytest.raises(ValueError, match="timeout"):
        create(review_timeout_seconds=timeout)
    if timeout is not None:
        adapter = create()
        with pytest.raises(ValueError, match="timeout"):
            asyncio.run(adapter.call_tool("operate", {"mode": "read"}, timeout))


def test_factory_contracts_and_optional_import(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(TypeError, match="BoundToolCatalog"):
        asyncio.run(create_mcp_client_tool_policy(object(), Client(), server_id="test"))
    with pytest.raises(TypeError, match="connected MCP"):
        create(object())
    for server_id in (None, "", "a/b", "a" * 129):
        with pytest.raises(ValueError, match="server_id"):
            asyncio.run(create_mcp_client_tool_policy(bindings(), Client(), server_id=server_id))
    for provider in ("actor_provider", "context_provider", "approval_provider"):
        with pytest.raises(TypeError, match=provider):
            create(**{provider: 1})

    def missing(_name: str) -> Any:
        raise ImportError("missing")

    monkeypatch.setattr(module, "import_module", missing)
    with pytest.raises(MCPClientIntegrationError, match=r"\[mcp-client\]"):
        create()


@pytest.mark.parametrize(
    "page,error",
    [
        (object(), MCPClientIntegrationError),
        (Page(()), MCPClientIntegrationError),
        (Page([object()]), MCPClientIntegrationError),
        (Page([Tool(1)]), MCPClientIntegrationError),
        (Page([Tool(), Tool()]), MCPClientIntegrationError),
        (Page([]), ToolCatalogValidationError),
        (Page([Tool("extra")]), ToolCatalogValidationError),
        (Page([Tool()], ""), MCPClientIntegrationError),
        (Page([Tool()], 1), MCPClientIntegrationError),
        (Page([Tool()], "a" * 4097), MCPClientIntegrationError),
    ],
)
def test_bad_discovery_fails_closed(page: Any, error: Any) -> None:
    client = Client()
    client.session.pages[None] = page
    with pytest.raises(error):
        create(client)
    assert client.session.calls == []


def test_discovery_limits_and_cycles(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Client()
    client.session.pages = {None: Page([], "loop"), "loop": Page([], "loop")}
    with pytest.raises(MCPClientIntegrationError, match="repeated cursor"):
        create(client)
    monkeypatch.setattr(module, "MAX_MCP_CLIENT_DISCOVERY_PAGES", 1)
    with pytest.raises(MCPClientIntegrationError, match="page limit"):
        create(client)
    client.session.pages = {None: Page([Tool(), Tool("extra")])}
    monkeypatch.setattr(module, "MAX_TOOL_CATALOG_TOOLS", 1)
    with pytest.raises(MCPClientIntegrationError, match="tool limit"):
        create(client)
    monkeypatch.setattr(module, "MAX_MCP_CLIENT_SNAPSHOT_BYTES", 16)
    with pytest.raises(MCPClientIntegrationError, match="byte limit"):
        create(Client())


def test_discovery_order_is_irrelevant_but_content_is_pinned() -> None:
    client = Client()
    adapter = create(client)
    client.session.pages = {None: Page([], "next"), "next": Page([Tool()])}
    assert asyncio.run(adapter.call_tool("operate", {"mode": "read"})) == {"mode": "read"}
    client.session.pages["next"].tools[0].description = "changed"
    with pytest.raises(MCPClientIntegrationError, match="definitions changed"):
        asyncio.run(adapter.call_tool("operate", {"mode": "read"}))
    assert len(client.session.calls) == 1


def test_review_copies_complete_sensitive_request_and_skips_allow_deny() -> None:
    reviews = []
    client = Client()
    original = {"mode": "send", "content": "private-content"}
    meta = {"tenant": "one"}

    async def approve(review: Any) -> ToolCallApproval:
        reviews.append(review)
        payload = review.to_dict()
        assert payload["request"]["meta"] == {"tenant": "one"}
        assert payload["request"]["request_state"] == "next-round"
        assert payload["capabilities"] == ["external:write"]
        assert payload["policy"]["fingerprint"].startswith("v1:sha256:")
        assert "private-content" not in repr(review)
        payload["request"]["arguments"]["content"] = "mutated review copy"
        original["content"] = "mutated original"
        meta["tenant"] = "changed"
        return review.approval(approved=True)

    adapter = create(client, approval_provider=approve)
    result = asyncio.run(
        adapter.call_tool("operate", original, meta=meta, request_state="next-round")
    )
    assert result["content"] == "private-content"
    assert client.session.calls[0][2]["meta"] == {"tenant": "one"}
    assert reviews[0].request["arguments"]["content"] == "private-content"
    asyncio.run(adapter.call_tool("operate", {"mode": "read"}))
    with pytest.raises(ToolCallDeniedError):
        asyncio.run(adapter.call_tool("operate", {"mode": "delete"}))
    assert len(reviews) == 1


@pytest.mark.parametrize(
    "response", ["none", "reject", "nonapproval", "sync", "forged-id", "forged-fp"]
)
def test_invalid_review_response_never_sends(response: str) -> None:
    client = Client()

    async def approve(review: Any) -> Any:
        if response == "none":
            return None
        if response == "nonapproval":
            return True
        if response == "forged-id":
            return ToolCallApproval("different", True, review.tool_call_fingerprint)
        if response == "forged-fp":
            return ToolCallApproval(review.tool_call_id, True, "v1:sha256:" + "0" * 64)
        return review.approval(approved=False)

    adapter = create(
        client, approval_provider=(lambda _review: None) if response == "sync" else approve
    )
    with pytest.raises((MCPClientIntegrationError, InputValidationError)):
        asyncio.run(adapter.call_tool("operate", {"mode": "send"}))
    assert client.session.calls == []


def test_review_replay_and_cross_target_evidence_fail() -> None:
    client = Client()
    evidence = None

    async def approve(review: Any) -> Any:
        nonlocal evidence
        if evidence is None:
            evidence = review.approval(approved=True)
        return evidence

    adapter = create(client, approval_provider=approve)
    asyncio.run(adapter.call_tool("operate", {"mode": "send"}))
    for target in (adapter, replace(adapter, server_id="other-server")):
        with pytest.raises(InputValidationError, match="does not match"):
            asyncio.run(target.call_tool("operate", {"mode": "send"}))
    assert len(client.session.calls) == 1


@pytest.mark.parametrize(
    "part",
    ["server_id", "registry", "arguments", "meta", "input_responses", "request_state", "actor"],
)
def test_complete_request_fingerprint_is_bound(part: str) -> None:
    adapter = create()
    binding = adapter.bindings["operate"]
    request = {"arguments": {}, "meta": None, "input_responses": None, "request_state": None}
    actor: dict[str, Any] = {"id": "a"}
    before = adapter._call_fingerprint(binding, "same-id", request, actor)
    if part == "server_id":
        adapter = replace(adapter, server_id="other")
    elif part == "registry":
        adapter = replace(adapter, registry_fingerprint="other")
    elif part == "actor":
        actor["id"] = "b"
    else:
        request[part] = "changed"
        if part == "arguments":
            request[part] = {"value": "changed"}
    assert before != adapter._call_fingerprint(binding, "same-id", request, actor)


@pytest.mark.parametrize("changed", ["actor", "context", "policy", "registry"])
def test_review_refreshes_trusted_facts_and_registry(changed: str) -> None:
    client = Client()
    actor = {"id": "a"}
    context = {"revoked": False}
    runtime = PolicyRuntime.from_deployment(create_policy_deployment(policy()))

    async def approve(review: Any) -> ToolCallApproval:
        if changed == "actor":
            actor["id"] = "b"
        elif changed == "context":
            context["revoked"] = True
        elif changed == "registry":
            client.session.pages[None].tools[0].description = "changed"
        else:
            denied = Policy.from_dict(
                {
                    "schema_version": 1,
                    "id": "revoked",
                    "version": "2",
                    "default_effect": "deny",
                    "rules": [],
                }
            )
            runtime.activate_deployment(create_policy_deployment(denied), expected_generation=1)
        return review.approval(approved=True)

    adapter = asyncio.run(
        create_mcp_client_tool_policy(
            bindings(runtime=runtime),
            client,
            server_id="test",
            approval_provider=approve,
            actor_provider=lambda: actor,
            context_provider=lambda: context,
        )
    )
    with pytest.raises((InputValidationError, ToolCallDeniedError, MCPClientIntegrationError)):
        asyncio.run(adapter.call_tool("operate", {"mode": "send"}))
    assert client.session.calls == []


def test_untrusted_provider_values_and_reserved_context_fail_closed() -> None:
    async def asynchronous() -> dict[str, Any]:
        return {}

    for kwargs, error in [
        ({"actor_provider": asynchronous}, MCPClientIntegrationError),
        ({"context_provider": lambda: {"mcp": {}}}, InputValidationError),
        ({"actor_provider": lambda: {"nested": object()}}, InputValidationError),
        ({"context_provider": lambda: []}, InputValidationError),
    ]:
        client = Client()
        adapter = create(client, **kwargs)
        with pytest.raises(error):
            asyncio.run(adapter.call_tool("operate", {"mode": "read"}))
        assert client.session.calls == []
    adapter = create(actor_provider=lambda: None, context_provider=lambda: None)
    assert asyncio.run(adapter.call_tool("operate", {"mode": "read"})) == {"mode": "read"}


def test_validation_audit_failure_and_cancellation_never_dispatch() -> None:
    client = Client()

    def audit_failure(_record: Any) -> None:
        raise OSError("audit unavailable")

    adapter = asyncio.run(
        create_mcp_client_tool_policy(bindings(audit_sink=audit_failure), client, server_id="test")
    )
    with pytest.raises(AuditLogError, match="audit sink failed"):
        asyncio.run(adapter.call_tool("operate", {"mode": "read"}))
    with pytest.raises(InputValidationError):
        asyncio.run(adapter.call_tool("operate", {"mode": "read", "x": object()}))
    with pytest.raises(TypeError, match="progress_callback"):
        asyncio.run(adapter.call_tool("operate", {}, progress_callback=1))

    async def cancelled(_review: Any) -> Any:
        raise asyncio.CancelledError()

    adapter = create(client, approval_provider=cancelled)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(adapter.call_tool("operate", {"mode": "send"}))
    assert client.session.calls == []


@pytest.mark.parametrize(
    "failure", [TimeoutError(), RuntimeError("connection lost"), asyncio.CancelledError()]
)
def test_dispatch_failure_is_never_retried(failure: BaseException) -> None:
    client = Client()
    client.session.fail = failure
    adapter = create(client)
    with pytest.raises(type(failure)):
        asyncio.run(adapter.call_tool("operate", {"mode": "read"}))
    assert len(client.session.calls) == 1


def test_discovery_validates_entries_once_and_hashes_once(monkeypatch: pytest.MonkeyPatch) -> None:
    names = tuple(f"tool_{index}" for index in range(64))
    tools = [Tool(name) for name in names]
    client = Client()
    client.session.pages = {None: Page(tools)}
    validations = []
    digests = []
    original_validate = module.validate_context
    original_digest = module._digest

    def validate(value: Any, *, label: str) -> Any:
        validations.append(tuple(value))
        return original_validate(value, label=label)

    def digest(value: Any) -> str:
        digests.append(value)
        return original_digest(value)

    monkeypatch.setattr(module, "validate_context", validate)
    monkeypatch.setattr(module, "_digest", digest)
    adapter = asyncio.run(
        create_mcp_client_tool_policy(bindings(names=names), client, server_id="test")
    )
    assert validations == [(name,) for name in names]
    assert len(digests) == 1
    expected = json.dumps(
        {
            "mcp_client_registry_version": 1,
            "tools": {tool.name: tool.model_dump() for tool in tools},
        },
        sort_keys=True,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("ascii")
    assert adapter.registry_fingerprint == "v1:sha256:" + hashlib.sha256(expected).hexdigest()


@pytest.mark.parametrize("delta", [0, -1])
def test_incremental_discovery_byte_limit_matches_full_canonical_bytes(
    monkeypatch: pytest.MonkeyPatch, delta: int
) -> None:
    tools = [Tool("first", 'Unicode \u00e9, quote " and newline\n'), Tool("second", "end")]
    client = Client()
    client.session.pages = {None: Page(tools[:1], "second-page"), "second-page": Page(tools[1:])}
    expected = json.dumps(
        {
            "mcp_client_registry_version": 1,
            "tools": {tool.name: tool.model_dump() for tool in tools},
        },
        sort_keys=True,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("ascii")
    monkeypatch.setattr(module, "MAX_MCP_CLIENT_SNAPSHOT_BYTES", len(expected) + delta)

    async def construct() -> Any:
        return await create_mcp_client_tool_policy(
            bindings(names=("first", "second")), client, server_id="test"
        )

    if delta == 0:
        adapter = asyncio.run(construct())
        assert adapter.registry_fingerprint == "v1:sha256:" + hashlib.sha256(expected).hexdigest()
    else:
        with pytest.raises(MCPClientIntegrationError, match="byte limit"):
            asyncio.run(construct())


def test_aggregate_item_limit_is_retained_across_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    assert module._container_items({"a": [{}, {"b": [1, 2]}]}) == 6
    client = Client()
    client.session.pages = {
        None: Page([Tool("first")], "second-page"),
        "second-page": Page([Tool("second")], "must-not-fetch"),
    }
    # Each entry has three items and passes by itself, but their sum must be bounded.
    monkeypatch.setattr(module, "MAX_CONTAINER_ITEMS", 5)
    with pytest.raises(InputValidationError, match="aggregate container items"):
        create(client)
    assert client.session.cursors == [None, "second-page"]
