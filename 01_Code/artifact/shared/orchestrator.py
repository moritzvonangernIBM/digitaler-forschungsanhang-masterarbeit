"""Single composition path for all four intervention conditions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from artifact.shared.configuration import (
    FrozenRuntimeConfiguration,
)
from artifact.shared.contracts import (
    ConfirmationTicket,
    GoalRecord,
    PreWriteDecision,
    PreWriteDisposition,
    SemanticDecision,
    SemanticDisposition,
    SemanticOpportunity,
    ToolAction,
    VisibleProcessState,
)
from artifact.shared.domain import (
    DomainRuntimeBindings,
)
from artifact.shared.telemetry import (
    EventLedger,
)


@dataclass(slots=True)
class PendingPreWrite:
    action: ToolAction
    original_call_id: str
    opportunity_id: str
    evidence_reads: int = 0
    confirmation_ticket: ConfirmationTicket | None = None


@dataclass(slots=True)
class InterventionState:
    condition: str
    ledger: EventLedger = field(default_factory=EventLedger)
    goals: list[GoalRecord] = field(default_factory=list)
    processed_write_events: set[str] = field(default_factory=set)
    pending_semantic_opportunity_id: str | None = None
    pending_prewrite: PendingPreWrite | None = None
    a_opportunities: int = 0
    a_extractions: int = 0
    a_evidence_reads: int = 0
    a_support_cards: int = 0
    b_opportunities: int = 0
    b_evidence_reads: int = 0
    b_confirmation_cycles: int = 0
    b_transfers: int = 0
    confirmation_requests_by_digest: dict[str, int] = field(default_factory=dict)
    rejections_by_digest: dict[str, int] = field(default_factory=dict)


class RuntimeInterventionOrchestrator:
    """Compose A/no-op, native-agent port, and B/no-op in one fixed order."""

    def __init__(
        self,
        config: FrozenRuntimeConfiguration,
        bindings: DomainRuntimeBindings | None = None,
    ) -> None:
        self.config = config
        if bindings is None:
            from artifact.retail.bindings import (
                RETAIL_BINDINGS,
            )

            bindings = RETAIL_BINDINGS
        self.bindings = bindings
        self.prewrite = (
            bindings.enabled_prewrite_factory()
            if config.factors.prewrite_control
            else bindings.disabled_prewrite_factory()
        )

    def new_state(self) -> InterventionState:
        return InterventionState(condition=self.config.condition)

    @staticmethod
    def _sources(decision: SemanticDecision) -> list[str]:
        if decision.action is not None:
            return list(decision.action.source_event_ids)
        if decision.card is not None:
            return list(decision.card.source_event_ids)
        return []

    def reconcile_goals(
        self,
        state: InterventionState,
        visible: VisibleProcessState,
    ) -> tuple[GoalRecord, ...]:
        completed = self.bindings.reconcile_completed_goals(
            state.goals,
            visible,
            state.processed_write_events,
        )
        for goal in completed:
            state.ledger.record(
                "A",
                "STATE_CHANGE",
                "A_GOAL_COMPLETED",
                state_revision=visible.revision,
                goal_binding=f"{goal.goal_id}@{goal.revision}",
                source_event_ids=[
                    source
                    for field in goal.fields.values()
                    for source in field.source_event_ids
                ],
            )
        return completed

    def start_semantic_opportunity(
        self,
        state: InterventionState,
        visible: VisibleProcessState,
        *,
        source_event_id: str,
        skip_reason: str | None = None,
    ) -> SemanticOpportunity:
        state.a_opportunities += 1
        opportunity_id = f"AOP-{state.a_opportunities:04d}"
        state.ledger.record(
            "A",
            "OPPORTUNITY",
            "A_USER_EVENT",
            opportunity_id=opportunity_id,
            state_revision=visible.revision,
            source_event_ids=[source_event_id] if source_event_id else [],
        )
        if skip_reason is not None:
            reason = f"A_SKIPPED_{skip_reason}"
            state.ledger.record(
                "A",
                "DECISION",
                reason,
                opportunity_id=opportunity_id,
                state_revision=visible.revision,
                disposition=SemanticDisposition.NO_OP.value,
            )
            return SemanticOpportunity(opportunity_id, False, reason)
        if not self.config.factors.semantic_support:
            state.ledger.record(
                "A",
                "DECISION",
                "A_DISABLED",
                opportunity_id=opportunity_id,
                state_revision=visible.revision,
                disposition=SemanticDisposition.NO_OP.value,
            )
            return SemanticOpportunity(opportunity_id, False, "A_DISABLED")
        if (
            state.a_extractions
            >= self.config.module_a.max_extractions_per_episode
        ):
            state.ledger.record(
                "A",
                "DECISION",
                "A_EXTRACTION_BUDGET_EXHAUSTED",
                opportunity_id=opportunity_id,
                state_revision=visible.revision,
                disposition=SemanticDisposition.NO_OP.value,
            )
            return SemanticOpportunity(
                opportunity_id,
                False,
                "A_EXTRACTION_BUDGET_EXHAUSTED",
            )
        state.a_extractions += 1
        state.ledger.record(
            "A",
            "ACTIVATION",
            "A_EXTRACTION_CALLED",
            opportunity_id=opportunity_id,
            state_revision=visible.revision,
            extraction_number=state.a_extractions,
        )
        return SemanticOpportunity(
            opportunity_id,
            True,
            "A_EXTRACTION_ALLOWED",
        )

    def complete_semantic_opportunity(
        self,
        state: InterventionState,
        visible: VisibleProcessState,
        opportunity: SemanticOpportunity,
        *,
        proposals: list[dict[str, Any]] | None,
        extraction_error: str | None = None,
    ) -> SemanticDecision:
        if not opportunity.should_extract:
            return SemanticDecision(
                SemanticDisposition.NO_OP,
                opportunity.reason_code,
                opportunity.opportunity_id,
            )
        if extraction_error is not None:
            decision = SemanticDecision(
                SemanticDisposition.NO_OP,
                "A_EXTRACTION_FAIL_OPEN",
                opportunity.opportunity_id,
            )
            state.ledger.record(
                "A",
                "DECISION",
                decision.reason_code,
                opportunity_id=opportunity.opportunity_id,
                state_revision=visible.revision,
                disposition=decision.disposition.value,
                error=extraction_error,
            )
            return decision
        try:
            records = self.bindings.parse_goal_records(
                visible,
                state.goals,
                proposals or [],
            )
        except (KeyError, TypeError, ValueError) as exc:
            state.ledger.record(
                "A",
                "VALIDATION",
                "A_GROUNDING_VALIDATION_FAILED",
                opportunity_id=opportunity.opportunity_id,
                state_revision=visible.revision,
                proposal_count=len(proposals or []),
                error_type=type(exc).__name__,
                error=str(exc),
            )
            decision = SemanticDecision(
                SemanticDisposition.NO_OP,
                "A_GROUNDING_FAIL_OPEN",
                opportunity.opportunity_id,
            )
            state.ledger.record(
                "A",
                "DECISION",
                decision.reason_code,
                opportunity_id=opportunity.opportunity_id,
                state_revision=visible.revision,
                disposition=decision.disposition.value,
                error=str(exc),
            )
            return decision
        state.ledger.record(
            "A",
            "VALIDATION",
            "A_GROUNDING_VALIDATION_PASSED",
            opportunity_id=opportunity.opportunity_id,
            state_revision=visible.revision,
            proposal_count=len(proposals or []),
            accepted_goal_count=len(records),
        )
        state.goals.extend(records)
        if records:
            state.ledger.record(
                "A",
                "STATE_CHANGE",
                "A_GOALS_ACCEPTED",
                opportunity_id=opportunity.opportunity_id,
                state_revision=visible.revision,
                goal_bindings=[
                    f"{goal.goal_id}@{goal.revision}" for goal in records
                ],
                source_event_ids=list(
                    dict.fromkeys(
                        source
                        for goal in records
                        for field in goal.fields.values()
                        for source in field.source_event_ids
                    )
                ),
            )
        return self._semantic_read_or_card(
            state,
            visible,
            opportunity.opportunity_id,
        )

    def _semantic_read_or_card(
        self,
        state: InterventionState,
        visible: VisibleProcessState,
        opportunity_id: str,
    ) -> SemanticDecision:
        if (
            state.a_evidence_reads
            < self.config.module_a.max_evidence_reads_per_episode
        ):
            evidence = self.bindings.next_evidence_read(
                visible,
                state.goals,
                opportunity_id=opportunity_id,
            )
            if evidence.disposition == SemanticDisposition.REQUEST_READ:
                state.a_evidence_reads += 1
                state.pending_semantic_opportunity_id = opportunity_id
                state.ledger.record(
                    "A",
                    "DECISION",
                    evidence.reason_code,
                    opportunity_id=opportunity_id,
                    state_revision=visible.revision,
                    disposition=evidence.disposition.value,
                    tool_name=evidence.action.tool_name if evidence.action else None,
                    arguments=evidence.action.arguments if evidence.action else None,
                    source_event_ids=self._sources(evidence),
                )
                state.ledger.record(
                    "A",
                    "MATERIAL_INTERVENTION",
                    "A_EVIDENCE_READ",
                    opportunity_id=opportunity_id,
                    state_revision=visible.revision,
                    read_number=state.a_evidence_reads,
                )
                return evidence
        elif state.goals:
            state.ledger.record(
                "A",
                "BUDGET",
                "A_EVIDENCE_BUDGET_EXHAUSTED",
                opportunity_id=opportunity_id,
                state_revision=visible.revision,
            )
        return self._semantic_card(
            state,
            visible,
            opportunity_id,
            event_type="DECISION",
        )

    def _semantic_card(
        self,
        state: InterventionState,
        visible: VisibleProcessState,
        opportunity_id: str,
        *,
        event_type: str,
    ) -> SemanticDecision:
        if (
            state.a_support_cards
            >= self.config.module_a.max_support_cards_per_episode
        ):
            decision = SemanticDecision(
                SemanticDisposition.NO_OP,
                "A_CARD_BUDGET_EXHAUSTED",
                opportunity_id,
            )
        else:
            decision = self.bindings.render_support_card(
                state.goals,
                opportunity_id=opportunity_id,
                max_chars=self.config.module_a.max_support_card_chars,
            )
        state.ledger.record(
            "A",
            event_type,
            decision.reason_code,
            opportunity_id=opportunity_id,
            state_revision=visible.revision,
            disposition=decision.disposition.value,
            source_event_ids=self._sources(decision),
            goal_bindings=(
                list(decision.card.goal_bindings)
                if decision.card is not None
                else []
            ),
            truncated=(
                decision.card.truncated if decision.card is not None else False
            ),
        )
        if decision.disposition == SemanticDisposition.SUPPORT_CARD:
            state.a_support_cards += 1
            state.ledger.record(
                "A",
                "MATERIAL_INTERVENTION",
                "A_CARD_INJECTED",
                opportunity_id=opportunity_id,
                state_revision=visible.revision,
                card_number=state.a_support_cards,
                card_chars=len(decision.card.content) if decision.card else 0,
            )
        return decision

    def complete_semantic_after_read(
        self,
        state: InterventionState,
        visible: VisibleProcessState,
    ) -> SemanticDecision | None:
        opportunity_id = state.pending_semantic_opportunity_id
        if opportunity_id is None:
            return None
        state.pending_semantic_opportunity_id = None
        return self._semantic_card(
            state,
            visible,
            opportunity_id,
            event_type="FOLLOW_UP_DECISION",
        )

    def evaluate_candidate(
        self,
        state: InterventionState,
        visible: VisibleProcessState,
        candidate: ToolAction,
        *,
        original_call_id: str,
    ) -> tuple[str, PreWriteDecision]:
        state.b_opportunities += 1
        opportunity_id = f"BOP-{state.b_opportunities:04d}"
        state.ledger.record(
            "B",
            "OPPORTUNITY",
            "B_WRITE_CANDIDATE",
            opportunity_id=opportunity_id,
            state_revision=visible.revision,
            original_call_id=original_call_id,
            tool_name=candidate.tool_name,
            arguments=candidate.arguments,
            action_digest=self.bindings.action_digest(candidate),
        )
        decision = self.prewrite.evaluate(visible, candidate)
        return opportunity_id, self._handle_prewrite_decision(
            state,
            visible,
            opportunity_id,
            original_call_id,
            decision,
            evidence_reads=0,
        )

    def reject_invalid_message_shape(
        self,
        state: InterventionState,
        visible: VisibleProcessState,
        candidate: ToolAction,
        *,
        original_call_id: str,
        tool_call_count: int,
    ) -> tuple[str, PreWriteDecision]:
        state.b_opportunities += 1
        opportunity_id = f"BOP-{state.b_opportunities:04d}"
        state.ledger.record(
            "B",
            "OPPORTUNITY",
            "B_WRITE_CANDIDATE",
            opportunity_id=opportunity_id,
            state_revision=visible.revision,
            original_call_id=original_call_id,
            tool_name=candidate.tool_name,
            arguments=candidate.arguments,
            action_digest=self.bindings.action_digest(candidate),
        )
        decision = PreWriteDecision(
            PreWriteDisposition.REJECT,
            "B_INVALID_MESSAGE_SHAPE",
            candidate,
        )
        state.ledger.record(
            "B",
            "DECISION",
            decision.reason_code,
            opportunity_id=opportunity_id,
            state_revision=visible.revision,
            disposition=decision.disposition.value,
            tool_call_count=tool_call_count,
        )
        return opportunity_id, decision

    def resume_after_evidence(
        self,
        state: InterventionState,
        visible: VisibleProcessState,
    ) -> tuple[str, PreWriteDecision] | None:
        pending = state.pending_prewrite
        if pending is None or pending.confirmation_ticket is not None:
            return None
        decision = self.prewrite.evaluate(visible, pending.action)
        return pending.opportunity_id, self._handle_prewrite_decision(
            state,
            visible,
            pending.opportunity_id,
            pending.original_call_id,
            decision,
            evidence_reads=pending.evidence_reads,
        )

    def resume_after_confirmation(
        self,
        state: InterventionState,
        visible: VisibleProcessState,
        *,
        user_text: str,
        user_event_id: str,
    ) -> tuple[str, PreWriteDecision] | None:
        pending = state.pending_prewrite
        if pending is None or pending.confirmation_ticket is None:
            return None
        token = self.bindings.bind_confirmation(
            pending.confirmation_ticket,
            user_text=user_text,
            user_event_id=user_event_id,
            current_state_revision=visible.revision,
        )
        if token is None:
            decision = PreWriteDecision(
                PreWriteDisposition.REJECT,
                "B_CONFIRMATION_NOT_BOUND",
                pending.action,
            )
        else:
            decision = self.prewrite.evaluate(
                visible,
                pending.action,
                confirmation=token,
            )
        return pending.opportunity_id, self._handle_prewrite_decision(
            state,
            visible,
            pending.opportunity_id,
            pending.original_call_id,
            decision,
            evidence_reads=pending.evidence_reads,
        )

    def _handle_prewrite_decision(
        self,
        state: InterventionState,
        visible: VisibleProcessState,
        opportunity_id: str,
        original_call_id: str,
        decision: PreWriteDecision,
        *,
        evidence_reads: int,
    ) -> PreWriteDecision:
        digest = self.bindings.action_digest(decision.candidate)
        final = decision
        if decision.disposition == PreWriteDisposition.REQUEST_EVIDENCE:
            if (
                evidence_reads
                >= self.config.module_b.max_evidence_reads_per_candidate
                or state.b_evidence_reads
                >= self.config.module_b.max_evidence_reads_per_episode
            ):
                final = PreWriteDecision(
                    PreWriteDisposition.TRANSFER,
                    "B_EVIDENCE_BUDGET_EXHAUSTED",
                    decision.candidate,
                )
            else:
                evidence_reads += 1
                state.b_evidence_reads += 1
                state.pending_prewrite = PendingPreWrite(
                    action=decision.candidate,
                    original_call_id=original_call_id,
                    opportunity_id=opportunity_id,
                    evidence_reads=evidence_reads,
                )
        elif decision.disposition == PreWriteDisposition.REQUEST_CONFIRMATION:
            count = state.confirmation_requests_by_digest.get(digest, 0)
            if (
                count
                >= self.config.module_b.max_confirmation_requests_per_action_digest
                or state.b_confirmation_cycles
                >= self.config.module_b.max_confirmation_cycles_per_episode
            ):
                final = PreWriteDecision(
                    PreWriteDisposition.TRANSFER,
                    "B_CONFIRMATION_BUDGET_EXHAUSTED",
                    decision.candidate,
                )
            else:
                state.confirmation_requests_by_digest[digest] = count + 1
                state.b_confirmation_cycles += 1
                state.pending_prewrite = PendingPreWrite(
                    action=decision.candidate,
                    original_call_id=original_call_id,
                    opportunity_id=opportunity_id,
                    evidence_reads=evidence_reads,
                    confirmation_ticket=decision.confirmation_ticket,
                )
        elif decision.disposition == PreWriteDisposition.REJECT:
            count = state.rejections_by_digest.get(digest, 0)
            if count >= self.config.module_b.max_rejections_per_action_digest:
                final = PreWriteDecision(
                    PreWriteDisposition.TRANSFER,
                    "B_REJECTION_BUDGET_EXHAUSTED",
                    decision.candidate,
                )
            else:
                state.rejections_by_digest[digest] = count + 1
                state.pending_prewrite = None
        else:
            state.pending_prewrite = None

        if final.disposition == PreWriteDisposition.TRANSFER:
            state.pending_prewrite = None
            if state.b_transfers >= self.config.module_b.max_transfers_per_episode:
                final = PreWriteDecision(
                    PreWriteDisposition.REJECT,
                    "B_TRANSFER_BUDGET_EXHAUSTED",
                    decision.candidate,
                )
            else:
                state.b_transfers += 1

        state.ledger.record(
            "B",
            "DECISION",
            final.reason_code,
            opportunity_id=opportunity_id,
            state_revision=visible.revision,
            disposition=final.disposition.value,
            original_call_id=original_call_id,
            tool_name=final.candidate.tool_name,
            arguments=final.candidate.arguments,
            evidence_tool=(
                final.evidence_action.tool_name
                if final.evidence_action is not None
                else None
            ),
            evidence_arguments=(
                final.evidence_action.arguments
                if final.evidence_action is not None
                else None
            ),
            action_digest=digest,
        )
        if final.disposition != PreWriteDisposition.ALLOW_UNCHANGED:
            state.ledger.record(
                "B",
                "MATERIAL_INTERVENTION",
                final.reason_code,
                opportunity_id=opportunity_id,
                state_revision=visible.revision,
                disposition=final.disposition.value,
            )
        return final

    def record_action_emitted(
        self,
        state: InterventionState,
        visible: VisibleProcessState,
        *,
        opportunity_id: str,
        action: ToolAction,
        emitted_call_id: str,
        role: str,
    ) -> None:
        state.ledger.record(
            "B",
            "DOWNSTREAM_ACTION",
            "B_ACTION_EMITTED",
            opportunity_id=opportunity_id,
            state_revision=visible.revision,
            emitted_call_id=emitted_call_id,
            tool_name=action.tool_name,
            arguments=action.arguments,
            action_role=role,
        )

    def record_final_disposition(
        self,
        state: InterventionState,
        visible: VisibleProcessState,
        *,
        opportunity_id: str,
        disposition: str,
        reason_code: str,
        emitted_call_id: str | None = None,
    ) -> None:
        state.ledger.record(
            "B",
            "FINAL_DISPOSITION",
            reason_code,
            opportunity_id=opportunity_id,
            state_revision=visible.revision,
            disposition=disposition,
            emitted_call_id=emitted_call_id,
        )

    def close_pending_at_termination(
        self,
        state: InterventionState,
        visible_revision: int,
    ) -> None:
        pending = state.pending_prewrite
        if pending is None:
            return
        existing = {
            event.opportunity_id
            for event in state.ledger.events
            if event.event_type == "FINAL_DISPOSITION"
        }
        if pending.opportunity_id not in existing:
            state.ledger.record(
                "B",
                "FINAL_DISPOSITION",
                "B_PENDING_AT_TERMINATION",
                opportunity_id=pending.opportunity_id,
                state_revision=visible_revision,
                disposition="pending_at_termination",
            )
