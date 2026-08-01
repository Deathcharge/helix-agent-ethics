"""Published/imported package-shape tests."""

from __future__ import annotations

import samsarix_ethics


def test_public_api_is_importable() -> None:
    assert samsarix_ethics.__version__ == "0.1.0"
    assert samsarix_ethics.PolicyEngine.__module__ == "samsarix_ethics.engine"
    assert "PolicyValidationError" in samsarix_ethics.__all__
    assert "SamsarixEthicsError" in samsarix_ethics.__all__
    assert "validate_context" in samsarix_ethics.__all__
    assert "ToolGate" in samsarix_ethics.__all__
    assert "ToolCallBlockedError" in samsarix_ethics.__all__
    assert "get_tool_context_schema" in samsarix_ethics.__all__
    assert "get_tool_approval_schema" in samsarix_ethics.__all__
    assert "get_audit_record_schema" in samsarix_ethics.__all__
    assert "AuditRecord" in samsarix_ethics.__all__
    assert "ToolCallApproval" in samsarix_ethics.__all__
    assert "fingerprint_tool_call" in samsarix_ethics.__all__
    assert samsarix_ethics.MAX_BATCH_ITEMS == 1_000
    assert samsarix_ethics.MAX_TOOL_CAPABILITIES == 64
    assert samsarix_ethics.MAX_TOOL_CALL_FINGERPRINT_BYTES == 1_048_576
    assert samsarix_ethics.TOOL_CALL_APPROVAL_VERSION == 1
    assert samsarix_ethics.TOOL_CALL_FINGERPRINT_VERSION == 1
    assert samsarix_ethics.TOOL_CONTEXT_VERSION == 1
    assert samsarix_ethics.AUDIT_RECORD_VERSION == 1
