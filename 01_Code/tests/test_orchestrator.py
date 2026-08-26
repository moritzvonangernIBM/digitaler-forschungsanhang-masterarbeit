from __future__ import annotations

from dataclasses import replace

from artifact.retail.configuration import (
    load_frozen_configuration,
)
from artifact.retail.contracts import (
    GoalKind,
    GoalRecord,
    GoalStatus,
    GroundedField,
    PreWriteDisposition,
    SemanticDisposition,
    ToolAction,
    VisibleProcessState,
)
from artifact.retail.orchestrator import (
    RuntimeInterventionOrchestrator,
)
from artifact.retail.telemetry import (
    EventLedger,
)


def grounded(value, source):
    return GroundedField(value, (source,))


def visible(*, with_order=True, revision=3):
    order = {
        "order_id": "#P",
        "user_id": "u1",
        "status": "pending",
        "items": [],
        "payment_history": [
            {
                "transaction_type": "payment",
                "payment_method_id": "card1",
                "amount": 10,
            }
        ],
    }
    return VisibleProcessState(
        revision=revision,
        authenticated_user_id=grounded("u1", "auth"),
        users={
            "u1": grounded(
                {
                    "user_id": "u1",
                    "payment_methods": {
                        "card1": {"source": "credit_card"}
                    },
                },
                "user",
            )
        },
        orders={"#P": grounded(order, "order")} if with_order else {},
        user_utterances=[
            grounded(
                "Cancel order #P because it was ordered by mistake.",
                "message:0:user",
            )
        ],
        visible_user_event_ids=["message:0:user"],
    )


def proposal():
    return {
        "goal_id": "g1",
        "revision": 1,
        "kind": "cancel_pending_order",
        "status": "open",
        "fields": {
            "order_id": {
                "value": "#P",
                "source_event_ids": ["message:0:user"],
            }
        },
        "depends_on": [],
    }


def action():
    return ToolAction(
        "cancel_pending_order",
        {"order_id": "#P", "reason": "ordered by mistake"},
    )


def test_all_conditions_use_the_same_orchestrator_class_and_ports():
    orchestrators = [
        RuntimeInterventionOrchestrator(load_frozen_configuration(condition))
        for condition in (
            "C0_NATIVE",
            "C1_SEMANTIC_SUPPORT",
            "C2_PREWRITE_CONTROL",
            "C3_COMBINED_INTERVENTION",
        )
    ]
    assert {type(item) for item in orchestrators} == {
        RuntimeInterventionOrchestrator
    }
    assert [item.prewrite.enabled for item in orchestrators] == [
        False,
        False,
        True,
        True,
    ]


def test_a_disabled_records_no_op_without_extraction():
    orchestrator = RuntimeInterventionOrchestrator(
        load_frozen_configuration("C0_NATIVE")
    )
    runtime = orchestrator.new_state()
    state = visible()
    opportunity = orchestrator.start_semantic_opportunity(
        runtime,
        state,
        source_event_id="message:0:user",
    )
    decision = orchestrator.complete_semantic_opportunity(
        runtime,
        state,
        opportunity,
        proposals=None,
    )
    assert not opportunity.should_extract
    assert decision.disposition == SemanticDisposition.NO_OP
    assert runtime.a_extractions == 0
    assert runtime.ledger.audit()["pass"]


def test_a_card_does_not_gain_authority_over_b():
    orchestrator = RuntimeInterventionOrchestrator(
        load_frozen_configuration("C3_COMBINED_INTERVENTION")
    )
    runtime = orchestrator.new_state()
    state = visible()
    opportunity = orchestrator.start_semantic_opportunity(
        runtime,
        state,
        source_event_id="message:0:user",
    )
    semantic = orchestrator.complete_semantic_opportunity(
        runtime,
        state,
        opportunity,
        proposals=[proposal()],
    )
    assert semantic.disposition == SemanticDisposition.SUPPORT_CARD
    # Candidate reason intentionally differs from the semantic record.
    candidate = ToolAction(
        "cancel_pending_order",
        {"order_id": "#P", "reason": "no longer needed"},
    )
    b_opportunity, decision = orchestrator.evaluate_candidate(
        runtime,
        state,
        candidate,
        original_call_id="native-1",
    )
    assert b_opportunity == "BOP-0001"
    assert decision.disposition == PreWriteDisposition.REQUEST_CONFIRMATION
    assert decision.reason_code == "B_CONFIRM_EXACT_WRITE"


def test_b_preserves_one_candidate_across_evidence_and_confirmation():
    orchestrator = RuntimeInterventionOrchestrator(
        load_frozen_configuration("C2_PREWRITE_CONTROL")
    )
    runtime = orchestrator.new_state()
    missing = visible(with_order=False)
    opportunity_id, first = orchestrator.evaluate_candidate(
        runtime,
        missing,
        action(),
        original_call_id="native-1",
    )
    assert first.disposition == PreWriteDisposition.REQUEST_EVIDENCE
    assert runtime.pending_prewrite.action == action()

    observed = visible(with_order=True, revision=5)
    _, second = orchestrator.resume_after_evidence(runtime, observed)
    assert second.disposition == PreWriteDisposition.REQUEST_CONFIRMATION
    assert runtime.pending_prewrite.action == action()

    confirmed = visible(with_order=True, revision=6)
    _, third = orchestrator.resume_after_confirmation(
        runtime,
        confirmed,
        user_text="Yes, please proceed.",
        user_event_id="message:5:user",
    )
    assert third.disposition == PreWriteDisposition.ALLOW_UNCHANGED
    assert third.candidate == action()
    orchestrator.record_action_emitted(
        runtime,
        confirmed,
        opportunity_id=opportunity_id,
        action=third.candidate,
        emitted_call_id="write-1",
        role="revalidated_candidate_write",
    )
    orchestrator.record_final_disposition(
        runtime,
        confirmed,
        opportunity_id=opportunity_id,
        disposition="executed_unchanged",
        reason_code=third.reason_code,
        emitted_call_id="write-1",
    )
    audit = runtime.ledger.audit()
    assert audit["pass"], audit["issues"]
    assert audit["b_opportunities"] == 1
    assert audit["b_final_dispositions"] == 1


