"""Owned subprocess fixture: real file operations, deterministic kill checkpoints."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import samsarix_ethics.io as io_module
from samsarix_ethics import (
    PolicyRuntime,
    SamsarixEthicsError,
    ToolCallDeniedError,
    ToolDispatcher,
    load_policy,
    load_policy_deployment,
    load_tool_gate_deployment,
    load_tool_gate_deployment_envelope,
    write_policy,
    write_policy_deployment,
    write_tool_gate_deployment,
    write_tool_gate_deployment_envelope,
)

READERS = {
    "policy": load_policy,
    "deployment": load_policy_deployment,
    "catalog": load_tool_gate_deployment,
    "envelope": load_tool_gate_deployment_envelope,
}
WRITERS = {
    "policy": write_policy,
    "deployment": write_policy_deployment,
    "catalog": write_tool_gate_deployment,
    "envelope": write_tool_gate_deployment_envelope,
}


def checkpoint(phase: str) -> None:
    print(json.dumps({"phase": phase, "pid": os.getpid()}), flush=True)
    if sys.stdin.buffer.read(1) != b"c":
        raise RuntimeError("Owned test controller disconnected")


def install_checkpoint(selected: str, force: bool) -> None:
    real_temporary = io_module.tempfile.NamedTemporaryFile
    real_fsync = io_module.os.fsync
    real_publish = io_module.os.replace if force else io_module.os.link

    class StagedFile:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.file = real_temporary(*args, **kwargs)

        def __enter__(self) -> Any:
            self.file.__enter__()
            return self

        def __exit__(self, *args: Any) -> Any:
            return self.file.__exit__(*args)

        def __getattr__(self, name: str) -> Any:
            return getattr(self.file, name)

        def write(self, payload: bytes) -> int:
            middle = len(payload) // 2
            self.file.write(payload[:middle])
            self.file.flush()
            if selected == "partial":
                checkpoint(selected)
            self.file.write(payload[middle:])
            return len(payload)

    def fsync(descriptor: int) -> None:
        real_fsync(descriptor)
        if selected == "fsynced":
            checkpoint(selected)

    def publish(*args: Any, **kwargs: Any) -> None:
        if selected == "before-publish":
            checkpoint(selected)
        real_publish(*args, **kwargs)
        if selected == "published":
            checkpoint(selected)

    io_module.tempfile.NamedTemporaryFile = StagedFile
    io_module.os.fsync = fsync
    if force:
        io_module.os.replace = publish
    else:
        io_module.os.link = publish


def restart(kind: str, path: Path, key_path: str, minimum: int) -> None:
    calls: list[str] = []

    def read() -> str:
        calls.append("read")
        return "ticket"

    def delete() -> None:
        calls.append("delete")

    try:
        artifact = READERS[kind](path)
        if kind in {"policy", "deployment"}:
            runtime = (
                PolicyRuntime(artifact)
                if kind == "policy"
                else PolicyRuntime.from_deployment(artifact)
            )
            result = {
                "generation": runtime.status.generation,
                "fingerprint": runtime.policy_fingerprint,
                "contract_version": runtime.status.context_contract_version,
                "read": runtime.evaluate({"action": {"operation": "read"}}).outcome.value,
                "delete": runtime.evaluate({"action": {"operation": "delete"}}).outcome.value,
            }
        else:
            callbacks = {"read": read, "delete": delete}
            if kind == "envelope":
                dispatcher = ToolDispatcher.bind_authenticated_deployment(
                    artifact,
                    authentication_keys={"test-key": Path(key_path).read_bytes()},
                    expected_audience="support:test",
                    minimum_sequence=minimum,
                    registered_tools=callbacks,
                )
                deployment = artifact.deployment
            else:
                dispatcher = ToolDispatcher.bind_deployment(artifact, registered_tools=callbacks)
                deployment = artifact
            result = {
                "fingerprint": PolicyRuntime.from_deployment(
                    deployment.policy_deployment
                ).policy_fingerprint,
            }
            for name in ("read", "delete"):
                try:
                    result[name] = dispatcher.execute(name, {}).decision.outcome.value
                except ToolCallDeniedError:
                    result[name] = "deny"
        print(json.dumps({"status": "ready", "calls": calls, **result}), flush=True)
    except SamsarixEthicsError as error:
        print(
            json.dumps({"status": "rejected", "error_type": type(error).__name__, "calls": calls}),
            flush=True,
        )
        raise SystemExit(2) from None


def main() -> None:
    operation, kind, destination, *options = sys.argv[1:]
    target = Path(destination)
    if operation == "restart":
        restart(kind, target, options[0], int(options[1]))
        return
    candidate, selected, replace = options
    artifact = READERS[kind](candidate)
    force = replace == "replace"
    install_checkpoint(selected, force)
    try:
        WRITERS[kind](target, artifact, force=force)
        print(json.dumps({"status": "published"}), flush=True)
    except SamsarixEthicsError as error:
        print(json.dumps({"status": "rejected", "error_type": type(error).__name__}), flush=True)
        raise SystemExit(2) from None
    finally:
        # A killed worker must not reach Python cleanup, even after publication.
        (target.parent / f"unwound-{os.getpid()}").write_text("unwound", encoding="ascii")


if __name__ == "__main__":
    main()
