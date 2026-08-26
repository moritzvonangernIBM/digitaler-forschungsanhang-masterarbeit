"""Compatibility exports for domain-neutral runtime telemetry."""

from artifact.shared.telemetry import (
    EventLedger,
    TelemetryEvent,
)

__all__ = ["EventLedger", "TelemetryEvent"]
