# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Authenticate, reload, and bind one complete coding-agent deployment."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from samsarix_ethics import (
    ToolDispatcher,
    authenticate_tool_gate_deployment,
    create_tool_gate_deployment,
    generate_deployment_auth_key,
    load_policy_deployment,
    load_tool_catalog,
    load_tool_gate_deployment_envelope,
    write_tool_gate_deployment_envelope,
)

ROOT = Path(__file__).parents[1]


def read_file(*, path: str) -> dict[str, str]:
    """Return demo metadata instead of reading an arbitrary caller-selected file."""

    return {"path": path, "status": "read would run here"}


def _unused_tool(**arguments: object) -> dict[str, object]:
    """Provide inert callbacks for tools not selected by this demonstration."""

    return dict(arguments)


def main() -> None:
    """Run the authenticated deployment journey with temporary key material."""

    deployment = create_tool_gate_deployment(
        load_policy_deployment(ROOT / "examples/deployment/coding-agent-baseline.deployment.json"),
        load_tool_catalog(ROOT / "examples/catalogs/coding-agent-tools.json"),
    )
    key = generate_deployment_auth_key()
    now = datetime.now(UTC).replace(microsecond=0)
    envelope = authenticate_tool_gate_deployment(
        deployment,
        key,
        key_id="demo-key",
        audience="coding-agent:demo",
        sequence=1,
        issued_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        expires_at=(now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )

    with TemporaryDirectory(prefix="samsarix-authenticated-deployment-") as directory:
        path = Path(directory) / "coding-agent.authenticated.json"
        write_tool_gate_deployment_envelope(path, envelope)
        reloaded = load_tool_gate_deployment_envelope(path)
        callbacks = {
            tool.name: (read_file if tool.name == "read_file" else _unused_tool)
            for tool in deployment.tool_catalog.tools
        }
        dispatcher = ToolDispatcher.bind_authenticated_deployment(
            reloaded,
            authentication_keys={"demo-key": key},
            expected_audience="coding-agent:demo",
            minimum_sequence=1,
            registered_tools=callbacks,
        )
        result = dispatcher.execute(
            "read_file",
            {"path": "README.md"},
            actor={"id": "coding-agent"},
            context={"workspace_contained": True},
        )
        if not result.decision.allowed or result.value["status"] != "read would run here":
            raise RuntimeError("authenticated demo did not execute the expected safe callback")
        print(
            f"Authenticated deployment {envelope.deployment_fingerprint}; "
            f"read_file -> {result.decision.outcome.value}"
        )


if __name__ == "__main__":
    main()
