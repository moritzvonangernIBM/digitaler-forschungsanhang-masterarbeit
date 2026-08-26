"""Projection of visible dialogue/tool events into an oracle-free state."""

from __future__ import annotations

from typing import Any, Sequence

from artifact.shared.contracts import (
    GroundedField,
    VisibleProcessState,
)
from artifact.shared.visible_trace import (
    canonical_tool_action,
    decode_tool_result,
    message_content,
    message_role,
    tool_events,
)

WRITE_TOOLS = frozenset(
    {
        "cancel_pending_order",
        "modify_pending_order_address",
        "modify_pending_order_items",
        "modify_pending_order_payment",
        "modify_user_address",
        "return_delivered_order_items",
        "exchange_delivered_order_items",
    }
)


def project_visible_state(messages: Sequence[Any]) -> VisibleProcessState:
    """Project only information already present in the runtime trace."""

    state = VisibleProcessState(revision=len(messages))
    for index, message in enumerate(messages):
        role = message_role(message)
        content = message_content(message)
        if role not in {"user", "assistant"} or not content:
            continue
        event_id = str(getattr(message, "id", "") or f"message:{index}:{role}")
        if role == "user":
            state.visible_user_event_ids.append(event_id)
            state.user_utterances.append(GroundedField(content, (event_id,)))
        else:
            state.visible_assistant_event_ids.append(event_id)
            state.assistant_utterances.append(GroundedField(content, (event_id,)))

    for event in tool_events(messages):
        if event.failed:
            state.failed_tool_actions.add(
                canonical_tool_action(event.name, event.arguments)
            )
            continue
        event_id = f"tool:{event.call_id}:{event.name}"
        decoded = decode_tool_result(event.result)
        payload = decoded if isinstance(decoded, dict) else {}
        grounded = GroundedField(payload or decoded, (event_id,))
        if event.name in {"find_user_id_by_email", "find_user_id_by_name_zip"}:
            user_id = decoded.get("user_id") if isinstance(decoded, dict) else decoded
            if isinstance(user_id, str) and user_id:
                state.authenticated_user_id = GroundedField(user_id, (event_id,))
        elif event.name == "get_user_details" and payload:
            user_id = str(
                payload.get("user_id") or event.arguments.get("user_id") or ""
            )
            if user_id:
                state.users[user_id] = grounded
        elif event.name == "get_order_details" and payload:
            order_id = str(
                payload.get("order_id") or event.arguments.get("order_id") or ""
            )
            if order_id:
                state.orders[order_id] = grounded
        elif event.name == "get_product_details" and payload:
            product_id = str(
                payload.get("product_id")
                or event.arguments.get("product_id")
                or ""
            )
            if product_id:
                state.products[product_id] = grounded
        elif event.name in WRITE_TOOLS:
            state.completed_writes.append(
                GroundedField(
                    {
                        "tool_name": event.name,
                        "arguments": event.arguments,
                        "result": decoded,
                    },
                    (event_id,),
                )
            )
            if event.name == "modify_user_address" and payload:
                user_id = str(
                    payload.get("user_id")
                    or event.arguments.get("user_id")
                    or ""
                )
                if user_id:
                    state.users[user_id] = grounded
            elif payload:
                order_id = str(
                    payload.get("order_id")
                    or event.arguments.get("order_id")
                    or ""
                )
                if order_id:
                    state.orders[order_id] = grounded
    return state


def user_payload(state: VisibleProcessState) -> dict[str, Any]:
    user_id = (
        str(state.authenticated_user_id.value)
        if state.authenticated_user_id is not None
        else ""
    )
    field = state.users.get(user_id)
    return dict(field.value) if field and isinstance(field.value, dict) else {}


def order_payload(
    state: VisibleProcessState, order_id: str
) -> dict[str, Any] | None:
    field = state.orders.get(order_id)
    return dict(field.value) if field and isinstance(field.value, dict) else None


def product_payload(
    state: VisibleProcessState, product_id: str
) -> dict[str, Any] | None:
    field = state.products.get(product_id)
    return dict(field.value) if field and isinstance(field.value, dict) else None
