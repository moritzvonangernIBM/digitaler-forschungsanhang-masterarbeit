"""Tau2 adapter implementing the final construct-separated Retail factors."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any

from artifact.retail.bindings import (
    RETAIL_BINDINGS,
)
from artifact.retail.tau2_retail_adapter import (
    RuntimeInterventionState,
    create_retail_runtime_intervention_agent_class,
)
from artifact.retail.state_projection import (
    WRITE_TOOLS,
)
from artifact.shared.contracts import (
    ToolAction,
)
from artifact.shared.tau2_adapter import (
    model_visible_request,
    model_visible_response,
)

from .contracts import CommitmentEntry, FeasibilityDisposition, SemanticSupportCard
from .prewrite_validation import evaluate_bundle, explain_evaluation
from .semantic_support import (
    build_commitment_card,
    is_transaction_request_text,
    merge_commitments,
    parse_snapshot_records,
    snapshot_prompt,
)

RUNTIME_SCHEMA_VERSION = "retail_factorial_runtime_support_v2"
SEMANTIC_SYSTEM_INSTRUCTION = (
    "You are a schema-constrained, source-grounded goal extractor. "
    "You have no action, policy, completion, or runtime authority."
)
MAX_A_EXTRACTIONS = 4


@dataclass(slots=True)
class FactorialRuntimeState(RuntimeInterventionState):
    """Treatment state for a source-grounded selective commitment ledger."""

    commitments: tuple[CommitmentEntry, ...] = ()
    active_card: SemanticSupportCard | None = None
    active_card_id: str | None = None
    active_card_records: tuple[dict[str, Any], ...] = ()
    active_card_uses: int = 0
    retired_card_hashes: tuple[str, ...] = ()
    retired_commitment_versions: tuple[str, ...] = ()
    semantic_ledger_tainted: bool = False
    artifact_schema_version: str = RUNTIME_SCHEMA_VERSION


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _serialise_commitment(entry: Any) -> dict[str, Any]:
    """Serialise both the legacy span ledger and the final evidence ledger."""

    serialiser = getattr(entry, "serialise", None)
    if callable(serialiser):
        return dict(serialiser())
    return {
        "commitment_id": entry.commitment_id,
        "operation": entry.proposal.kind,
        "fields": {
            key: {
                "value": field.value,
                "source_event_ids": list(field.source_event_ids),
            }
            for key, field in sorted(entry.proposal.fields.items())
        },
    }


def _commitment_version(entry: Any) -> str:
    return _sha(json.dumps(_serialise_commitment(entry), sort_keys=True, separators=(",", ":")))


def _usage(message: Any) -> tuple[float, float]:
    return (
        float(getattr(message, "cost", None) or 0.0),
        float(getattr(message, "generation_time_seconds", None) or 0.0),
    )


def _aggregate_usage(message: Any, hidden: list[Any]) -> Any:
    cost, seconds = _usage(message)
    for item in hidden:
        item_cost, item_seconds = _usage(item)
        cost += item_cost
        seconds += item_seconds
    updates = {"cost": cost, "generation_time_seconds": seconds}
    if hasattr(message, "model_copy"):
        return message.model_copy(update=updates)
    for key, value in updates.items():
        setattr(message, key, value)
    return message


def _calls(message: Any) -> tuple[Any, ...]:
    return tuple(getattr(message, "tool_calls", None) or ())


def _write_calls(message: Any) -> tuple[Any, ...]:
    return tuple(
        call
        for call in _calls(message)
        if str(getattr(call, "name", "") or "") in WRITE_TOOLS
    )


def _card_trace_audit(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Check that every injected card is grounded, activated and linked."""

    issues: list[str] = []
    activated: dict[str, dict[str, Any]] = {}
    injected: dict[str, int] = {}
    commitment_ids: set[str] = set()
    for event in events:
        reason = event.get("reason_code")
        card_id = str(event.get("card_id") or "")
        if reason == "A_LEDGER_UPDATED":
            records = event.get("validated_records") or []
            if not records:
                issues.append("ledger update without validated records")
            for record in records:
                commitment_id = str(record.get("commitment_id") or "")
                if not commitment_id:
                    issues.append("ledger record without commitment_id")
                commitment_ids.add(commitment_id)
                for name, field in (record.get("fields") or {}).items():
                    sources = field.get("source_event_ids") or []
                    if not sources:
                        issues.append(
                            f"{commitment_id}: field {name} without source IDs"
                        )
                    expected_role = (
                        ":assistant"
                        if name == "assistant_context_spans"
                        else ":user"
                    )
                    if any(
                        not str(source).endswith(expected_role)
                        for source in sources
                    ):
                        issues.append(
                            f"{commitment_id}: field {name} has invalid source authority"
                        )
                for binding in record.get("bindings") or []:
                    mention = binding.get("mention") or {}
                    source_id = str(mention.get("source_event_id") or "")
                    if not source_id.endswith(":user"):
                        issues.append(
                            f"{commitment_id}: binding mention lacks user authority"
                        )
                    state = binding.get("binding_state")
                    fact_sources = binding.get("fact_source_event_ids") or []
                    if state == "resolved" and not fact_sources:
                        issues.append(
                            f"{commitment_id}: resolved binding lacks fact evidence"
                        )
                    if state != "resolved" and binding.get("canonical_value"):
                        issues.append(
                            f"{commitment_id}: unresolved binding exposes canonical value"
                        )
        elif reason == "A_CARD_ACTIVATED":
            if not card_id:
                issues.append("activated card without card_id")
                continue
            records = event.get("validated_records") or []
            if not records:
                issues.append(f"{card_id}: no validated records")
            for record in records:
                commitment_id = str(record.get("commitment_id") or "")
                if commitment_id and commitment_id not in commitment_ids:
                    issues.append(
                        f"{card_id}: unknown commitment {commitment_id}"
                    )
                fields = record.get("fields") or {}
                if not fields:
                    issues.append(f"{card_id}: record without fields")
                for name, field in fields.items():
                    if not field.get("source_event_ids"):
                        issues.append(
                            f"{card_id}: field {name} without source IDs"
                        )
                    expected_role = (
                        ":assistant"
                        if name == "assistant_context_spans"
                        else ":user"
                    )
                    if any(
                        not str(source).endswith(expected_role)
                        for source in field.get("source_event_ids") or []
                    ):
                        issues.append(
                            f"{card_id}: field {name} has invalid source authority"
                        )
            activated[card_id] = event
        elif reason == "A_CARD_INJECTED":
            if card_id not in activated:
                issues.append(f"{card_id}: injection without activation")
            elif event.get("card_sha256") != activated[card_id].get(
                "card_sha256"
            ):
                issues.append(f"{card_id}: card hash changed before injection")
            injected[card_id] = injected.get(card_id, 0) + 1
        elif reason == "A_CARD_REACHED_WRITE_CANDIDATE":
            if injected.get(card_id, 0) < 1:
                issues.append(f"{card_id}: write linkage without injection")
            if not event.get("candidate_calls"):
                issues.append(f"{card_id}: write linkage without candidate")
    for event in events:
        if event.get("reason_code") != "B_SINGLE_REPLAN":
            continue
        findings = event.get("findings") or []
        if not findings:
            issues.append("B replan without findings")
        for finding in findings:
            if not finding.get("required_response"):
                issues.append("B finding without required response")
            if "observed" not in finding:
                issues.append("B finding without visible-state evidence")
    result = {
        "pass": not issues,
        "issues": issues,
        "activated_cards": len(activated),
        "injected_cards": len(injected),
        "card_injections": sum(injected.values()),
        "write_linkages": sum(
            event.get("reason_code") == "A_CARD_REACHED_WRITE_CANDIDATE"
            for event in events
        ),
    }
    native_linkages = [
        event
        for event in events
        if event.get("reason_code") == "A_CARD_REACHED_NATIVE_DECISION"
    ]
    if native_linkages:
        result["native_decision_linkages"] = len(native_linkages)
        for strength in ("strong", "partial", "none"):
            result[f"native_linkage_{strength}"] = sum(
                event.get("linkage_strength") == strength
                for event in native_linkages
            )
    return result