def test_b_evidence_budget_exhaustion_is_bounded_and_transfers_once():
    config = load_frozen_configuration("C2_PREWRITE_CONTROL")
    config = replace(
        config,
        module_b=replace(
            config.module_b,
            max_evidence_reads_per_candidate=1,
            max_evidence_reads_per_episode=1,
        ),
    )
    orchestrator = RuntimeInterventionOrchestrator(config)
    runtime = orchestrator.new_state()
    missing = visible(with_order=False)
    _, first = orchestrator.evaluate_candidate(
        runtime,
        missing,
        action(),
        original_call_id="native-1",
    )
    assert first.disposition == PreWriteDisposition.REQUEST_EVIDENCE
    _, exhausted = orchestrator.resume_after_evidence(runtime, missing)
    assert exhausted.disposition == PreWriteDisposition.TRANSFER
    assert runtime.b_evidence_reads == 1
    assert runtime.b_transfers == 1
    assert runtime.pending_prewrite is None


def test_a_extraction_and_card_budgets_are_hard_limits():
    config = load_frozen_configuration("C1_SEMANTIC_SUPPORT")
    config = replace(
        config,
        module_a=replace(
            config.module_a,
            max_extractions_per_episode=1,
            max_support_cards_per_episode=1,
        ),
    )
    orchestrator = RuntimeInterventionOrchestrator(config)
    runtime = orchestrator.new_state()
    state = visible()
    first = orchestrator.start_semantic_opportunity(
        runtime,
        state,
        source_event_id="message:0:user",
    )
    decision = orchestrator.complete_semantic_opportunity(
        runtime,
        state,
        first,
        proposals=[proposal()],
    )
    assert decision.disposition == SemanticDisposition.SUPPORT_CARD
    second = orchestrator.start_semantic_opportunity(
        runtime,
        state,
        source_event_id="message:1:user",
    )
    assert not second.should_extract
    assert second.reason_code == "A_EXTRACTION_BUDGET_EXHAUSTED"
    assert runtime.a_extractions == 1
    assert runtime.a_support_cards == 1


def test_repeated_rejection_and_transfer_are_bounded():
    orchestrator = RuntimeInterventionOrchestrator(
        load_frozen_configuration("C2_PREWRITE_CONTROL")
    )
    runtime = orchestrator.new_state()
    state = visible()
    invalid = ToolAction(
        "cancel_pending_order",
        {"order_id": "#P", "reason": "unsupported"},
    )
    _, first = orchestrator.evaluate_candidate(
        runtime,
        state,
        invalid,
        original_call_id="bad-1",
    )
    assert first.disposition == PreWriteDisposition.REJECT
    _, second = orchestrator.evaluate_candidate(
        runtime,
        state,
        invalid,
        original_call_id="bad-2",
    )
    assert second.disposition == PreWriteDisposition.TRANSFER
    _, third = orchestrator.evaluate_candidate(
        runtime,
        state,
        invalid,
        original_call_id="bad-3",
    )
    assert third.disposition == PreWriteDisposition.REJECT
    assert third.reason_code == "B_TRANSFER_BUDGET_EXHAUSTED"
    assert runtime.b_transfers == 1


def test_telemetry_events_are_immutable_and_reconciled():
    ledger = EventLedger()
    event = ledger.record(
        "A",
        "OPPORTUNITY",
        "A_USER_EVENT",
        opportunity_id="AOP-0001",
        nested={"value": 1},
    )
    try:
        event.payload["new"] = 1
    except TypeError:
        pass
    else:
        raise AssertionError("telemetry payload is mutable")
    ledger.record(
        "A",
        "DECISION",
        "A_DISABLED",
        opportunity_id="AOP-0001",
    )
    assert ledger.audit()["pass"]


def test_goal_completion_is_derived_only_from_visible_successful_write():
    orchestrator = RuntimeInterventionOrchestrator(
        load_frozen_configuration("C1_SEMANTIC_SUPPORT")
    )
    runtime = orchestrator.new_state()
    runtime.goals.append(
        GoalRecord(
            "g1",
            1,
            GoalKind.CANCEL_PENDING_ORDER,
            GoalStatus.OPEN,
            {"order_id": grounded("#P", "message:0:user")},
        )
    )
    state = visible()
    state.completed_writes.append(
        grounded(
            {
                "tool_name": "cancel_pending_order",
                "arguments": {
                    "order_id": "#P",
                    "reason": "ordered by mistake",
                },
                "result": {"status": "cancelled"},
            },
            "tool:write",
        )
    )
    completed = orchestrator.reconcile_goals(runtime, state)
    assert len(completed) == 1
    assert completed[0].status == GoalStatus.COMPLETED
