"""Authenticated tool-gate deployment envelope behavior and boundaries."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from samsarix_ethics import (
    MAX_DEPLOYMENT_AUTH_KEYS,
    MAX_TOOL_GATE_DEPLOYMENT_ENVELOPE_BYTES,
    DeploymentAuthenticationError,
    Outcome,
    ToolDispatcher,
    ToolGate,
    ToolGateDeployment,
    ToolGateDeploymentEnvelope,
    VerifiedToolGateDeployment,
    authenticate_tool_gate_deployment,
    create_tool_gate_deployment,
    fingerprint_tool_gate_deployment,
    generate_deployment_auth_key,
    get_tool_gate_deployment_envelope_schema,
    load_policy_deployment,
    load_tool_catalog,
    load_tool_gate_deployment_envelope,
    verify_tool_gate_deployment_envelope,
    write_tool_gate_deployment_envelope,
)

_ROOT = Path(__file__).parents[1]
_POLICY_DEPLOYMENT = _ROOT / "examples/deployment/coding-agent-baseline.deployment.json"
_CATALOG = _ROOT / "examples/catalogs/coding-agent-tools.json"
_KEY = b"authenticated-deployment-test-key"
_KEY_ID = "prod-2026-q3"
_AUDIENCE = "coding-agent:production"
_ISSUED = "2026-08-02T12:00:00Z"
_EXPIRES = "2026-08-03T12:00:00Z"
_NOW = datetime(2026, 8, 2, 18, tzinfo=UTC)


def _deployment() -> ToolGateDeployment:
    return create_tool_gate_deployment(
        load_policy_deployment(_POLICY_DEPLOYMENT),
        load_tool_catalog(_CATALOG),
    )


def _envelope(*, key: bytes = _KEY, sequence: int = 42) -> ToolGateDeploymentEnvelope:
    return authenticate_tool_gate_deployment(
        _deployment(),
        key,
        key_id=_KEY_ID,
        audience=_AUDIENCE,
        sequence=sequence,
        issued_at=_ISSUED,
        expires_at=_EXPIRES,
    )


def _verify(
    envelope: ToolGateDeploymentEnvelope,
    **changes: Any,
) -> VerifiedToolGateDeployment:
    arguments: dict[str, Any] = {
        "expected_audience": _AUDIENCE,
        "minimum_sequence": 42,
        "now": _NOW,
    }
    arguments.update(changes)
    return verify_tool_gate_deployment_envelope(envelope, {_KEY_ID: _KEY}, **arguments)


def test_pinned_fingerprint_and_mac_vector() -> None:
    envelope = _envelope()

    assert fingerprint_tool_gate_deployment(envelope.deployment) == (
        "v1:sha256:49f3430784cb194aede8b56efbe7447f52af9111909e0327d39e24fd3589f2f6"
    )
    assert envelope.mac == (
        "v1:hmac-sha256:0d7dfef907f22b95fd2c084e3cba909e388711d0e7cd8f21009e8a49ad9c0b9f"
    )


def test_key_generation_returns_fresh_256_bit_values() -> None:
    first = generate_deployment_auth_key()
    second = generate_deployment_auth_key()

    assert len(first) == 32
    assert len(second) == 32
    assert first != second


def test_round_trip_is_detached_and_verifies_current_claims() -> None:
    envelope = _envelope()
    value = envelope.to_dict()
    parsed = ToolGateDeploymentEnvelope.from_dict(value)
    value["deployment"]["tool_catalog"]["id"] = "changed"
    verified = _verify(parsed)

    assert parsed == envelope
    assert parsed.deployment.tool_catalog.id == "coding-agent-tools"
    assert verified.deployment is parsed.deployment
    assert verified.key_id == _KEY_ID
    assert verified.audience == _AUDIENCE
    assert verified.sequence == 42
    assert verified.verified_at == "2026-08-02T18:00:00Z"
    assert verified.deployment_fingerprint == parsed.deployment_fingerprint
    assert "capabilities" not in repr(parsed)
    assert "capabilities" not in repr(verified)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("audience", "coding-agent:staging", "MAC verification failed"),
        ("sequence", 43, "MAC verification failed"),
        ("issued_at", "2026-08-02T12:00:01Z", "MAC verification failed"),
        ("expires_at", "2026-08-03T11:59:59Z", "MAC verification failed"),
        ("key_id", "replacement-key", "not trusted"),
        ("mac", "v1:hmac-sha256:" + "0" * 64, "MAC verification failed"),
    ],
)
def test_authenticated_claim_tampering_fails(field: str, value: Any, message: str) -> None:
    document = _envelope().to_dict()
    document[field] = value
    parsed = ToolGateDeploymentEnvelope.from_dict(document)

    with pytest.raises(DeploymentAuthenticationError, match=message):
        _verify(parsed)


def test_embedded_deployment_tampering_fails_before_authentication() -> None:
    document = _envelope().to_dict()
    document["deployment"]["tool_catalog"]["version"] = "replaced"

    with pytest.raises(DeploymentAuthenticationError, match="fingerprint does not match"):
        ToolGateDeploymentEnvelope.from_dict(document)


def test_wrong_key_audience_sequence_and_time_fail_closed() -> None:
    envelope = _envelope()
    with pytest.raises(DeploymentAuthenticationError, match="MAC verification failed"):
        verify_tool_gate_deployment_envelope(
            envelope,
            {_KEY_ID: b"x" * 32},
            expected_audience=_AUDIENCE,
            now=_NOW,
        )
    with pytest.raises(DeploymentAuthenticationError, match="audience does not match"):
        _verify(envelope, expected_audience="coding-agent:staging")
    with pytest.raises(DeploymentAuthenticationError, match="older than"):
        _verify(envelope, minimum_sequence=43)
    with pytest.raises(DeploymentAuthenticationError, match="not yet valid"):
        _verify(envelope, now=datetime(2026, 8, 2, 11, 59, 59, tzinfo=UTC))
    with pytest.raises(DeploymentAuthenticationError, match="expired"):
        _verify(envelope, now=datetime(2026, 8, 3, 12, tzinfo=UTC))

    assert (
        _verify(
            envelope,
            now=datetime(2026, 8, 2, 11, 59, 59, tzinfo=UTC),
            clock_skew_seconds=1,
        ).sequence
        == 42
    )
    assert (
        _verify(
            envelope,
            now=datetime(2026, 8, 3, 12, tzinfo=UTC),
            clock_skew_seconds=1,
        ).sequence
        == 42
    )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"tool_gate_deployment_auth_version": True}, "version must be 1"),
        ({"algorithm": "none"}, "algorithm must be"),
        ({"key_id": "bad key"}, "key_id must be"),
        ({"audience": "bad audience"}, "audience must be"),
        ({"sequence": True}, "sequence must be"),
        ({"issued_at": "2026-08-02"}, "issued_at must be"),
        ({"expires_at": _ISSUED}, "later than"),
        ({"expires_at": "2026-09-02T12:00:01Z"}, "lifetime exceeds"),
        ({"deployment_fingerprint": "bad"}, "fingerprint must use"),
        ({"mac": "bad"}, "mac must use"),
    ],
)
def test_envelope_shape_and_claim_validation(changes: dict[str, Any], message: str) -> None:
    document = _envelope().to_dict()
    document.update(changes)

    with pytest.raises(DeploymentAuthenticationError, match=message):
        ToolGateDeploymentEnvelope.from_dict(document)


def test_keyring_and_verifier_parameter_limits() -> None:
    envelope = _envelope()
    with pytest.raises(DeploymentAuthenticationError, match="32-4096"):
        authenticate_tool_gate_deployment(
            _deployment(),
            b"short",
            key_id=_KEY_ID,
            audience=_AUDIENCE,
            sequence=1,
            issued_at=_ISSUED,
            expires_at=_EXPIRES,
        )
    with pytest.raises(DeploymentAuthenticationError, match="exceeds"):
        verify_tool_gate_deployment_envelope(
            envelope,
            {f"key-{index}": b"x" * 32 for index in range(MAX_DEPLOYMENT_AUTH_KEYS + 1)},
            expected_audience=_AUDIENCE,
            now=_NOW,
        )
    with pytest.raises(DeploymentAuthenticationError, match="bytes-like"):
        verify_tool_gate_deployment_envelope(
            envelope,
            {_KEY_ID: "secret"},  # type: ignore[dict-item]
            expected_audience=_AUDIENCE,
            now=_NOW,
        )
    assert (
        verify_tool_gate_deployment_envelope(
            envelope,
            {_KEY_ID: _KEY, "unused": "malformed"},  # type: ignore[dict-item]
            expected_audience=_AUDIENCE,
            now=_NOW,
        ).key_id
        == _KEY_ID
    )
    with pytest.raises(TypeError, match="timezone-aware"):
        _verify(envelope, now=datetime(2026, 8, 2, 18))
    with pytest.raises(ValueError, match="clock_skew_seconds"):
        _verify(envelope, clock_skew_seconds=3601)


def test_direct_construction_and_wrong_public_types_are_rejected() -> None:
    envelope = _envelope()
    with pytest.raises(TypeError, match="created by"):
        VerifiedToolGateDeployment()
    with pytest.raises(TypeError, match="ToolGateDeployment"):
        authenticate_tool_gate_deployment(
            object(),  # type: ignore[arg-type]
            _KEY,
            key_id=_KEY_ID,
            audience=_AUDIENCE,
            sequence=1,
            issued_at=_ISSUED,
            expires_at=_EXPIRES,
        )
    with pytest.raises(TypeError, match="ToolGateDeploymentEnvelope"):
        verify_tool_gate_deployment_envelope(
            object(),  # type: ignore[arg-type]
            {_KEY_ID: _KEY},
            expected_audience=_AUDIENCE,
        )
    with pytest.raises(TypeError, match="mapping"):
        verify_tool_gate_deployment_envelope(
            envelope,
            object(),  # type: ignore[arg-type]
            expected_audience=_AUDIENCE,
        )


def test_atomic_bounded_file_round_trip_duplicate_keys_and_schema(tmp_path: Path) -> None:
    envelope = _envelope()
    path = tmp_path / "gate.authenticated.json"
    assert write_tool_gate_deployment_envelope(path, envelope) == path.resolve()
    assert load_tool_gate_deployment_envelope(path) == envelope
    with pytest.raises(DeploymentAuthenticationError, match="refusing to overwrite"):
        write_tool_gate_deployment_envelope(path, envelope)

    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text(
        json.dumps(envelope.to_dict())[:-1] + ',"algorithm":"hmac-sha256"}',
        encoding="utf-8",
    )
    with pytest.raises(DeploymentAuthenticationError, match="duplicate object key"):
        load_tool_gate_deployment_envelope(duplicate)

    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b"{" + b" " * MAX_TOOL_GATE_DEPLOYMENT_ENVELOPE_BYTES + b"}")
    with pytest.raises(DeploymentAuthenticationError, match="byte limit"):
        load_tool_gate_deployment_envelope(oversized)

    schema = get_tool_gate_deployment_envelope_schema()
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(envelope.to_dict())
    schema["$defs"]["tool_gate_deployment"]["title"] = "changed"
    assert (
        get_tool_gate_deployment_envelope_schema()["$defs"]["tool_gate_deployment"]["title"]
        != "changed"
    )


def test_gate_and_dispatcher_authenticate_immediately_before_binding() -> None:
    envelope = _envelope()
    registered = {tool.name for tool in envelope.deployment.tool_catalog.tools}
    bindings = ToolGate.bind_authenticated_deployment(
        envelope,
        authentication_keys={_KEY_ID: _KEY},
        expected_audience=_AUDIENCE,
        minimum_sequence=42,
        now=_NOW,
        registered_tools=registered,
    )
    assert bindings.authenticated_deployment is not None
    assert bindings.authenticated_deployment.key_id == _KEY_ID
    assert bindings.authenticated_deployment.sequence == 42
    assert bindings.authenticated_deployment.verified_at == "2026-08-02T18:00:00Z"
    assert (
        bindings.authenticated_deployment.deployment_fingerprint == envelope.deployment_fingerprint
    )
    assert (
        bindings["read_file"]
        .enforce(
            {"path": "README.md"},
            actor={"id": "coding-agent"},
            context={"workspace_contained": True},
        )
        .outcome
        is Outcome.ALLOW
    )

    callbacks = {name: (lambda **arguments: arguments) for name in registered}
    dispatcher = ToolDispatcher.bind_authenticated_deployment(
        envelope,
        authentication_keys={_KEY_ID: _KEY},
        expected_audience=_AUDIENCE,
        minimum_sequence=42,
        now=_NOW,
        registered_tools=callbacks,
    )
    assert dispatcher.authenticated_deployment is not None
    assert dispatcher.authenticated_deployment.key_id == _KEY_ID
    assert dispatcher.authenticated_deployment.sequence == 42
    assert dispatcher.authenticated_deployment.verified_at == "2026-08-02T18:00:00Z"
    assert (
        dispatcher.authenticated_deployment.deployment_fingerprint
        == envelope.deployment_fingerprint
    )
    result = dispatcher.execute(
        "read_file",
        {"path": "README.md"},
        actor={"id": "coding-agent"},
        context={"workspace_contained": True},
    )
    assert result.value == {"path": "README.md"}

    with pytest.raises(DeploymentAuthenticationError, match="expired"):
        ToolGate.bind_authenticated_deployment(
            envelope,
            authentication_keys={_KEY_ID: _KEY},
            expected_audience=_AUDIENCE,
            now=datetime(2026, 8, 4, tzinfo=UTC),
            registered_tools=registered,
        )


def test_dispatcher_rejects_authentication_before_inspecting_callbacks() -> None:
    class ExplodingCallbacks(Mapping[str, Any]):
        def __getitem__(self, key: str) -> Any:
            raise AssertionError(f"callback mapping was inspected for {key}")

        def __iter__(self) -> Iterator[str]:
            raise AssertionError("callback mapping was iterated")

        def __len__(self) -> int:
            raise AssertionError("callback mapping length was read")

    with pytest.raises(DeploymentAuthenticationError, match="expired"):
        ToolDispatcher.bind_authenticated_deployment(
            _envelope(),
            authentication_keys={_KEY_ID: _KEY},
            expected_audience=_AUDIENCE,
            now=datetime(2026, 8, 4, tzinfo=UTC),
            registered_tools=ExplodingCallbacks(),
        )