def factorial_runtime_record(state: FactorialRuntimeState) -> dict[str, Any]:
    config = state._runtime_config
    events = state.intervention.ledger.serialise()
    return {
        "schema_version": state.artifact_schema_version,
        "domain": "retail",
        "condition": state.condition,
        "factors": {
            "semantic_support": config.factors.semantic_support,
            "prewrite_control": config.factors.prewrite_control,
        },
        "counts": {
            "a_opportunities": state.intervention.a_opportunities,
            "a_extractions": state.intervention.a_extractions,
            "a_support_cards": state.intervention.a_support_cards,
            "a_commitments": len(state.commitments),
            "b_opportunities": state.intervention.b_opportunities,
            "b_evidence_reads": state.intervention.b_evidence_reads,
            "b_replans": sum(
                row["component"] == "B"
                and row["reason_code"] == "B_SINGLE_REPLAN"
                for row in events
            ),
        },
        "cost_usd": {
            "native_agent": state.native_cost_usd,
            "semantic_support": state.semantic_cost_usd,
            "prewrite_validation": 0.0,
        },
        "seconds": {
            "native_agent": state.native_seconds,
            "semantic_support": state.semantic_seconds,
            "prewrite_validation": state.prewrite_seconds,
        },
        "events": events,
        "observer_audit": state.intervention.ledger.audit(),
        "semantic_linkage_audit": _card_trace_audit(events),
    }


