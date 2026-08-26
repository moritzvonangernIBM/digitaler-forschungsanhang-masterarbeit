"""Deterministic, LLM-free control for the seven Retail write tools."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from typing import Any

from artifact.retail.state_projection import (
    WRITE_TOOLS,
    order_payload,
    product_payload,
    user_payload,
)
from artifact.shared.contracts import (
    ConfirmationTicket,
    ConfirmationToken,
    PreWriteDecision,
    PreWriteDisposition,
    ToolAction,
    VisibleProcessState,
)
from artifact.shared.visible_trace import (
    canonical_tool_action,
)

ORDER_WRITES = WRITE_TOOLS - {"modify_user_address"}
ADDRESS_FIELDS = ("address1", "address2", "city", "state", "country", "zip")
ITEM_WRITES = {
    "modify_pending_order_items",
    "return_delivered_order_items",
    "exchange_delivered_order_items",
}
VARIANT_WRITES = {
    "modify_pending_order_items",
    "exchange_delivered_order_items",
}
PAYMENT_WRITES = {
    "modify_pending_order_items",
    "modify_pending_order_payment",
    "return_delivered_order_items",
    "exchange_delivered_order_items",
}
AFFIRMATIVE = re.compile(
    r"\b(?:yes|yes please|i confirm|confirmed|go ahead|please proceed|do it|okay|ok)\b",
    re.IGNORECASE,
)
NEGATIVE = re.compile(
    r"^\s*(?:no\b|not yet\b|do not\b|don't\b)",
    re.IGNORECASE,
)


def canonical_action(action: ToolAction) -> str:
    return json.dumps(
        {"tool_name": action.tool_name, "arguments": action.arguments},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def action_digest(action: ToolAction) -> str:
    return hashlib.sha256(canonical_action(action).encode("utf-8")).hexdigest()


def issue_confirmation(
    state: VisibleProcessState, action: ToolAction
) -> ConfirmationTicket:
    rendered = canonical_action(action)
    return ConfirmationTicket(
        action_digest=action_digest(action),
        source_state_revision=state.revision,
        canonical_action=rendered,
        message=f"Please confirm this exact action: {rendered}. Shall I proceed?",
    )


def bind_confirmation(
    ticket: ConfirmationTicket,
    *,
    user_text: str,
    user_event_id: str,
    current_state_revision: int,
) -> ConfirmationToken | None:
    """Bind only a later, explicit affirmative event to one exact ticket."""

    if (
        not user_event_id
        or NEGATIVE.search(user_text)
        or not AFFIRMATIVE.search(user_text)
        or current_state_revision <= ticket.source_state_revision
    ):
        return None
    return ConfirmationToken(
        action_digest=ticket.action_digest,
        source_state_revision=ticket.source_state_revision,
        confirmed_state_revision=current_state_revision,
        user_event_id=user_event_id,
    )


def is_explicit_confirmation_response(user_text: str) -> bool:
    """Identify only explicit affirmation/negation as a B-bound answer."""

    return bool(AFFIRMATIVE.search(user_text) or NEGATIVE.search(user_text))


def confirmation_matches(
    token: ConfirmationToken | None,
    state: VisibleProcessState,
    action: ToolAction,
) -> bool:
    return bool(
        token is not None
        and token.action_digest == action_digest(action)
        and token.confirmed_state_revision == state.revision
        and token.source_state_revision < token.confirmed_state_revision
    )


def _decision(
    disposition: PreWriteDisposition,
    code: str,
    candidate: ToolAction,
    *,
    evidence: ToolAction | None = None,
    ticket: ConfirmationTicket | None = None,
) -> PreWriteDecision:
    return PreWriteDecision(
        disposition=disposition,
        reason_code=code,
        candidate=candidate,
        evidence_action=evidence,
        confirmation_ticket=ticket,
    )


def _read(
    tool_name: str,
    arguments: dict[str, Any],
    sources: tuple[str, ...],
) -> ToolAction:
    return ToolAction(tool_name, arguments, sources)


def _request_evidence(
    state: VisibleProcessState,
    candidate: ToolAction,
    reason_code: str,
    action: ToolAction,
) -> PreWriteDecision:
    if (
        canonical_tool_action(action.tool_name, action.arguments)
        in state.failed_tool_actions
    ):
        return _decision(
            PreWriteDisposition.REJECT,
            "B_FAILED_EVIDENCE_READ_SUPPRESSED",
            candidate,
        )
    return _decision(
        PreWriteDisposition.REQUEST_EVIDENCE,
        reason_code,
        candidate,
        evidence=action,
    )


def _source_ids(
    state: VisibleProcessState, *entity_ids: str
) -> tuple[str, ...]:
    values: list[str] = []
    if state.authenticated_user_id is not None:
        values.extend(state.authenticated_user_id.source_event_ids)
    for entity_id in entity_ids:
        field = (
            state.orders.get(entity_id)
            or state.products.get(entity_id)
            or state.users.get(entity_id)
        )
        if field is not None:
            values.extend(field.source_event_ids)
    return tuple(dict.fromkeys(values))


def _items(order: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item for item in order.get("items") or [] if isinstance(item, dict)
    ]


def _item_counts(order: dict[str, Any]) -> Counter[str]:
    return Counter(str(item.get("item_id")) for item in _items(order))


def _payments(order: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in order.get("payment_history") or []
        if isinstance(item, dict)
    ]


def _payment_methods(
    state: VisibleProcessState,
) -> dict[str, dict[str, Any]]:
    methods = user_payload(state).get("payment_methods") or {}
    if not isinstance(methods, dict):
        return {}
    return {
        str(key): value if isinstance(value, dict) else {}
        for key, value in methods.items()
    }


def _is_gift_card(method_id: str, record: dict[str, Any]) -> bool:
    return "gift_card" in str(record.get("source") or method_id).casefold()


def _variant(
    product: dict[str, Any], item_id: str
) -> dict[str, Any] | None:
    variants = product.get("variants") or {}
    if isinstance(variants, dict):
        value = variants.get(item_id)
        return value if isinstance(value, dict) else None
    if isinstance(variants, list):
        for value in variants:
            if (
                isinstance(value, dict)
                and str(value.get("item_id")) == item_id
            ):
                return value
    return None


def _finish(
    state: VisibleProcessState,
    candidate: ToolAction,
    confirmation: ConfirmationToken | None,
) -> PreWriteDecision:
    if confirmation_matches(confirmation, state, candidate):
        return _decision(
            PreWriteDisposition.ALLOW_UNCHANGED,
            "B_READY_UNCHANGED",
            candidate,
        )
    return _decision(
        PreWriteDisposition.REQUEST_CONFIRMATION,
        "B_CONFIRM_EXACT_WRITE",
        candidate,
        ticket=issue_confirmation(state, candidate),
    )


class PassThroughPreWriteControl:
    """Explicit no-op module used when factor B is disabled."""

    enabled = False

    @staticmethod
    def evaluate(
        state: VisibleProcessState,
        candidate: ToolAction,
        *,
        confirmation: ConfirmationToken | None = None,
    ) -> PreWriteDecision:
        del state, confirmation
        return _decision(
            PreWriteDisposition.ALLOW_UNCHANGED,
            "B_DISABLED_PASS_THROUGH",
            candidate,
        )


class DeterministicPreWriteControl:
    """Narrow policy/state predicate guard; it never calls a model."""

    enabled = True

    @staticmethod
    def evaluate(
        state: VisibleProcessState,
        candidate: ToolAction,
        *,
        confirmation: ConfirmationToken | None = None,
    ) -> PreWriteDecision:
        name, args = candidate.tool_name, candidate.arguments
        if name not in WRITE_TOOLS:
            return _decision(
                PreWriteDisposition.ALLOW_UNCHANGED,
                "B_NOT_IN_SCOPE",
                candidate,
            )
        if state.authenticated_user_id is None:
            return _decision(
                PreWriteDisposition.REJECT,
                "B_NOT_AUTHENTICATED",
                candidate,
            )
        user_id = str(state.authenticated_user_id.value)

        if name == "modify_user_address":
            if str(args.get("user_id") or "") != user_id:
                return _decision(
                    PreWriteDisposition.REJECT,
                    "B_FOREIGN_USER",
                    candidate,
                )
            if any(
                key not in args
                or (key != "address2" and not str(args[key]).strip())
                for key in ADDRESS_FIELDS
            ):
                return _decision(
                    PreWriteDisposition.REJECT,
                    "B_INCOMPLETE_ADDRESS",
                    candidate,
                )
            return _finish(state, candidate, confirmation)

        order_id = str(args.get("order_id") or "")
        if not order_id:
            return _decision(
                PreWriteDisposition.REJECT,
                "B_MISSING_ORDER_ID",
                candidate,
            )
        order = order_payload(state, order_id)
        if order is None:
            sources = state.authenticated_user_id.source_event_ids
            return _request_evidence(
                state,
                candidate,
                "B_ORDER_NOT_OBSERVED",
                _read(
                    "get_order_details",
                    {"order_id": order_id},
                    sources,
                ),
            )
        sources = _source_ids(state, order_id)
        if str(order.get("user_id") or "") != user_id:
            return _decision(
                PreWriteDisposition.REJECT,
                "B_FOREIGN_ORDER",
                candidate,
            )

        required_status = (
            "delivered"
            if name
            in {
                "return_delivered_order_items",
                "exchange_delivered_order_items",
            }
            else "pending"
        )
        if str(order.get("status") or "") != required_status:
            return _decision(
                PreWriteDisposition.REJECT,
                "B_INELIGIBLE_STATUS",
                candidate,
            )

        prior = [
            field.value
            for field in state.completed_writes
            if isinstance(field.value, dict)
        ]
        if any(
            value.get("tool_name") == name
            and value.get("arguments") == args
            for value in prior
        ):
            return _decision(
                PreWriteDisposition.REJECT,
                "B_DUPLICATE_WRITE",
                candidate,
            )

        if name == "cancel_pending_order":
            if args.get("reason") not in {
                "no longer needed",
                "ordered by mistake",
            }:
                return _decision(
                    PreWriteDisposition.REJECT,
                    "B_INVALID_CANCEL_REASON",
                    candidate,
                )
        elif name == "modify_pending_order_address":
            if any(
                key not in args
                or (key != "address2" and not str(args[key]).strip())
                for key in ADDRESS_FIELDS
            ):
                return _decision(
                    PreWriteDisposition.REJECT,
                    "B_INCOMPLETE_ADDRESS",
                    candidate,
                )

        if name in ITEM_WRITES:
            old_ids = [str(value) for value in args.get("item_ids") or []]
            if not old_ids:
                return _decision(
                    PreWriteDisposition.REJECT,
                    "B_EMPTY_ITEM_SET",
                    candidate,
                )
            if Counter(old_ids) - _item_counts(order):
                return _decision(
                    PreWriteDisposition.REJECT,
                    "B_ITEM_NOT_IN_ORDER",
                    candidate,
                )

        price_difference = 0.0
        if name in VARIANT_WRITES:
            old_ids = [str(value) for value in args.get("item_ids") or []]
            new_ids = [
                str(value) for value in args.get("new_item_ids") or []
            ]
            if len(old_ids) != len(new_ids):
                return _decision(
                    PreWriteDisposition.REJECT,
                    "B_ITEM_LIST_LENGTH",
                    candidate,
                )
            if any(old == new for old, new in zip(old_ids, new_ids)):
                return _decision(
                    PreWriteDisposition.REJECT,
                    "B_VARIANT_UNCHANGED",
                    candidate,
                )
            remaining = list(_items(order))
            pairs: list[tuple[dict[str, Any], str]] = []
            for old_id, new_id in zip(old_ids, new_ids):
                index = next(
                    (
                        index
                        for index, item in enumerate(remaining)
                        if str(item.get("item_id")) == old_id
                    ),
                    None,
                )
                if index is None:
                    return _decision(
                        PreWriteDisposition.REJECT,
                        "B_ITEM_NOT_IN_ORDER",
                        candidate,
                    )
                pairs.append((remaining.pop(index), new_id))
            for old_item, new_id in pairs:
                product_id = str(old_item.get("product_id") or "")
                product = product_payload(state, product_id)
                if product is None:
                    return _request_evidence(
                        state,
                        candidate,
                        "B_PRODUCT_NOT_OBSERVED",
                        _read(
                            "get_product_details",
                            {"product_id": product_id},
                            sources,
                        ),
                    )
                variant = _variant(product, new_id)
                if variant is None:
                    return _decision(
                        PreWriteDisposition.REJECT,
                        "B_WRONG_PRODUCT_FAMILY",
                        candidate,
                    )
                if not bool(variant.get("available")):
                    return _decision(
                        PreWriteDisposition.REJECT,
                        "B_VARIANT_UNAVAILABLE",
                        candidate,
                    )
                price_difference += float(variant.get("price") or 0) - float(
                    old_item.get("price") or 0
                )

        if name in PAYMENT_WRITES:
            payment_id = str(args.get("payment_method_id") or "")
            payments = _payments(order)
            original = next(
                (
                    payment
                    for payment in payments
                    if payment.get("transaction_type") == "payment"
                ),
                None,
            )
            if (
                name == "return_delivered_order_items"
                and original
                and payment_id == str(original.get("payment_method_id"))
            ):
                method = {"source": payment_id}
            else:
                methods = _payment_methods(state)
                if not methods:
                    return _request_evidence(
                        state,
                        candidate,
                        "B_PAYMENT_PROFILE_NOT_OBSERVED",
                        _read(
                            "get_user_details",
                            {"user_id": user_id},
                            sources,
                        ),
                    )
                method = methods.get(payment_id)
                if method is None:
                    return _decision(
                        PreWriteDisposition.REJECT,
                        "B_PAYMENT_NOT_OWNED",
                        candidate,
                    )
            if (
                name == "return_delivered_order_items"
                and original
                and payment_id != str(original.get("payment_method_id"))
                and not _is_gift_card(payment_id, method)
            ):
                return _decision(
                    PreWriteDisposition.REJECT,
                    "B_INVALID_REFUND_METHOD",
                    candidate,
                )
            if (
                name == "return_delivered_order_items"
                and original is None
                and not _is_gift_card(payment_id, method)
            ):
                return _decision(
                    PreWriteDisposition.REJECT,
                    "B_INVALID_REFUND_METHOD",
                    candidate,
                )
            if name == "modify_pending_order_payment":
                if (
                    len(payments) != 1
                    or payments[0].get("transaction_type") != "payment"
                ):
                    return _decision(
                        PreWriteDisposition.REJECT,
                        "B_PAYMENT_HISTORY",
                        candidate,
                    )
                if payment_id == str(payments[0].get("payment_method_id")):
                    return _decision(
                        PreWriteDisposition.REJECT,
                        "B_PAYMENT_UNCHANGED",
                        candidate,
                    )
                price_difference = float(payments[0].get("amount") or 0)
            if (
                _is_gift_card(payment_id, method)
                and float(method.get("balance") or 0)
                < max(price_difference, 0)
            ):
                return _decision(
                    PreWriteDisposition.REJECT,
                    "B_INSUFFICIENT_BALANCE",
                    candidate,
                )

        return _finish(state, candidate, confirmation)
