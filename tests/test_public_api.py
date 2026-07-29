"""Published/imported package-shape tests."""

from __future__ import annotations

import helix_ethics


def test_public_api_is_importable() -> None:
    assert helix_ethics.__version__ == "0.1.0"
    assert helix_ethics.PolicyEngine.__module__ == "helix_ethics.engine"
    assert "PolicyValidationError" in helix_ethics.__all__
