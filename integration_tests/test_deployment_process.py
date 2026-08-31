"""Actual owned-process death and restart; not an OS/power-loss simulator."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from deployment_process_worker import READERS, WRITERS

import samsarix_ethics
from samsarix_ethics import (
    ContextContract,
    Policy,
    ToolCatalog,
    authenticate_tool_gate_deployment,
    create_policy_deployment,
    create_tool_gate_deployment,
    fingerprint_policy,
    generate_deployment_auth_key,
)

KINDS = ["policy", "deployment", "catalog", "envelope"]
WORKER = Path(__file__).with_name("deployment_process_worker.py")


def _command(*arguments: str) -> list[str]:
    # Windows venv redirectors can leave the real interpreter alive when only their
    # launcher is killed. Launch the base interpreter directly, with this exact
    # installed/source package root and no site initialization. The core needs no deps.
    executable = Path(sys.base_prefix) / "python.exe" if os.name == "nt" else Path(sys.executable)
    assert executable.is_file()
    return [str(executable), "-S", str(WORKER), *arguments]


def _environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(Path(samsarix_ethics.__file__).parents[1])
    return environment


def _policy(version: int) -> Policy:
    return Policy.from_dict(
        {
            "schema_version": 1,
            "id": "support-policy",
            "version": str(version),
            "default_effect": "deny",
            "rules": [
                {
                    "id": "read-control",
                    "effect": "allow" if version == 1 else "deny",
                    "conditions": [
                        {"field": "action.operation", "operator": "eq", "value": "read"}
                    ],
                }
            ],
        }
    )


def _artifact(kind: str, version: int, key: bytes, **claims: Any) -> Any:
    policy = _policy(version)
    if kind == "policy":
        return policy
    contract = ContextContract.from_dict(
        {
            "context_contract_version": 1,
            "id": "support-context",
            "version": str(version),
            "fields": {
                "action": {"type": "object", "required": True},
                "action.operation": {"type": "string", "required": True},
            },
        }
    )
    deployment = create_policy_deployment(policy, contract)
    if kind == "deployment":
        return deployment
    catalog = ToolCatalog.from_dict(
        {
            "tool_catalog_version": 1,
            "id": "support-tools",
            "version": str(version),
            "tools": [
                {"name": "read", "capabilities": ["resource:read"]},
                {"name": "delete", "capabilities": ["resource:destructive"]},
            ],
        }
    )
    complete = create_tool_gate_deployment(deployment, catalog)
    if kind == "catalog":
        return complete
    now = datetime.now(UTC).replace(microsecond=0)
    authentication = {
        "key_id": "test-key",
        "audience": "support:test",
        "sequence": version,
        "issued_at": (now - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        **claims,
    }
    return authenticate_tool_gate_deployment(complete, key, **authentication)


def _restart(kind: str, target: Path, key_path: Path, minimum: int = 1) -> tuple[int, Any]:
    result = subprocess.run(  # noqa: S603 - fixed owned interpreter/fixture, no shell
        _command("restart", kind, str(target), str(key_path), str(minimum)),
        capture_output=True,
        env=_environment(),
        timeout=15,
        check=False,
    )
    assert not result.stderr, result.stderr.decode()
    assert len(result.stdout) < 4096
    return result.returncode, json.loads(result.stdout)


@contextmanager
def _paused_writer(
    kind: str, target: Path, candidate: Path, stage: str, force: bool
) -> Iterator[Any]:
    process = subprocess.Popen(  # noqa: S603 - fixed owned interpreter/fixture, no shell
        _command(
            "publish", kind, str(target), str(candidate), stage, "replace" if force else "new"
        ),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_environment(),
    )
    assert process.stdout is not None
    with ThreadPoolExecutor(max_workers=1) as reader:
        ready = reader.submit(process.stdout.readline, 4096)
        try:
            line = ready.result(timeout=15)
            assert line, "Writer exited before the requested checkpoint"
            report = json.loads(line)
            assert report == {"phase": stage, "pid": process.pid}
            assert process.poll() is None
            yield process
        finally:
            if process.poll() is None:
                process.kill()
            # Killing this exact process closes its pipes and unblocks the bounded reader.
            ready.result(timeout=5)
            process.communicate(timeout=5)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("force", [False, True], ids=["create", "replace"])
@pytest.mark.parametrize("stage", ["partial", "fsynced", "published"])
def test_killed_publisher_leaves_only_absent_prior_or_complete_current_artifact(
    tmp_path: Path, kind: str, force: bool, stage: str
) -> None:
    target, candidate = tmp_path / "active.json", tmp_path / "candidate.json"
    key_path = tmp_path / "test-key"
    key = generate_deployment_auth_key()
    key_path.write_bytes(key)
    old, new = _artifact(kind, 1, key), _artifact(kind, 2, key)
    if force:
        WRITERS[kind](target, old)
    WRITERS[kind](candidate, new)
    with _paused_writer(kind, target, candidate, stage, force) as process:
        worker_pid = process.pid
        process.kill()
        process.wait(timeout=5)
        assert process.returncode != 0
    assert not (tmp_path / f"unwound-{worker_pid}").exists()
    published = stage == "published"
    expected = new if published else old
    if force or published:
        assert READERS[kind](target) == expected
        code, report = _restart(kind, target, key_path)
        assert code == 0 and report["status"] == "ready"
        version = 2 if published else 1
        assert report["fingerprint"] == fingerprint_policy(_policy(version))
        assert report["read"] == ("deny" if published else "allow")
        assert report["delete"] == "deny"
        assert report["calls"] == (
            ["read"] if kind in {"catalog", "envelope"} and not published else []
        )
        if kind in {"policy", "deployment"}:
            assert report["generation"] == 1
            assert report["contract_version"] == (str(version) if kind == "deployment" else None)
    else:
        assert not target.exists()
        code, report = _restart(kind, target, key_path)
        assert code == 2 and report["status"] == "rejected" and report["calls"] == []
    orphans = list(tmp_path.glob(".active.json.*"))
    assert len(orphans) == (0 if force and published else 1)
    if stage == "partial":
        assert len(orphans[0].read_bytes()) < len(candidate.read_bytes())


@pytest.mark.parametrize("kind", KINDS)
def test_concurrent_exclusive_publishers_never_overwrite_the_winner(
    tmp_path: Path, kind: str
) -> None:
    target = tmp_path / "active.json"
    paths = [tmp_path / "one.json", tmp_path / "two.json"]
    key = generate_deployment_auth_key()
    artifacts = [_artifact(kind, version, key) for version in (1, 2)]
    for path, artifact in zip(paths, artifacts, strict=True):
        WRITERS[kind](path, artifact)
    with (
        _paused_writer(kind, target, paths[0], "before-publish", False) as one,
        _paused_writer(kind, target, paths[1], "before-publish", False) as two,
    ):
        for process in (one, two):
            process.stdin.write(b"c")
            process.stdin.flush()
        results = [process.communicate(timeout=15) for process in (one, two)]
        codes = [process.returncode for process in (one, two)]
        assert sorted(codes) == [0, 2]
        for index, (output, errors) in enumerate(results):
            assert errors == b""
            assert json.loads(output)["status"] == (
                "published" if codes[index] == 0 else "rejected"
            )
        assert READERS[kind](target) == artifacts[codes.index(0)]
    assert list(tmp_path.glob(".active.json.*")) == []


@pytest.mark.parametrize("failure", ["key", "audience", "expired", "future", "rollback", "tamper"])
def test_restart_reauthenticates_before_exposing_callbacks(tmp_path: Path, failure: str) -> None:
    target, key_path = tmp_path / "active.json", tmp_path / "test-key"
    key = generate_deployment_auth_key()
    key_path.write_bytes(generate_deployment_auth_key() if failure == "key" else key)
    claims: dict[str, Any] = {}
    now = datetime.now(UTC).replace(microsecond=0)
    if failure == "audience":
        claims["audience"] = "other:workload"
    elif failure == "expired":
        claims["issued_at"] = (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        claims["expires_at"] = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    elif failure == "future":
        claims["issued_at"] = (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        claims["expires_at"] = (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    artifact = _artifact("envelope", 1, key, **claims)
    WRITERS["envelope"](target, artifact)
    if failure == "tamper":
        value = artifact.to_dict()
        value["mac"] = value["mac"][:-1] + ("0" if value["mac"][-1] != "0" else "1")
        target.write_text(json.dumps(value), encoding="utf-8")
    code, result = _restart("envelope", target, key_path, minimum=2 if failure == "rollback" else 1)
    assert code == 2
    assert result == {
        "status": "rejected",
        "error_type": "DeploymentAuthenticationError",
        "calls": [],
    }


@pytest.mark.parametrize("kind", KINDS)
def test_corrupt_active_file_is_rejected_without_searching_old_or_staged_files(
    tmp_path: Path, kind: str
) -> None:
    key_path, target = tmp_path / "test-key", tmp_path / "active.json"
    key = generate_deployment_auth_key()
    key_path.write_bytes(key)
    artifact = _artifact(kind, 1, key)
    WRITERS[kind](tmp_path / "previous.json", artifact)
    WRITERS[kind](tmp_path / ".active.json.abandoned", artifact)
    target.write_bytes(b'{"incomplete":')
    code, result = _restart(kind, target, key_path)
    assert code == 2 and result["status"] == "rejected" and result["calls"] == []
