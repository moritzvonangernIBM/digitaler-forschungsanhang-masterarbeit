"""Deterministic factor B: candidate feasibility without dialogue control."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from artifact.retail.prewrite_control import (
    DeterministicPreWriteControl,
)
from artifact.retail.state_projection import (
    WRITE_TOOLS,
)
from artifact.shared.contracts import (
    PreWriteDisposition,
    ToolAction,
    VisibleProcessState,
)

from .contracts import (
    FeasibilityBundle,
    FeasibilityDisposition,
    FeasibilityEvaluation,
)

REPAIR_INSTRUCTIONS = {
    "B_NOT_AUTHENTICATED": "Authenticate the user before proposing a write.",
    "B_FOREIGN_USER": "Do not mutate a user record that is not authenticated.",
    "B_INCOMPLETE_ADDRESS": "Obtain every required address field before retrying.",
    "B_MISSING_ORDER_ID": "Obtain a concrete order identifier before retrying.",
    "B_ORDER_NOT_OBSERVED": "Read the specified order before reconsidering the write.",
    "B_FOREIGN_ORDER": "Do not mutate an order owned by another user.",
    "B_INELIGIBLE_STATUS": "Do not repeat the write for the observed order status.",
    "B_DUPLICATE_WRITE": "Do not repeat an already completed identical write.",
    "B_INVALID_CANCEL_REASON": "Use only a cancellation reason enumerated by the Retail tool contract.",
    "B_EMPTY_ITEM_SET": "Obtain at least one concrete item identifier.",
    "B_ITEM_NOT_IN_ORDER": "Re-read the order and select only items that belong to it.",
    "B_ITEM_LIST_LENGTH": "Provide one replacement item for every original item.",
    "B_VARIANT_UNCHANGED": "Choose a different valid variant or do not mutate.",
    "B_PRODUCT_NOT_OBSERVED": "Read the relevant product before reconsidering the write.",
    "B_WRONG_PRODUCT_FAMILY": "Choose only a variant from the original product family.",
    "B_VARIANT_UNAVAILABLE": "Choose an available variant or ask the user for another option.",
    "B_PAYMENT_PROFILE_NOT_OBSERVED": "Read the authenticated user profile before reconsidering the payment method.",
    "B_PAYMENT_NOT_OWNED": "Use only a payment method owned by the authenticated user.",
    "B_INVALID_REFUND_METHOD": "Use the original payment method or an owned gift card as allowed by policy.",
    "B_PAYMENT_HISTORY": "Do not modify payment when the observed payment history is ineligible.",
    "B_PAYMENT_UNCHANGED": "Choose a payment method different from the original one.",
    "B_INSUFFICIENT_BALANCE": "Choose a payment method with sufficient available balance.",
    "B_FAILED_EVIDENCE_READ_SUPPRESSED": "Do not repeat the failed evidence read; choose another safe response or transfer.",
}


def _action(call: Any) -> ToolAction:
    return ToolAction(
        tool_name=str(getattr(call, "name", "") or ""),
        arguments=dict(getattr(call, "arguments", None) or {}),
    )


def evaluate_write(
    state: VisibleProcessState,
    call: Any,
    *,
    enabled: bool,
) -> FeasibilityEvaluation:
    """Evaluate objective predicates against the exact visible state.

    REQUEST_CONFIRMATION means all deterministic feasibility predicates
    passed. Confirmation itself deliberately remains native dialogue policy.
    """

    action = _action(call)
    identifier = str(getattr(call, "id", "") or "")
    if not enabled:
        return FeasibilityEvaluation(
            identifier,
            action,
            FeasibilityDisposition.VALID_UNCHANGED,
            "B_DISABLED_PASS_THROUGH",
        )
    decision = DeterministicPreWriteControl.evaluate(state, action)
    if decision.disposition in {
        PreWriteDisposition.ALLOW_UNCHANGED,
        PreWriteDisposition.REQUEST_CONFIRMATION,
    }:
        return FeasibilityEvaluation(
            identifier,
            action,
            FeasibilityDisposition.VALID_UNCHANGED,
            "B_FEASIBILITY_VALID_CONFIRMATION_NATIVE_SCOPE",
        )
    if decision.disposition == PreWriteDisposition.REQUEST_EVIDENCE:
        return FeasibilityEvaluation(
            identifier,
            action,
            FeasibilityDisposition.EVIDENCE_REQUIRED,
            decision.reason_code,
            evidence_action=decision.evidence_action,
        )
    return FeasibilityEvaluation(
        identifier,
        action,
        FeasibilityDisposition.INVALID,
        decision.reason_code,
    )


def evaluate_bundle(
    state: VisibleProcessState,
    calls: Iterable[Any],
    *,
    enabled: bool,
    bundle_id: str,
) -> FeasibilityBundle:
    sequence = tuple(calls)
    return FeasibilityBundle(
        bundle_id=bundle_id,
        tool_call_count=len(sequence),
        write_evaluations=tuple(
            evaluate_write(state, call, enabled=enabled)
            for call in sequence
            if str(getattr(call, "name", "") or "") in WRITE_TOOLS
        ),
    )


def explain_evaluation(
    state: VisibleProcessState,
    row: FeasibilityEvaluation,
) -> dict[str, Any]:
    """Return compact, visible-state evidence for one B decision."""

    args = row.action.arguments
    order_id = str(args.get("order_id") or "")
    order_field = state.orders.get(order_id)
    order = (
        order_field.value
        if order_field is not None and isinstance(order_field.value, dict)
        else None
    )
    authenticated = state.authenticated_user_id
    user_id = str(authenticated.value) if authenticated is not None else ""
    user_field = state.users.get(user_id)
    user = (
        user_field.value
        if user_field is not None and isinstance(user_field.value, dict)
        else None
    )
    candidate_old_ids = {
        str(value) for value in args.get("item_ids") or []
    }
    candidate_new_ids = {
        str(value) for value in args.get("new_item_ids") or []
    }
    candidate_payment_id = str(args.get("payment_method_id") or "")
    products = []
    if order is not None:
        relevant_items = [
            item
            for item in order.get("items") or []
            if isinstance(item, dict)
            and (
                not candidate_old_ids
                or str(item.get("item_id") or "") in candidate_old_ids
            )
        ]
        product_ids = {
            str(item.get("product_id") or "") for item in relevant_items
        }
        for product_id in sorted(product_ids):
            field = state.products.get(product_id)
            payload = (
                field.value
                if field is not None and isinstance(field.value, dict)
                else None
            )
            products.append(
                {
                    "product_id": product_id,
                    "observed": payload is not None,
                    "candidate_variants": (
                        [
                            {
                                "item_id": item_id,
                                "available": variant.get("available"),
                                "price": variant.get("price"),
                            }
                            for item_id in sorted(candidate_new_ids)
                            for variant in [
                                (payload.get("variants") or {}).get(item_id)
                            ]
                            if isinstance(variant, dict)
                        ]
                        if payload is not None
                        and isinstance(payload.get("variants"), dict)
                        else []
                    ),
                    "source_event_ids": (
                        list(field.source_event_ids) if field else []
                    ),
                }
            )
    return {
        "call_id": row.call_id,
        "tool_name": row.action.tool_name,
        "candidate_arguments": dict(args),
        "reason_code": row.reason_code,
        "disposition": row.disposition.value,
        "required_response": (
            "Execute the unchanged native candidate; confirmation remains "
            "within native dialogue policy."
            if row.disposition == FeasibilityDisposition.VALID_UNCHANGED
            else REPAIR_INSTRUCTIONS.get(
                row.reason_code,
                "Reconsider the candidate using only visible evidence and Retail policy.",
            )
        ),
        "observed": {
            "authenticated_user_id": user_id or None,
            "authentication_source_event_ids": (
                list(authenticated.source_event_ids) if authenticated else []
            ),
            "order": (
                {
                    "order_id": order_id,
                    "user_id": order.get("user_id"),
                    "status": order.get("status"),
                    "items": [
                        {
                            "item_id": item.get("item_id"),
                            "product_id": item.get("product_id"),
                            "price": item.get("price"),
                        }
                        for item in order.get("items") or []
                        if isinstance(item, dict)
                    ],
                    "payment_history": order.get("payment_history") or [],
                    "source_event_ids": list(order_field.source_event_ids),
                }
                if order is not None and order_field is not None
                else None
            ),
            "user_profile": (
                {
                    "user_id": user_id,
                    "candidate_payment_method": (
                        {
                            "payment_method_id": candidate_payment_id,
                            **dict(
                                (user.get("payment_methods") or {}).get(
                                    candidate_payment_id
                                )
                                or {}
                            ),
                        }
                        if candidate_payment_id
                        and isinstance(user.get("payment_methods"), dict)
                        and candidate_payment_id
                        in (user.get("payment_methods") or {})
                        else None
                    ),
                    "source_event_ids": list(user_field.source_event_ids),
                }
                if user is not None and user_field is not None
                else None
            ),
            "products": products,
        },
        "evidence_action": (
            {
                "tool_name": row.evidence_action.tool_name,
                "arguments": row.evidence_action.arguments,
            }
            if row.evidence_action
            else None
        ),
    }
