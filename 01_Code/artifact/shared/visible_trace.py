"""Domain-neutral parsing of visible dialogue and tool events."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Sequence


@dataclass(frozen=True, slots=True)
class ToolEvent:
    call_id: str
    name: str
    arguments: dict[str, Any]
    result: str
    failed: bool


def canonical_tool_action(
    name: str,
    arguments: dict[str, Any] | None,
) -> tuple[str, str]:
    return (
        str(name),
        json.dumps(
            dict(arguments or {}),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ),
    )


def message_role(message: Any) -> str:
    role = getattr(message, "role", None)
    return str(getattr(role, "value", role))


def message_content(message: Any) -> str:
    return str(getattr(message, "content", None) or "")


def tool_events(messages: Sequence[Any]) -> tuple[ToolEvent, ...]:
    calls: dict[str, Any] = {}
    events: list[ToolEvent] = []
    for message in messages:
        role = message_role(message)
        for call in getattr(message, "tool_calls", None) or []:
            call_id = str(getattr(call, "id", "") or "")
            requestor = str(getattr(call, "requestor", "") or role)
            if call_id and requestor == "assistant":
                calls[call_id] = call
        if role != "tool":
            continue
        call_id = str(getattr(message, "id", "") or "")
        call = calls.get(call_id)
        if call is None:
            continue
        events.append(
            ToolEvent(
                call_id=call_id,
                name=str(getattr(call, "name", "")),
                arguments=dict(getattr(call, "arguments", None) or {}),
                result=message_content(message),
                failed=bool(getattr(message, "error", False)),
            )
        )
    return tuple(events)


def decode_tool_result(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return str(value).strip().strip('"')
