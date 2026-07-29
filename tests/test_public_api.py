"""Published/imported package-shape tests."""

from __future__ import annotations

import samsarix_ethics


def test_public_api_is_importable() -> None:
    assert samsarix_ethics.__version__ == "0.1.0"
    assert samsarix_ethics.PolicyEngine.__module__ == "samsarix_ethics.engine"
    assert "PolicyValidationError" in samsarix_ethics.__all__
    assert "SamsarixEthicsError" in samsarix_ethics.__all__
