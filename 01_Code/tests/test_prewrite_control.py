from __future__ import annotations

import inspect
import ast
from copy import deepcopy
from pathlib import Path

from artifact.retail.contracts import (
    GroundedField,
    PreWriteDisposition,
    ToolAction,
    VisibleProcessState,
)
from artifact.retail.prewrite_control import (
    DeterministicPreWriteControl,
    PassThroughPreWriteControl,
    action_digest,
    bind_confirmation,
)
from artifact.retail.state_projection import (
    canonical_tool_action,
)


def grounded(value, source):
    return GroundedField(value, (source,))


def state() -> VisibleProcessState:
    user = {
        "user_id": "u1",
        "payment_methods": {
            "card1": {"source": "credit_card"},
            "card2": {"source": "credit_card"},
            "gift1": {"source": "gift_card", "balance": 100.0},
        },
    }
    pending = {
        "order_id": "#P",
        "user_id": "u1",
        "status": "pending",
        "items": [{"item_id": "old", "product_id": "p1", "price": 10.0}],
        "payment_history": [
            {
                "transaction_type": "payment",
                "payment_method_id": "card1",
                "amount": 10.0,
            }
        ],
    }
    delivered = {
        **pending,
        "order_id": "#D",
        "status": "delivered",
    }
    product = {
        "product_id": "p1",
        "variants": {
            "new": {"item_id": "new", "available": True, "price": 12.0}
        },
    }
    return VisibleProcessState(
        revision=5,
        authenticated_user_id=grounded("u1", "auth"),
        users={"u1": grounded(user, "user")},
        orders={
            "#P": grounded(pending, "pending"),
            "#D": grounded(delivered, "delivered"),
        },
        products={"p1": grounded(product, "product")},
    )


def actions():
    address = {
        "address1": "1 Main St",
        "address2": "",
        "city": "Austin",
        "state": "TX",
        "country": "USA",
        "zip": "78701",
    }
    return [
        ToolAction(
            "cancel_pending_order",
            {"order_id": "#P", "reason": "ordered by mistake"},
        ),
        ToolAction(
            "modify_pending_order_address",
            {"order_id": "#P", **address},
        ),
        ToolAction(
            "modify_pending_order_items",
            {
                "order_id": "#P",
                "item_ids": ["old"],
                "new_item_ids": ["new"],
                "payment_method_id": "card2",
            },
        ),
        ToolAction(
            "modify_pending_order_payment",
            {"order_id": "#P", "payment_method_id": "card2"},
        ),
        ToolAction(
            "modify_user_address",
            {"user_id": "u1", **address},
        ),
        ToolAction(
            "return_delivered_order_items",
            {
                "order_id": "#D",
                "item_ids": ["old"],
                "payment_method_id": "card1",
            },
        ),
        ToolAction(
            "exchange_delivered_order_items",
            {
                "order_id": "#D",
                "item_ids": ["old"],
                "new_item_ids": ["new"],
                "payment_method_id": "card2",
            },
        ),
    ]


def test_disabled_control_preserves_candidate_object_identity():
    action = actions()[0]
    decision = PassThroughPreWriteControl.evaluate(state(), action)
    assert decision.disposition == PreWriteDisposition.ALLOW_UNCHANGED
    assert decision.candidate is action


def test_b_signature_has_no_goal_or_support_card_input():
    parameters = inspect.signature(
        DeterministicPreWriteControl.evaluate
    ).parameters
    assert set(parameters) == {"state", "candidate", "confirmation"}


def test_b_source_contains_no_model_or_generation_dependency():
    source = (
        Path(__file__).resolve().parents[1]
        / "artifact/retail/prewrite_control.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not {
        "GoalRecord",
        "SupportCard",
        "generate",
        "generate_fn",
    } & (imported_names | called_names)
    assert not any("llm" in name.casefold() for name in imported_names)


