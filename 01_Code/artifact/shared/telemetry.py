"""Immutable, treatment-neutral mechanism ledger across domains."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze(item) for key, item in value.items()}
        )
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set | frozenset):
        return frozenset(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple | frozenset):
        return [_thaw(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class TelemetryEvent:
    sequence: int
    component: str
    event_type: str
    reason_code: str
    opportunity_id: str | None
    state_revision: int | None
    payload: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "component": self.component,
            "event_type": self.event_type,
            "reason_code": self.reason_code,
            "opportunity_id": self.opportunity_id,
            "state_revision": self.state_revision,
            **_thaw(self.payload),
        }


@dataclass(slots=True)
class EventLedger:
    _events: list[TelemetryEvent] = field(default_factory=list)

    @property
    def events(self) -> tuple[TelemetryEvent, ...]:
        return tuple(self._events)

    def record(
        self,
        component: str,
        event_type: str,
        reason_code: str,
        *,
        opportunity_id: str | None = None,
        state_revision: int | None = None,
        **payload: Any,
    ) -> TelemetryEvent:
        event = TelemetryEvent(
            sequence=len(self._events),
            component=component,
            event_type=event_type,
            reason_code=reason_code,
            opportunity_id=opportunity_id,
            state_revision=state_revision,
            payload=_freeze(payload),
        )
        self._events.append(event)
        return event

    def serialise(self) -> list[dict[str, Any]]:
        return [event.as_dict() for event in self._events]

    def audit(self, *, allow_open_b: bool = False) -> dict[str, Any]:
        """Reconcile opportunity, decision, action and final disposition chains."""

        issues: list[str] = []
        serialised = self.serialise()
        for component in ("A", "B"):
            opportunities = {
                str(event["opportunity_id"])
                for event in serialised
                if event["component"] == component
                and event["event_type"] == "OPPORTUNITY"
                and event.get("opportunity_id")
            }
            decisions = {
                str(event["opportunity_id"])
                for event in serialised
                if event["component"] == component
                and event["event_type"] == "DECISION"
                and event.get("opportunity_id")
            }
            unknown = decisions - opportunities
            missing = opportunities - decisions
            if unknown:
                issues.append(
                    f"{component}: decisions without opportunities {sorted(unknown)}"
                )
            if missing:
                issues.append(
                    f"{component}: opportunities without decisions {sorted(missing)}"
                )
        b_opportunities = {
            str(event["opportunity_id"])
            for event in serialised
            if event["component"] == "B"
            and event["event_type"] == "OPPORTUNITY"
            and event.get("opportunity_id")
        }
        b_closed = {
            str(event["opportunity_id"])
            for event in serialised
            if event["component"] == "B"
            and event["event_type"] == "FINAL_DISPOSITION"
            and event.get("opportunity_id")
        }
        if not allow_open_b and b_opportunities - b_closed:
            issues.append(
                "B: opportunities without final disposition "
                f"{sorted(b_opportunities - b_closed)}"
            )
        if b_closed - b_opportunities:
            issues.append(
                "B: final dispositions without opportunities "
                f"{sorted(b_closed - b_opportunities)}"
            )

        sequences = [event["sequence"] for event in serialised]
        if sequences != list(range(len(sequences))):
            issues.append("ledger sequence is not contiguous")
        return {
            "pass": not issues,
            "issues": issues,
            "event_count": len(serialised),
            "a_opportunities": sum(
                event["component"] == "A"
                and event["event_type"] == "OPPORTUNITY"
                for event in serialised
            ),
            "b_opportunities": len(b_opportunities),
            "b_final_dispositions": len(b_closed),
        }
