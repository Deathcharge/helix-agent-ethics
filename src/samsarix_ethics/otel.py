# Copyright 2024-2026 Samsarix LLC
# SPDX-License-Identifier: Apache-2.0

"""Optional privacy-minimized OpenTelemetry decision-event integration."""

from __future__ import annotations

from collections.abc import Callable
from importlib import import_module
from typing import Any, cast

from .audit import AuditRecord
from .errors import SamsarixEthicsError

OPENTELEMETRY_DECISION_EVENT_VERSION = 1
OPENTELEMETRY_DECISION_EVENT_NAME = "samsarix.policy.decision"


class OpenTelemetryIntegrationError(SamsarixEthicsError):
    """Raised when the OpenTelemetry API cannot receive decision events safely."""


class OpenTelemetryDecisionEventSink:
    """Attach metadata-only policy decisions to the current OpenTelemetry span."""

    def __init__(self) -> None:
        try:
            trace_module = import_module("opentelemetry.trace")
            get_current_span = trace_module.get_current_span
        except (AttributeError, ImportError) as exc:
            raise OpenTelemetryIntegrationError(
                "install the compatible OpenTelemetry API with "
                "'samsarix-agent-ethics[opentelemetry]'"
            ) from exc
        if not callable(get_current_span):
            raise OpenTelemetryIntegrationError(
                "OpenTelemetry trace.get_current_span must be callable"
            )
        self._get_current_span = cast(Callable[[], Any], get_current_span)

    def __call__(self, record: AuditRecord, /) -> None:
        if not isinstance(record, AuditRecord):
            raise TypeError("record must be an AuditRecord")
        span = self._get_current_span()
        is_recording = getattr(span, "is_recording", None)
        add_event = getattr(span, "add_event", None)
        if not callable(is_recording) or not callable(add_event):
            raise OpenTelemetryIntegrationError(
                "OpenTelemetry current span has an incompatible API shape"
            )
        recording = is_recording()
        if not isinstance(recording, bool):
            raise OpenTelemetryIntegrationError(
                "OpenTelemetry span is_recording must return a boolean"
            )
        if not recording:
            return
        add_event(
            OPENTELEMETRY_DECISION_EVENT_NAME,
            attributes={
                "samsarix.event.version": OPENTELEMETRY_DECISION_EVENT_VERSION,
                "samsarix.audit_record.version": record.audit_record_version,
                "samsarix.decision.id": record.decision_id,
                "samsarix.decision.evaluated_at": record.evaluated_at,
                "samsarix.decision.outcome": record.outcome,
                "samsarix.policy.id": record.policy_id,
                "samsarix.policy.version": record.policy_version,
                "samsarix.policy.fingerprint": record.policy_fingerprint,
                "samsarix.policy.matched_rules": record.matched_rules,
                "samsarix.policy.warning_count": record.warning_count,
            },
        )