def test_all_seven_write_families_require_exact_confirmation_then_release_unchanged():
    for action in actions():
        visible = state()
        first = DeterministicPreWriteControl.evaluate(visible, action)
        assert first.disposition == PreWriteDisposition.REQUEST_CONFIRMATION
        assert first.candidate is action
        visible.revision += 1
        token = bind_confirmation(
            first.confirmation_ticket,
            user_text="Yes, please proceed.",
            user_event_id="confirmation",
            current_state_revision=visible.revision,
        )
        released = DeterministicPreWriteControl.evaluate(
            visible,
            action,
            confirmation=token,
        )
        assert released.disposition == PreWriteDisposition.ALLOW_UNCHANGED
        assert released.candidate is action


def test_confirmation_for_one_action_cannot_release_a_changed_action():
    visible = state()
    original = actions()[0]
    ticket = DeterministicPreWriteControl.evaluate(
        visible,
        original,
    ).confirmation_ticket
    visible.revision += 1
    token = bind_confirmation(
        ticket,
        user_text="I confirm",
        user_event_id="confirmation",
        current_state_revision=visible.revision,
    )
    changed = ToolAction(
        "cancel_pending_order",
        {"order_id": "#P", "reason": "no longer needed"},
    )
    decision = DeterministicPreWriteControl.evaluate(
        visible,
        changed,
        confirmation=token,
    )
    assert decision.disposition == PreWriteDisposition.REQUEST_CONFIRMATION
    assert action_digest(changed) != ticket.action_digest


def test_missing_order_requests_only_the_specific_read():
    visible = state()
    visible.orders.clear()
    action = actions()[0]
    decision = DeterministicPreWriteControl.evaluate(visible, action)
    assert decision.disposition == PreWriteDisposition.REQUEST_EVIDENCE
    assert decision.evidence_action.tool_name == "get_order_details"
    assert decision.evidence_action.arguments == {"order_id": "#P"}


def test_failed_evidence_read_is_not_repeated():
    visible = state()
    visible.orders.clear()
    visible.failed_tool_actions.add(
        canonical_tool_action("get_order_details", {"order_id": "#P"})
    )
    decision = DeterministicPreWriteControl.evaluate(visible, actions()[0])
    assert decision.disposition == PreWriteDisposition.REJECT
    assert decision.reason_code == "B_FAILED_EVIDENCE_READ_SUPPRESSED"


def test_invalid_or_foreign_writes_are_rejected_before_confirmation():
    visible = state()
    bad = ToolAction(
        "cancel_pending_order",
        {"order_id": "#P", "reason": "because"},
    )
    assert (
        DeterministicPreWriteControl.evaluate(visible, bad).reason_code
        == "B_INVALID_CANCEL_REASON"
    )
    visible.orders["#P"].value["user_id"] = "u2"
    assert (
        DeterministicPreWriteControl.evaluate(
            visible,
            actions()[0],
        ).reason_code
        == "B_FOREIGN_ORDER"
    )


