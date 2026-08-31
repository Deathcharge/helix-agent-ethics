"""Atomic writer cleanup must also survive normal BaseException unwinding."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import samsarix_ethics.io as io_module
from samsarix_ethics import PolicyValidationError, load_policy
from samsarix_ethics.io import write_sample_policy


@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize("stage", ["fsync", "publish"])
@pytest.mark.parametrize("exception", [KeyboardInterrupt, SystemExit, RuntimeError])
def test_python_unwinding_cleans_staged_file_without_changing_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    force: bool,
    stage: str,
    exception: type[BaseException],
) -> None:
    target = tmp_path / "active.json"
    if force:
        target.write_bytes(b"prior operator-owned content")
    failure = exception("injected interruption")

    def interrupt(*_args: Any) -> None:
        raise failure

    operation = "fsync" if stage == "fsync" else ("replace" if force else "link")
    monkeypatch.setattr(io_module.os, operation, interrupt)
    with pytest.raises(exception) as error:
        write_sample_policy(target, force=force)
    assert error.value is failure
    assert list(tmp_path.glob(".active.json.*")) == []
    if force:
        assert target.read_bytes() == b"prior operator-owned content"
    else:
        assert not target.exists()


def test_cleanup_failure_does_not_replace_original_interruption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "active.json"
    failure = KeyboardInterrupt("injected interruption")

    def interrupt(*_args: Any) -> None:
        raise failure

    def cannot_remove(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("injected filesystem outage")

    monkeypatch.setattr(io_module.os, "fsync", interrupt)
    monkeypatch.setattr(Path, "unlink", cannot_remove)
    with pytest.raises(KeyboardInterrupt) as error:
        write_sample_policy(target)
    assert error.value is failure
    assert not target.exists()
    assert len(list(tmp_path.glob(".active.json.*"))) == 1


def test_cleanup_error_after_exclusive_publish_does_not_roll_back_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "active.json"

    def cannot_remove(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("injected filesystem outage")

    monkeypatch.setattr(Path, "unlink", cannot_remove)
    with pytest.raises(PolicyValidationError, match="cannot write"):
        write_sample_policy(target)
    assert load_policy(target).id == "safe-agent-actions"
    assert len(list(tmp_path.glob(".active.json.*"))) == 1
