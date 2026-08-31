# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Show which emergency policy a fresh process enforces after local publication."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import samsarix_ethics
from samsarix_ethics import (
    Policy,
    PolicyRuntime,
    create_policy_deployment,
    load_policy,
    write_policy_deployment,
)

ROOT = Path(__file__).parent
READ = {"action": {"operation": "read", "risk": "low"}}


def restarted_decision(path: Path, expected_code: int) -> dict[str, object] | None:
    """Invoke the installed package in a new process, with bounded completion."""
    # Use the base interpreter on Windows to avoid killing only a venv redirector
    # if a child times out. -S plus this exact package root needs no optional deps.
    executable = Path(sys.base_prefix) / "python.exe" if os.name == "nt" else Path(sys.executable)
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(Path(samsarix_ethics.__file__).parents[1])
    result = subprocess.run(  # noqa: S603 - fixed interpreter/module; only owned temp path varies
        [
            str(executable),
            "-S",
            "-m",
            "samsarix_ethics",
            "check",
            "--deployment",
            str(path),
            "--input",
            "-",
        ],
        input=json.dumps(READ),
        capture_output=True,
        text=True,
        env=environment,
        timeout=20,
        check=False,
    )
    if result.returncode != expected_code:
        raise RuntimeError("Fresh-process policy check returned an unexpected exit code")
    if expected_code == 2:
        if result.stdout or not result.stderr:
            raise RuntimeError("Invalid deployment must produce an error, not a decision")
        return None
    return json.loads(result.stdout)


def main() -> None:
    baseline = load_policy(ROOT / "policies/safe-agent-actions.json")
    emergency = Policy.from_dict(
        {
            "schema_version": 1,
            "id": "emergency-lockdown",
            "version": "1",
            "default_effect": "deny",
            "rules": [],
        }
    )
    initial = create_policy_deployment(baseline)
    lockdown = create_policy_deployment(emergency)
    with TemporaryDirectory(prefix="samsarix-policy-restart-") as directory:
        active = Path(directory) / "active.deployment.json"
        write_policy_deployment(active, initial)
        runtime = PolicyRuntime.from_deployment(initial)
        runtime.activate_deployment(lockdown, expected_generation=1)
        if runtime.evaluate(READ).outcome.value != "deny":
            raise RuntimeError("Emergency in-process policy did not deny")
        before = restarted_decision(active, 0)
        if before is None or before["outcome"] != "allow":
            raise RuntimeError("The fresh process should still see the persisted baseline")
        print("memory-only lockdown: current process denies; fresh process still allows")

        # A deployment controller should validate/publish desired state before serving it.
        # This example has one writer and no concurrent ingress; it is not a rollout service.
        write_policy_deployment(active, lockdown, force=True)
        after = restarted_decision(active, 3)
        if after is None or after["outcome"] != "deny":
            raise RuntimeError("Fresh process did not enforce the published lockdown")
        print("published lockdown: fresh process denies")

        active.write_bytes(b'{"incomplete":')  # Deliberately corrupt only this owned temp fixture.
        restarted_decision(active, 2)
        print("corrupt active deployment: fresh process rejects startup input")
    print("No service, real tool side effect, persistent key, or production file was changed.")


if __name__ == "__main__":
    main()
