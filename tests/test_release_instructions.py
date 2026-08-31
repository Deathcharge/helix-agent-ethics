"""Guard critical release-guide commands; clean-room execution is separate evidence."""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest

GUIDE = Path(__file__).resolve().parents[1] / "RELEASING.md"
PROFILES = (
    "core",
    "openai-agents",
    "langchain",
    "pydantic-ai",
    "mcp",
    "opentelemetry",
    "mcp-client",
)


def _commands(block: str) -> list[list[str]]:
    return [
        shlex.split(line.strip())
        for line in re.sub(r"\\\s*\n\s*", " ", block).splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _blocks() -> list[str]:
    return re.findall(r"```bash\n(.*?)\n\s*```", GUIDE.read_text(encoding="utf-8"), re.DOTALL)


@pytest.mark.parametrize("profile", PROFILES)
def test_each_source_contract_installs_package_before_execution(profile: str) -> None:
    candidates = [block for block in _blocks() if "requirements-dev.lock" in block]
    matches = [
        block
        for block in candidates
        if (
            "requirements-dev.lock" in block and block.count(".lock") == 1
            if profile == "core"
            else f"requirements-{profile}.lock" in block
        )
    ]
    assert len(matches) == 1, f"Missing or ambiguous release instructions for {profile}"
    commands = _commands(matches[0])
    dependencies = next(i for i, cmd in enumerate(commands) if "--require-hashes" in cmd)
    install = ["python", "-m", "pip", "install", "--no-build-isolation", "--no-deps", "."]
    assert install in commands, f"{profile} must install Samsarix, not only its test dependencies"
    installed = commands.index(install)
    checked = commands.index(["python", "-m", "pip", "check"])
    executed = [
        i
        for i, cmd in enumerate(commands)
        if cmd[:3] == ["python", "-m", "pytest"]
        or (cmd[0] == "python" and cmd[1].startswith("examples/"))
    ]
    assert executed and dependencies < installed < checked < min(executed)
    expected_locks = {"requirements-dev.lock"}
    if profile != "core":
        expected_locks.add(f"requirements-{profile}.lock")
    assert {part for part in commands[dependencies] if part.endswith(".lock")} == expected_locks


def test_all_seven_independent_contract_environments_are_documented() -> None:
    assert len([block for block in _blocks() if "requirements-dev.lock" in block]) == len(PROFILES)


def test_both_distribution_checks_pin_commit_ref_and_signer() -> None:
    commands = [cmd for block in _blocks() for cmd in _commands(block)]
    checks = [cmd for cmd in commands if cmd[:3] == ["gh", "attestation", "verify"]]
    assert len(checks) == 2
    assert {Path(cmd[3]).suffix for cmd in checks} == {".whl", ".gz"}
    for cmd in checks:
        for flag, value in (
            ("--repo", "Deathcharge/samsarix-agent-ethics"),
            ("--source-digest", "COMMIT"),
            ("--source-ref", "refs/heads/main"),
            ("--signer-workflow", "Deathcharge/samsarix-agent-ethics/.github/workflows/ci.yml"),
        ):
            assert flag in cmd, f"{cmd[3]} does not constrain {flag}"
            assert cmd[cmd.index(flag) + 1] == value
        assert cmd[3].startswith(".venv/release-artifacts/COMMIT/")


def test_download_cannot_mix_local_build_outputs_with_candidate_artifacts() -> None:
    commands = [cmd for block in _blocks() for cmd in _commands(block)]
    downloads = [cmd for cmd in commands if cmd[:3] == ["gh", "run", "download"]]
    assert len(downloads) == 1
    command = downloads[0]
    assert command[command.index("--name") + 1] == "python-distributions-COMMIT"
    assert command[command.index("--dir") + 1] == ".venv/release-artifacts/COMMIT"
