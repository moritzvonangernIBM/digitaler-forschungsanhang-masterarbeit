from __future__ import annotations

import pytest

from artifact.retail.contracts import (
    GoalKind,
    GoalRecord,
    GoalStatus,
    GroundedField,
    SemanticDisposition,
    VisibleProcessState,
)
from artifact.retail.semantic_support import (
    next_evidence_read,
    parse_goal_records,
    render_support_card,
)
from artifact.retail.state_projection import (
    canonical_tool_action,
)


def grounded(value, source="message:0:user"):
    return GroundedField(value, (source,))


def visible() -> VisibleProcessState:
    return VisibleProcessState(
        revision=4,
        authenticated_user_id=grounded("u1", "tool:auth"),
        users={"u1": grounded({"user_id": "u1"}, "tool:user")},
        user_utterances=[
            grounded("Please cancel order #P because I ordered it by mistake.")
        ],
        visible_user_event_ids=["message:0:user"],
    )


def proposal(order_id="#P"):
    return {
        "goal_id": "g1",
        "revision": 1,
        "kind": "cancel_pending_order",
        "status": "open",
        "fields": {
            "order_id": {
                "value": order_id,
                "source_event_ids": ["message:0:user"],
            },
            "reason": {
                "value": "ordered it by mistake",
                "source_event_ids": ["message:0:user"],
            },
        },
        "depends_on": [],
    }


def test_grounding_accepts_visible_values_and_preserves_sources():
    records = parse_goal_records(visible(), [], [proposal()])
    assert records[0].kind == GoalKind.CANCEL_PENDING_ORDER
    assert records[0].fields["order_id"].value == "#P"
    assert records[0].fields["order_id"].source_event_ids == (
        "message:0:user",
    )


def test_grounding_rejects_one_invented_field_atomically():
    invented = proposal("#INVENTED")
    invented["goal_id"] = "g2"
    with pytest.raises(ValueError, match="not entailed"):
        parse_goal_records(visible(), [], [proposal(), invented])


def test_semantic_extractor_cannot_assert_completed_status():
    invalid = proposal()
    invalid["status"] = "completed"
    with pytest.raises(ValueError, match="cannot assert completion"):
        parse_goal_records(visible(), [], [invalid])


def test_card_contains_concrete_values_sources_and_is_deterministically_bounded():
    records = parse_goal_records(visible(), [], [proposal()])
    normal = render_support_card(records, opportunity_id="AOP-1", max_chars=2048)
    assert normal.disposition == SemanticDisposition.SUPPORT_CARD
    assert "#P" in normal.card.content
    assert "message:0:user" in normal.card.content
    assert "allowed" not in normal.card.content.casefold()
    assert not normal.card.truncated

    bounded = render_support_card(records, opportunity_id="AOP-1", max_chars=96)
    assert len(bounded.card.content) <= 96
    assert bounded.card.truncated
    assert bounded.card.content.endswith("... [CARD TRUNCATED]")


def test_evidence_frontier_returns_one_read_and_suppresses_failed_duplicate():
    state = visible()
    records = parse_goal_records(state, [], [proposal()])
    decision = next_evidence_read(state, records, opportunity_id="AOP-1")
    assert decision.disposition == SemanticDisposition.REQUEST_READ
    assert decision.action.tool_name == "get_order_details"
    assert decision.action.arguments == {"order_id": "#P"}
    assert decision.action.tool_name in {
        "get_order_details",
        "get_product_details",
        "get_user_details",
    }

    state.failed_tool_actions.add(
        canonical_tool_action("get_order_details", {"order_id": "#P"})
    )
    suppressed = next_evidence_read(
        state,
        records,
        opportunity_id="AOP-1",
    )
    assert suppressed.disposition == SemanticDisposition.NO_OP
    assert suppressed.reason_code == "A_DUPLICATE_FAILED_READ_SUPPRESSED"


def test_no_authenticated_user_means_no_semantic_read():
    state = visible()
    state.authenticated_user_id = None
    records = parse_goal_records(state, [], [proposal()])
    decision = next_evidence_read(state, records, opportunity_id="AOP-1")
    assert decision.disposition == SemanticDisposition.NO_OP
    assert decision.reason_code == "A_AUTHENTICATION_REQUIRED"


def test_empty_or_terminal_goals_do_not_create_a_card():
    completed = GoalRecord(
        "g1",
        1,
        GoalKind.CANCEL_PENDING_ORDER,
        GoalStatus.COMPLETED,
        {"order_id": grounded("#P")},
    )
    decision = render_support_card(
        [completed],
        opportunity_id="AOP-1",
        max_chars=2048,
    )
    assert decision.disposition == SemanticDisposition.NO_OP
    assert decision.card is None