def create_factorial_retail_runtime_agent_class(
    *,
    snapshot_prompt_impl=snapshot_prompt,
    parse_snapshot_records_impl=parse_snapshot_records,
    merge_commitments_impl=merge_commitments,
    build_commitment_card_impl=build_commitment_card,
    select_active_commitments_impl=lambda commitments, visible: tuple(
        commitments
    ),
    is_transaction_request_text_impl=is_transaction_request_text,
    transaction_opportunity_impl=None,
    evaluate_bundle_impl=evaluate_bundle,
    explain_evaluation_impl=explain_evaluation,
    runtime_schema_version: str = RUNTIME_SCHEMA_VERSION,
    max_card_injections: int | None = None,
    max_a_extractions: int = MAX_A_EXTRACTIONS,
    snapshot_prompt_uses_commitments: bool = False,
    candidate_linkage_impl=None,
    parse_semantic_payload_impl=None,
    semantic_validation_attempts: int = 1,
):
    """Create one agent class from explicit, versioned component hooks.

    Defaults preserve the evaluated V1 behavior exactly. Development profiles
    can supply separate implementations without modifying the frozen path.
    """

    from tau2.agent.base_agent import ValidAgentInputMessage
    from tau2.data_model.message import (
        AssistantMessage,
        MultiToolMessage,
        SystemMessage,
        UserMessage,
    )

    BaseAgent = create_retail_runtime_intervention_agent_class()
    opportunity_detector = transaction_opportunity_impl or (
        lambda text, visible, state: is_transaction_request_text_impl(text)
    )

    class FactorialRetailRuntimeAgent(BaseAgent):
        def get_init_state(
            self,
            message_history: list[Any] | None = None,
        ) -> FactorialRuntimeState:
            base = super().get_init_state(message_history)
            return FactorialRuntimeState(
                domain=base.domain,
                condition=base.condition,
                system_messages=base.system_messages,
                messages=base.messages,
                intervention=base.intervention,
                native_cost_usd=base.native_cost_usd,
                semantic_cost_usd=base.semantic_cost_usd,
                native_seconds=base.native_seconds,
                semantic_seconds=base.semantic_seconds,
                prewrite_seconds=base.prewrite_seconds,
                _orchestrator=base._orchestrator,
                _runtime_config=base._runtime_config,
                _bindings=base._bindings,
                artifact_schema_version=runtime_schema_version,
            )

        @staticmethod
        def _deactivate_card(
            state: FactorialRuntimeState,
            visible: Any,
            *,
            reason_code: str,
        ) -> None:
            if state.active_card is None or state.active_card_id is None:
                return
            state.intervention.ledger.record(
                "A",
                "STATE_CHANGE",
                reason_code,
                state_revision=visible.revision,
                card_id=state.active_card_id,
                card_sha256=_sha(state.active_card.content),
                injection_count=state.active_card_uses,
            )
            state.active_card = None
            state.active_card_id = None
            state.active_card_records = ()
            state.active_card_uses = 0

        def _extract_commitments(
            self,
            state: FactorialRuntimeState,
            visible: Any,
        ) -> Any | None:
            intervention = state.intervention
            intervention.a_opportunities += 1
            opportunity_id = f"AOP-{intervention.a_opportunities:04d}"
            intervention.ledger.record(
                "A",
                "OPPORTUNITY",
                "A_MATERIAL_TRANSACTIONAL_USER_EVENT",
                opportunity_id=opportunity_id,
                state_revision=visible.revision,
                source_event_ids=(
                    [visible.visible_user_event_ids[-1]]
                    if visible.visible_user_event_ids
                    else []
                ),
            )
            intervention.a_extractions += 1
            prompt_commitments = tuple(
                select_active_commitments_impl(state.commitments, visible)
            )
            prompt = (
                snapshot_prompt_impl(
                    visible,
                    # Completed or conflicting commitments must not remain
                    # available as lifecycle targets for the semantic model.
                    commitments=prompt_commitments,
                )
                if snapshot_prompt_uses_commitments
                else snapshot_prompt_impl(visible)
            )
            response = None
            started = time.perf_counter()
            try:
                messages: list[Any] = [
                    SystemMessage(
                        role="system",
                        content=SEMANTIC_SYSTEM_INSTRUCTION,
                    ),
                    UserMessage(role="user", content=prompt),
                ]
                accepted: tuple[Any, ...] = ()
                rejected: tuple[dict[str, Any], ...] = ()
                payload: Any = None
                attempts = max(1, int(semantic_validation_attempts))
                for attempt in range(attempts):
                    intervention.ledger.record(
                        "A",
                        "REQUEST",
                        "A_EXTRACTION_REQUEST",
                        opportunity_id=opportunity_id,
                        state_revision=visible.revision,
                        attempt=attempt + 1,
                        model_request=model_visible_request(
                            model=self.semantic_llm,
                            messages=messages,
                            tools=[],
                            llm_args=self.llm_args,
                        ),
                    )
                    attempt_started = time.perf_counter()
                    response = self.semantic_generate_fn(
                        model=self.semantic_llm,
                        tools=[],
                        messages=messages,
                        call_name="retail_factor_a_goal_support",
                        **self.llm_args,
                    )
                    measured = time.perf_counter() - attempt_started
                    cost, reported = _usage(response)
                    state.semantic_cost_usd += cost
                    state.semantic_seconds += reported or measured
                    raw_content = str(getattr(response, "content", "") or "")
                    intervention.ledger.record(
                        "A",
                        "RESPONSE",
                        "A_EXTRACTION_RESPONSE",
                        opportunity_id=opportunity_id,
                        state_revision=visible.revision,
                        attempt=attempt + 1,
                        raw_content=raw_content,
                        model_response=model_visible_response(response),
                        cost_usd=cost,
                        seconds=reported or measured,
                    )
                    try:
                        payload = json.loads(raw_content)
                        if parse_semantic_payload_impl is not None:
                            if not isinstance(payload, dict):
                                raise ValueError(
                                    "semantic output requires a JSON object"
                                )
                            accepted, rejected = parse_semantic_payload_impl(
                                visible, payload
                            )
                        else:
                            rows = (
                                payload.get("goals")
                                if isinstance(payload, dict)
                                else None
                            )
                            if not isinstance(rows, list):
                                raise ValueError(
                                    "semantic output requires a goals list"
                                )
                            accepted, rejected = parse_snapshot_records_impl(
                                visible, rows
                            )
                    except (json.JSONDecodeError, TypeError, ValueError) as exc:
                        accepted = ()
                        rejected = (
                            {
                                "error_type": type(exc).__name__,
                                "error": str(exc),
                            },
                        )
                    if not rejected or accepted or attempt + 1 >= attempts:
                        break
                    intervention.ledger.record(
                        "A",
                        "STATE_CHANGE",
                        "A_SCHEMA_RETRY_REQUESTED",
                        opportunity_id=opportunity_id,
                        state_revision=visible.revision,
                        attempt=attempt + 1,
                        rejection_details=list(rejected),
                    )
                    messages = messages + [
                        response,
                        UserMessage(
                            role="user",
                            content=(
                                "Your JSON failed deterministic validation: "
                                f"{json.dumps(rejected, sort_keys=True)}. "
                                "Re-read the original evidence and return one "
                                "complete corrected JSON object only. Do not "
                                "add unsupported content."
                            ),
                        ),
                    ]

                revision_attempted = bool(
                    isinstance(payload, dict)
                    and any(
                        isinstance(row, dict)
                        and (
                            row.get("ledger_action") in {"amend", "withdraw"}
                            or row.get("speech_act")
                            in {"correction", "withdrawal"}
                        )
                        for row in payload.get("events") or payload.get("goals") or []
                    )
                )
                if rejected and revision_attempted and state.commitments:
                    state.semantic_ledger_tainted = True
                if not rejected and any(
                    getattr(item, "speech_act", None).value
                    in {"correction", "withdrawal"}
                    for item in accepted
                    if getattr(item, "speech_act", None) is not None
                ):
                    state.semantic_ledger_tainted = False
                merged, changed = merge_commitments_impl(
                    state.commitments,
                    accepted,
                    revision=visible.revision,
                )
                state.commitments = merged
                validated_records = tuple(
                    _serialise_commitment(entry) for entry in changed
                )
                intervention.ledger.record(
                    "A",
                    "DECISION",
                    "A_LEDGER_UPDATED" if changed else "A_VALIDATED_NO_OP",
                    opportunity_id=opportunity_id,
                    state_revision=visible.revision,
                    disposition="STORED_SILENTLY" if changed else "NO_OP",
                    validated_records=list(validated_records),
                    accepted_records=len(accepted),
                    changed_commitments=len(changed),
                    total_commitments=len(state.commitments),
                    rejected_records=len(rejected),
                    rejection_details=list(rejected),
                    source_event_ids=list(
                        dict.fromkeys(
                            source_id
                            for entry in changed
                            for field in entry.proposal.fields.values()
                            for source_id in field.source_event_ids
                        )
                    ),
                    response_sha256=hashlib.sha256(
                        str(getattr(response, "content", "") or "").encode()
                    ).hexdigest(),
                    extraction_attempts=attempt + 1,
                    ledger_quarantined=state.semantic_ledger_tainted,
                    semantic_payload=payload,
                )
                return response
            except Exception as exc:
                measured = time.perf_counter() - started
                if response is None:
                    state.semantic_seconds += measured
                intervention.ledger.record(
                    "A",
                    "DECISION",
                    "A_EXTRACTION_FAIL_OPEN",
                    opportunity_id=opportunity_id,
                    state_revision=visible.revision,
                    disposition="NO_OP",
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                return response

        def _refresh_selective_card(
            self,
            state: FactorialRuntimeState,
            visible: Any,
        ) -> None:
            """Expose A only where the component-specific renderer finds risk."""

            if state.semantic_ledger_tainted:
                self._deactivate_card(
                    state,
                    visible,
                    reason_code="A_LEDGER_QUARANTINED_AFTER_REJECTED_REVISION",
                )
                return

            selectable_commitments = tuple(
                select_active_commitments_impl(state.commitments, visible)
            )
            if not selectable_commitments:
                self._deactivate_card(
                    state,
                    visible,
                    reason_code="A_NO_ACTIVE_GROUNDED_GOAL",
                )
                return
            has_new_commitment_version = any(
                _commitment_version(entry)
                not in state.retired_commitment_versions
                for entry in selectable_commitments
            )
            if not has_new_commitment_version:
                self._deactivate_card(
                    state,
                    visible,
                    reason_code="A_NO_NEW_COMPOUND_RISK",
                )
                return
            card = build_commitment_card_impl(
                selectable_commitments,
                visible,
                max_chars=self.runtime_config.module_a.max_support_card_chars,
            )
            if card is None:
                self._deactivate_card(
                    state,
                    visible,
                    reason_code="A_NO_ADVISORY_DECISION_COMPLEXITY",
                )
                state.intervention.ledger.record(
                    "A",
                    "DECISION",
                    "A_NO_ADVISORY_DECISION_COMPLEXITY",
                    state_revision=visible.revision,
                    disposition="NO_OP",
                    commitment_count=len(state.commitments),
                )
                return
            card_sha256 = _sha(card.content)
            if card_sha256 in state.retired_card_hashes:
                return
            if (
                state.active_card is not None
                and state.active_card.content == card.content
            ):
                return
            self._deactivate_card(
                state,
                visible,
                reason_code="A_CARD_REFRESHED_AFTER_VISIBLE_PROGRESS",
            )
            intervention = state.intervention
            intervention.a_support_cards += 1
            card_id = f"AC-{intervention.a_support_cards:04d}"
            records = tuple(
                _serialise_commitment(entry)
                for entry in selectable_commitments
            )
            state.active_card = card
            state.active_card_id = card_id
            state.active_card_records = records
            state.active_card_uses = 0
            intervention.ledger.record(
                "A",
                "DECISION",
                "A_CARD_ACTIVATED",
                state_revision=visible.revision,
                disposition="SELECTIVE_ADVISORY",
                trigger_reason="A_COMPOUND_COMMITMENT_RISK",
                card_id=card_id,
                card_sha256=_sha(card.content),
                card_content=card.content,
                validated_records=list(records),
                accepted_records=len(records),
                rejected_records=0,
                rejection_details=[],
                source_event_ids=list(card.source_event_ids),
                verified_completed_writes=[
                    {
                        "value": field.value,
                        "source_event_ids": list(field.source_event_ids),
                    }
                    for field in visible.completed_writes
                ],
            )

        def _record_bundle(
            self,
            state: RuntimeInterventionState,
            visible: Any,
            bundle: Any,
            *,
            role: str,
        ) -> list[tuple[str, str]]:
            tracked = []
            for row in bundle.write_evaluations:
                state.intervention.b_opportunities += 1
                opportunity_id = (
                    f"BOP-{state.intervention.b_opportunities:04d}"
                )
                tracked.append((row.call_id, opportunity_id))
                state.intervention.ledger.record(
                    "B",
                    "OPPORTUNITY",
                    "B_NATIVE_WRITE_CANDIDATE",
                    opportunity_id=opportunity_id,
                    state_revision=visible.revision,
                    bundle_id=bundle.bundle_id,
                    candidate_role=role,
                    call_id=row.call_id,
                    tool_name=row.action.tool_name,
                    arguments=row.action.arguments,
                )
                state.intervention.ledger.record(
                    "B",
                    "DECISION",
                    row.reason_code,
                    opportunity_id=opportunity_id,
                    state_revision=visible.revision,
                    disposition=row.disposition.value,
                    decision_evidence=explain_evaluation_impl(visible, row),
                )
            return tracked

        @staticmethod
        def _close(
            state: RuntimeInterventionState,
            visible: Any,
            tracked: list[tuple[str, str]],
            *,
            disposition: str,
            reason_code: str,
        ) -> None:
            for call_id, opportunity_id in tracked:
                state.intervention.ledger.record(
                    "B",
                    "FINAL_DISPOSITION",
                    reason_code,
                    opportunity_id=opportunity_id,
                    state_revision=visible.revision,
                    disposition=disposition,
                    emitted_call_id=(
                        call_id if disposition == "executed_unchanged" else None
                    ),
                )

        @staticmethod
        def _findings(
            visible: Any,
            bundle: Any,
        ) -> list[dict[str, Any]]:
            return [
                explain_evaluation_impl(visible, row)
                for row in bundle.write_evaluations
                if row.disposition != FeasibilityDisposition.VALID_UNCHANGED
            ]

        def _transfer(self, state: RuntimeInterventionState, reason: str) -> Any:
            if RETAIL_BINDINGS.transfer_tool in self.tool_names:
                return self._tool_message(
                    state,
                    ToolAction(
                        RETAIL_BINDINGS.transfer_tool,
                        {"summary": reason},
                        ("runtime-feasibility",),
                    ),
                    prefix="factorial_b_transfer",
                )
            return AssistantMessage.text(
                "I cannot safely complete that action and need human support."
            )

        def _govern(
            self,
            state: FactorialRuntimeState,
            visible: Any,
            candidate: Any,
            *,
            semantic_context: str | None,
        ) -> tuple[Any, list[Any]]:
            started = time.perf_counter()
            bundle = evaluate_bundle_impl(
                visible,
                _calls(candidate),
                enabled=True,
                bundle_id=f"BB-{state.intervention.b_opportunities + 1:04d}-O",
            )
            state.prewrite_seconds += time.perf_counter() - started
            if not bundle.write_evaluations:
                return candidate, []
            tracked = self._record_bundle(
                state, visible, bundle, role="original"
            )
            if bundle.valid:
                self._close(
                    state,
                    visible,
                    tracked,
                    disposition="executed_unchanged",
                    reason_code="B_BUNDLE_VALID_UNCHANGED",
                )
                return candidate, []
            if bundle.evidence_only:
                evidence = next(
                    row.evidence_action
                    for row in bundle.write_evaluations
                    if row.disposition
                    == FeasibilityDisposition.EVIDENCE_REQUIRED
                )
                state.intervention.b_evidence_reads += 1
                self._close(
                    state,
                    visible,
                    tracked,
                    disposition="held_for_evidence",
                    reason_code="B_EXACT_EVIDENCE_READ",
                )
                return self._tool_message(
                    state, evidence, prefix="factorial_b_read"
                ), [candidate]

            self._close(
                state,
                visible,
                tracked,
                disposition="held_for_replan",
                reason_code="B_INVALID_HELD_FOR_SINGLE_REPLAN",
            )
            state.intervention.ledger.record(
                "B",
                "ACTIVATION",
                "B_SINGLE_REPLAN",
                state_revision=visible.revision,
                findings=self._findings(visible, bundle),
            )
            b_context = (
                "The proposed write was not executed. Reconsider it once "
                "using only visible evidence and Retail policy. Correct the "
                "candidate, choose an appropriate read, or transfer. "
                "Do not invent values. Deterministic findings: "
                f"{json.dumps(self._findings(visible, bundle), sort_keys=True)}"
            )
            context = (
                f"{semantic_context}\n\n{b_context}"
                if semantic_context
                else b_context
            )
            revised = self._native(state, private_context=context)
            started = time.perf_counter()
            revised_bundle = evaluate_bundle_impl(
                visible,
                _calls(revised),
                enabled=True,
                bundle_id=f"BB-{state.intervention.b_opportunities + 1:04d}-R",
            )
            state.prewrite_seconds += time.perf_counter() - started
            if not revised_bundle.write_evaluations:
                return revised, [candidate]
            revised_tracked = self._record_bundle(
                state, visible, revised_bundle, role="revised"
            )
            if revised_bundle.valid:
                self._close(
                    state,
                    visible,
                    revised_tracked,
                    disposition="executed_unchanged",
                    reason_code="B_REVISED_BUNDLE_VALID",
                )
                return revised, [candidate]
            if revised_bundle.evidence_only:
                evidence = next(
                    row.evidence_action
                    for row in revised_bundle.write_evaluations
                    if row.disposition
                    == FeasibilityDisposition.EVIDENCE_REQUIRED
                )
                state.intervention.b_evidence_reads += 1
                self._close(
                    state,
                    visible,
                    revised_tracked,
                    disposition="held_for_evidence",
                    reason_code="B_REVISED_EXACT_EVIDENCE_READ",
                )
                return self._tool_message(
                    state, evidence, prefix="factorial_b_read"
                ), [candidate, revised]
            self._close(
                state,
                visible,
                revised_tracked,
                disposition="blocked_after_replan",
                reason_code="B_REVISED_BUNDLE_INVALID",
            )
            return self._transfer(
                state, "The single pre-write replan remained infeasible."
            ), [candidate, revised]

        def generate_next_message(
            self,
            message: ValidAgentInputMessage,
            state: FactorialRuntimeState,
        ):
            if isinstance(message, MultiToolMessage):
                state.messages.extend(message.tool_messages)
            else:
                state.messages.append(message)
            visible = RETAIL_BINDINGS.project_visible_state(state.messages)

            hidden: list[Any] = []
            private_context = None
            # Retire an exhausted card before a new extraction or visible-state
            # refresh can recreate the same content under a new card id.
            if (
                state.active_card is not None
                and max_card_injections is not None
                and state.active_card_uses >= max_card_injections
            ):
                digest = _sha(state.active_card.content)
                state.retired_card_hashes = tuple(
                    dict.fromkeys(state.retired_card_hashes + (digest,))
                )
                self._deactivate_card(
                    state,
                    visible,
                    reason_code="A_CARD_INJECTION_BUDGET_EXHAUSTED",
                )
            new_transaction = bool(
                self.runtime_config.factors.semantic_support
                and isinstance(message, UserMessage)
                and opportunity_detector(
                    str(message.content or ""), visible, state
                )
            )
            if new_transaction:
                if state.intervention.a_extractions < max_a_extractions:
                    response = self._extract_commitments(state, visible)
                    if response is not None:
                        hidden.append(response)

            if self.runtime_config.factors.semantic_support:
                self._refresh_selective_card(state, visible)

            injected_card_id = None
            if state.active_card is not None and state.active_card_id is not None:
                private_context = state.active_card.content
                injected_card_id = state.active_card_id
                state.active_card_uses += 1
                state.intervention.ledger.record(
                    "A",
                    "ACTIVATION",
                    "A_CARD_INJECTED",
                    state_revision=visible.revision,
                    card_id=state.active_card_id,
                    card_sha256=_sha(state.active_card.content),
                    injection_number=state.active_card_uses,
                    source_event_ids=list(
                        state.active_card.source_event_ids
                    ),
                )
                if (
                    max_card_injections is not None
                    and state.active_card_uses >= max_card_injections
                ):
                    state.retired_commitment_versions = tuple(
                        dict.fromkeys(
                            state.retired_commitment_versions
                            + tuple(
                                _sha(
                                    json.dumps(
                                        record,
                                        sort_keys=True,
                                        separators=(",", ":"),
                                    )
                                )
                                for record in state.active_card_records
                            )
                        )
                    )

            candidate = self._native(state, private_context=private_context)
            all_candidate_calls = [
                {
                    "call_id": str(getattr(call, "id", "") or ""),
                    "tool_name": str(getattr(call, "name", "") or ""),
                    "arguments": dict(
                        getattr(call, "arguments", None) or {}
                    ),
                }
                for call in _calls(candidate)
            ]
            linkage = (
                candidate_linkage_impl(
                    state.active_card_records,
                    all_candidate_calls,
                )
                if injected_card_id is not None
                and candidate_linkage_impl is not None
                else None
            )
            if (
                injected_card_id is not None
                and candidate_linkage_impl is not None
            ):
                state.intervention.ledger.record(
                    "A",
                    "LINKAGE",
                    "A_CARD_REACHED_NATIVE_DECISION",
                    state_revision=visible.revision,
                    card_id=injected_card_id,
                    card_sha256=(
                        _sha(state.active_card.content)
                        if state.active_card is not None
                        else None
                    ),
                    native_action_type=(
                        "tool_candidate"
                        if all_candidate_calls
                        else "text_response"
                    ),
                    candidate_calls=all_candidate_calls,
                    **(linkage or {}),
                )
            candidate_writes = _write_calls(candidate)
            if injected_card_id is not None and candidate_writes:
                state.intervention.ledger.record(
                    "A",
                    "LINKAGE",
                    "A_CARD_REACHED_WRITE_CANDIDATE",
                    state_revision=visible.revision,
                    card_id=injected_card_id,
                    card_sha256=(
                        _sha(state.active_card.content)
                        if state.active_card is not None
                        else None
                    ),
                    candidate_calls=[
                        {
                            "call_id": str(getattr(call, "id", "") or ""),
                            "tool_name": str(
                                getattr(call, "name", "") or ""
                            ),
                            "arguments": dict(
                                getattr(call, "arguments", None) or {}
                            ),
                        }
                        for call in candidate_writes
                    ],
                    **(linkage or {}),
                )
            outgoing = candidate
            governed_hidden: list[Any] = []
            if self.runtime_config.factors.prewrite_control:
                outgoing, governed_hidden = self._govern(
                    state,
                    visible,
                    candidate,
                    semantic_context=private_context,
                )
            if governed_hidden:
                outgoing = _aggregate_usage(outgoing, governed_hidden)
            if hidden:
                outgoing = _aggregate_usage(outgoing, hidden)
            state.messages.append(outgoing)
            return outgoing, state

    return FactorialRetailRuntimeAgent


def create_factorial_retail_runtime_agent(**kwargs: Any):
    """Tau registry factory with explicit nested runtime-kwarg handling."""

    from support.runtime_config import (
        split_agent_runtime_kwargs,
    )
    from artifact.shared.configuration import (
        load_frozen_configuration,
    )

    kwargs.pop("task", None)
    llm_args, agent_kwargs = split_agent_runtime_kwargs(kwargs.get("llm_args"))
    kwargs["llm_args"] = llm_args
    kwargs.update(agent_kwargs)
    condition = str(kwargs.get("condition") or "C0_NATIVE")
    kwargs["runtime_config"] = kwargs.get(
        "runtime_config"
    ) or load_frozen_configuration(condition)
    return create_factorial_retail_runtime_agent_class()(**kwargs)