def test_b_frozen_predicate_matrix_reaches_every_failure_branch():
    """Contract test: every documented B failure is executable and stable."""

    observed: set[str] = set()

    def record(visible, action):
        decision = DeterministicPreWriteControl.evaluate(visible, action)
        observed.add(decision.reason_code)
        return decision

    visible = state()
    visible.authenticated_user_id = None
    record(visible, actions()[0])

    visible = state()
    record(
        visible,
        ToolAction(
            "modify_user_address",
            {
                "user_id": "u2",
                "address1": "1 Main St",
                "address2": "",
                "city": "Austin",
                "state": "TX",
                "country": "USA",
                "zip": "78701",
            },
        ),
    )
    record(
        state(),
        ToolAction("modify_user_address", {"user_id": "u1"}),
    )
    record(state(), ToolAction("cancel_pending_order", {"reason": "ordered by mistake"}))

    visible = state()
    visible.orders.clear()
    record(visible, actions()[0])

    visible = state()
    visible.orders["#P"].value["user_id"] = "u2"
    record(visible, actions()[0])

    visible = state()
    visible.orders["#P"].value["status"] = "cancelled"
    record(visible, actions()[0])

    visible = state()
    visible.completed_writes.append(
        grounded(
            {
                "tool_name": actions()[0].tool_name,
                "arguments": actions()[0].arguments,
            },
            "prior-write",
        )
    )
    record(visible, actions()[0])

    record(
        state(),
        ToolAction(
            "cancel_pending_order",
            {"order_id": "#P", "reason": "unsupported"},
        ),
    )
    record(
        state(),
        ToolAction(
            "return_delivered_order_items",
            {"order_id": "#D", "item_ids": [], "payment_method_id": "card1"},
        ),
    )
    record(
        state(),
        ToolAction(
            "return_delivered_order_items",
            {"order_id": "#D", "item_ids": ["absent"], "payment_method_id": "card1"},
        ),
    )
    record(
        state(),
        ToolAction(
            "modify_pending_order_items",
            {
                "order_id": "#P",
                "item_ids": ["old"],
                "new_item_ids": [],
                "payment_method_id": "card2",
            },
        ),
    )
    record(
        state(),
        ToolAction(
            "modify_pending_order_items",
            {
                "order_id": "#P",
                "item_ids": ["old"],
                "new_item_ids": ["old"],
                "payment_method_id": "card2",
            },
        ),
    )

    visible = state()
    visible.products.clear()
    record(visible, actions()[2])

    wrong_family = deepcopy(state())
    wrong_family.products["p1"].value["variants"].clear()
    record(wrong_family, actions()[2])

    unavailable = deepcopy(state())
    unavailable.products["p1"].value["variants"]["new"]["available"] = False
    record(unavailable, actions()[2])

    no_profile = state()
    no_profile.users.clear()
    record(no_profile, actions()[3])

    record(
        state(),
        ToolAction(
            "modify_pending_order_payment",
            {"order_id": "#P", "payment_method_id": "foreign-card"},
        ),
    )
    record(
        state(),
        ToolAction(
            "return_delivered_order_items",
            {"order_id": "#D", "item_ids": ["old"], "payment_method_id": "card2"},
        ),
    )

    invalid_history = state()
    invalid_history.orders["#P"].value["payment_history"].append(
        {"transaction_type": "payment", "payment_method_id": "card2", "amount": 1.0}
    )
    record(invalid_history, actions()[3])

    record(
        state(),
        ToolAction(
            "modify_pending_order_payment",
            {"order_id": "#P", "payment_method_id": "card1"},
        ),
    )

    insufficient = state()
    insufficient.users["u1"].value["payment_methods"]["gift1"]["balance"] = 1.0
    record(
        insufficient,
        ToolAction(
            "modify_pending_order_payment",
            {"order_id": "#P", "payment_method_id": "gift1"},
        ),
    )

    assert observed == {
        "B_NOT_AUTHENTICATED",
        "B_FOREIGN_USER",
        "B_INCOMPLETE_ADDRESS",
        "B_MISSING_ORDER_ID",
        "B_ORDER_NOT_OBSERVED",
        "B_FOREIGN_ORDER",
        "B_INELIGIBLE_STATUS",
        "B_DUPLICATE_WRITE",
        "B_INVALID_CANCEL_REASON",
        "B_EMPTY_ITEM_SET",
        "B_ITEM_NOT_IN_ORDER",
        "B_ITEM_LIST_LENGTH",
        "B_VARIANT_UNCHANGED",
        "B_PRODUCT_NOT_OBSERVED",
        "B_WRONG_PRODUCT_FAMILY",
        "B_VARIANT_UNAVAILABLE",
        "B_PAYMENT_PROFILE_NOT_OBSERVED",
        "B_PAYMENT_NOT_OWNED",
        "B_INVALID_REFUND_METHOD",
        "B_PAYMENT_HISTORY",
        "B_PAYMENT_UNCHANGED",
        "B_INSUFFICIENT_BALANCE",
    }
