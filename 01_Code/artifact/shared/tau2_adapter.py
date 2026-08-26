"""Domain-neutral Tau2 adapter for the modular intervention runtime."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from artifact.shared.configuration import (
    FrozenRuntimeConfiguration,
    load_frozen_configuration,
)
from artifact.shared.contracts import (
    PreWriteDecision,
    PreWriteDisposition,
    SemanticDisposition,
    ToolAction,
)
from artifact.shared.domain import (
    DomainRuntimeBindings,
)
from artifact.shared.orchestrator import (
    InterventionState,
    RuntimeInterventionOrchestrator,
)
from artifact.shared.visible_trace import (
    message_role,
)

RUNTIME_SCHEMA_VERSION = "modular_runtime_intervention_runtime_v3"
SEMANTIC_SYSTEM_INSTRUCTION = (
    "You are a schema-constrained, source-grounded goal extractor. "
    "You have no action authority."
)
NATIVE_AGENT_INSTRUCTION = """
You are a customer service agent that helps the user according to the <policy> provided below.
In each turn you can either:
- Send a message to the user.
- Make a tool call.
You cannot do both at the same time.

Try to be helpful and always follow the policy. Always make sure you generate valid JSON only.
""".strip()
NATIVE_SYSTEM_PROMPT = """
<instructions>
{agent_instruction}
</instructions>
<policy>
{domain_policy}
</policy>
""".strip()


@dataclass(slots=True)
class RuntimeInterventionState:
    domain: str
    condition: str
    system_messages: list[Any]
    messages: list[Any]
    intervention: InterventionState
    native_cost_usd: float = 0.0
    semantic_cost_usd: float = 0.0
    native_seconds: float = 0.0
    semantic_seconds: float = 0.0
    prewrite_seconds: float = 0.0
    _orchestrator: RuntimeInterventionOrchestrator | None = field(
        default=None,
        repr=False,
    )
    _runtime_config: FrozenRuntimeConfiguration | None = field(
        default=None,
        repr=False,
    )
    _bindings: DomainRuntimeBindings | None = field(default=None, repr=False)


def _message_usage(message: Any) -> tuple[float, float]:
    return (
        float(getattr(message, "cost", None) or 0.0),
        float(getattr(message, "generation_time_seconds", None) or 0.0),
    )


def _trace_value(value: Any) -> Any:
    dumper = getattr(value, "model_dump", None)
    if callable(dumper):
        return dumper(mode="json")
    if isinstance(value, dict):
        return {str(key): _trace_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_trace_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return {
        "name": str(getattr(value, "name", "") or type(value).__name__),
        "description": str(getattr(value, "description", "") or ""),
    }


def _trace_message(message: Any, index: int | None = None) -> dict[str, Any]:
    raw = _trace_value(message)
    if not isinstance(raw, dict):
        raw = {"value": raw}
    return {
        **({"index": index} if index is not None else {}),
        "role": str(raw.get("role") or getattr(message, "role", "") or ""),
        "content": raw.get("content", getattr(message, "content", None)),
        "tool_calls": raw.get("tool_calls", getattr(message, "tool_calls", None)),
        "cost": raw.get("cost", getattr(message, "cost", None)),
        "generation_time_seconds": raw.get(
            "generation_time_seconds",
            getattr(message, "generation_time_seconds", None),
        ),
    }


def model_visible_request(
    *,
    model: str,
    messages: list[Any],
    tools: list[Any] | None,
    llm_args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Mirror the payload Tau converts and passes to LiteLLM."""

    from tau2.utils import llm_utils

    tool_schemas = (
        [
            _trace_value(getattr(tool, "schema", getattr(tool, "open" + "ai_schema")))
            if hasattr(tool, "schema") or hasattr(tool, "open" + "ai_schema")
            else _trace_value(tool)
            for tool in tools
        ]
        if tools
        else None
    )
    parameters = dict(llm_args or {})
    if parameters.get("num_retries") is None:
        parameters["num_retries"] = llm_utils.DEFAULT_MAX_RETRIES
    # Credentials are transport configuration, not model-visible input.
    parameters = {
        key: _trace_value(value)
        for key, value in parameters.items()
        if not any(marker in key.casefold() for marker in ("api_key", "token", "secret"))
    }
    return {
        "model": model,
        "messages": llm_utils.to_litellm_messages(messages),
        "tools": tool_schemas,
        "tool_choice": "auto" if tool_schemas else None,
        "parameters": parameters,
    }


def model_visible_response(message: Any) -> Any:
    """Prefer the provider response retained by Tau over a reconstruction."""

    raw = getattr(message, "raw_data", None)
    return _trace_value(raw) if raw is not None else _trace_message(message)


def _with_aggregated_usage(message: Any, hidden: list[Any]) -> Any:
    cost, seconds = _message_usage(message)
    for item in hidden:
        item_cost, item_seconds = _message_usage(item)
        cost += item_cost
        seconds += item_seconds
    updates = {"cost": cost, "generation_time_seconds": seconds}
    if hasattr(message, "model_copy"):
        return message.model_copy(update=updates)
    for key, value in updates.items():
        setattr(message, key, value)
    return message


def _single_call(message: Any) -> Any | None:
    calls = list(getattr(message, "tool_calls", None) or [])
    return calls[0] if len(calls) == 1 else None


def _call_id(call: Any) -> str:
    return str(getattr(call, "id", "") or "")


def _action(call: Any) -> ToolAction:
    return ToolAction(
        tool_name=str(getattr(call, "name", "")),
        arguments=dict(getattr(call, "arguments", None) or {}),
    )


def runtime_record(state: RuntimeInterventionState) -> dict[str, Any]:
    """Return a complete JSON-serialisable mechanism record."""

    if state._bindings is None:
        raise ValueError("runtime state has no domain bindings")
    visible = state._bindings.project_visible_state(state.messages)
    orchestrator = state._orchestrator
    if orchestrator is not None:
        orchestrator.close_pending_at_termination(
            state.intervention,
            visible.revision,
        )
    audit = state.intervention.ledger.audit()
    config = state._runtime_config
    factors = (
        {
            "semantic_support": config.factors.semantic_support,
            "prewrite_control": config.factors.prewrite_control,
        }
        if config is not None
        else {}
    )
    return {
        "schema_version": RUNTIME_SCHEMA_VERSION,
        "domain": state.domain,
        "condition": state.condition,
        "factors": factors,
        "counts": {
            "a_opportunities": state.intervention.a_opportunities,
            "a_extractions": state.intervention.a_extractions,
            "a_evidence_reads": state.intervention.a_evidence_reads,
            "a_support_cards": state.intervention.a_support_cards,
            "b_opportunities": state.intervention.b_opportunities,
            "b_evidence_reads": state.intervention.b_evidence_reads,
            "b_confirmation_cycles": state.intervention.b_confirmation_cycles,
            "b_transfers": state.intervention.b_transfers,
        },
        "cost_usd": {
            "native_agent": state.native_cost_usd,
            "semantic_support": state.semantic_cost_usd,
            "prewrite_control": 0.0,
        },
        "seconds": {
            "native_agent": state.native_seconds,
            "semantic_support": state.semantic_seconds,
            "prewrite_control": state.prewrite_seconds,
        },
        "budgets": (
            {
                "module_a": {
                    key: getattr(config.module_a, key)
                    for key in config.module_a.__dataclass_fields__
                },
                "module_b": {
                    key: getattr(config.module_b, key)
                    for key in config.module_b.__dataclass_fields__
                },
            }
            if config is not None
            else {}
        ),
        "goals": [
            {
                "goal_id": goal.goal_id,
                "revision": goal.revision,
                "kind": goal.kind.value,
                "status": goal.status.value,
                "depends_on": list(goal.depends_on),
                "fields": {
                    key: {
                        "value": field.value,
                        "source_event_ids": list(field.source_event_ids),
                    }
                    for key, field in goal.fields.items()
                },
            }
            for goal in state.intervention.goals
        ],
        "events": state.intervention.ledger.serialise(),
        "observer_audit": audit,
    }


def create_runtime_intervention_agent_class(
    bindings: DomainRuntimeBindings,
):
    """Create the single Tau agent class used by C0, C1, C2, and C3."""

    from tau2.agent.base_agent import HalfDuplexAgent, ValidAgentInputMessage
    from tau2.data_model.message import (
        AssistantMessage,
        Message,
        MultiToolMessage,
        SystemMessage,
        ToolCall,
        UserMessage,
    )
    from tau2.environment.toolkit import Tool
    from tau2.utils import llm_utils

    class RuntimeInterventionAgent(
        HalfDuplexAgent[RuntimeInterventionState]
    ):
        def __init__(
            self,
            tools: list[Tool],
            domain_policy: str,
            llm: str,
            llm_args: Optional[dict[str, Any]] = None,
            condition: str = "C0_NATIVE",
            runtime_config: FrozenRuntimeConfiguration | None = None,
            generate_fn: Any | None = None,
            semantic_generate_fn: Any | None = None,
            **_: Any,
        ) -> None:
            super().__init__(tools=tools, domain_policy=domain_policy)
            self.runtime_config = runtime_config or load_frozen_configuration(
                condition
            )
            if self.runtime_config.condition != condition:
                raise ValueError("runtime config and condition differ")
            if llm != self.runtime_config.agent_model:
                raise ValueError(
                    "native agent model differs from the frozen configuration"
                )
            self.condition = condition
            self.llm = llm
            self.semantic_llm = str(
                self.runtime_config.base["module_a"]["model"]
            )
            self.llm_args = dict(llm_args or {})
            temperature = self.llm_args.setdefault(
                "temperature",
                self.runtime_config.temperature,
            )
            reasoning = self.llm_args.setdefault(
                "reasoning_effort",
                self.runtime_config.reasoning_effort,
            )
            if float(temperature) != self.runtime_config.temperature:
                raise ValueError("temperature differs from frozen configuration")
            if str(reasoning) != self.runtime_config.reasoning_effort:
                raise ValueError(
                    "reasoning effort differs from frozen configuration"
                )
            self.generate_fn = generate_fn or llm_utils.generate
            self.semantic_generate_fn = semantic_generate_fn or self.generate_fn
            self.orchestrator = RuntimeInterventionOrchestrator(
                self.runtime_config,
                bindings,
            )
            self.system_prompt = NATIVE_SYSTEM_PROMPT.format(
                agent_instruction=NATIVE_AGENT_INSTRUCTION,
                domain_policy=domain_policy,
            )
            self.tool_names = {str(tool.name) for tool in tools}

        def set_seed(self, seed: int) -> None:
            self.llm_args["seed"] = seed

        def get_init_state(
            self,
            message_history: Optional[list[Message]] = None,
        ) -> RuntimeInterventionState:
            state = RuntimeInterventionState(
                domain=bindings.name,
                condition=self.condition,
                system_messages=[
                    SystemMessage(role="system", content=self.system_prompt)
                ],
                messages=list(message_history or []),
                intervention=self.orchestrator.new_state(),
            )
            # These private references support a self-contained runtime record
            # without exposing tasks, rewards, or evaluator objects.
            state._orchestrator = self.orchestrator
            state._runtime_config = self.runtime_config
            state._bindings = bindings
            return state

        def _native(
            self,
            state: RuntimeInterventionState,
            *,
            private_context: str | None = None,
        ) -> Any:
            extra = (
                [
                    SystemMessage(
                        role="system",
                        content=(
                            "<private_source_grounded_support>\n"
                            f"{private_context}\n"
                            "</private_source_grounded_support>"
                        ),
                    )
                ]
                if private_context
                else []
            )
            request_messages = state.system_messages + state.messages + extra
            native_call_number = 1 + sum(
                event.component == "N" and event.reason_code == "N_NATIVE_REQUEST"
                for event in state.intervention.ledger.events
            )
            native_call_id = f"N-{native_call_number:04d}"
            visible = (
                state._bindings.project_visible_state(state.messages)
                if state._bindings is not None
                else None
            )
            source_event_ids = (
                list(visible.visible_user_event_ids[-1:])
                if visible is not None
                else []
            )
            state.intervention.ledger.record(
                "N",
                "REQUEST",
                "N_NATIVE_REQUEST",
                opportunity_id=native_call_id,
                state_revision=len(state.messages),
                source_event_ids=source_event_ids,
                model_request=model_visible_request(
                    model=self.llm,
                    messages=request_messages,
                    tools=self.tools,
                    llm_args=self.llm_args,
                ),
            )
            response = self.generate_fn(
                model=self.llm,
                tools=self.tools,
                messages=request_messages,
                call_name="agent_response",
                **self.llm_args,
            )
            cost, seconds = _message_usage(response)
            state.native_cost_usd += cost
            state.native_seconds += seconds
            state.intervention.ledger.record(
                "N",
                "RESPONSE",
                "N_NATIVE_RESPONSE",
                opportunity_id=native_call_id,
                state_revision=len(state.messages),
                source_event_ids=source_event_ids,
                model_response=model_visible_response(response),
                response=_trace_message(response),
                cost_usd=cost,
                seconds=seconds,
            )
            return response

        def _extract(
            self,
            state: RuntimeInterventionState,
            visible: Any,
            opportunity_id: str,
        ) -> tuple[list[dict[str, Any]] | None, Any | None, str | None]:
            prompt = bindings.goal_extractor_prompt(
                visible,
                state.intervention.goals,
            )
            semantic_messages = [
                SystemMessage(
                    role="system",
                    content=SEMANTIC_SYSTEM_INSTRUCTION,
                ),
                UserMessage(role="user", content=prompt),
            ]
            response = None
            state.intervention.ledger.record(
                "A",
                "REQUEST",
                "A_EXTRACTION_REQUEST",
                opportunity_id=opportunity_id,
                state_revision=visible.revision,
                model_request=model_visible_request(
                    model=self.semantic_llm,
                    messages=semantic_messages,
                    tools=[],
                    llm_args=self.llm_args,
                ),
                # Retained as a mechanism-audit convenience; Phoenix uses the
                # exact model_request above for the LLM input view.
                system_instruction=SEMANTIC_SYSTEM_INSTRUCTION,
                prompt=prompt,
                prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
            )
            try:
                started = time.perf_counter()
                response = self.semantic_generate_fn(
                    model=self.semantic_llm,
                    tools=[],
                    messages=semantic_messages,
                    call_name="runtime_semantic_support",
                    **self.llm_args,
                )
                measured = time.perf_counter() - started
                cost, reported_seconds = _message_usage(response)
                seconds = reported_seconds or measured
                state.semantic_cost_usd += cost
                state.semantic_seconds += seconds
                state.intervention.ledger.record(
                    "A",
                    "COST",
                    "A_EXTRACTION_USAGE",
                    opportunity_id=opportunity_id,
                    state_revision=visible.revision,
                    cost_usd=cost,
                    seconds=seconds,
                )
                raw_content = str(getattr(response, "content", "") or "")
                payload = json.loads(raw_content)
                proposals = payload.get("goals") if isinstance(payload, dict) else None
                if not isinstance(proposals, list):
                    raise ValueError("semantic output must contain a goals list")
                state.intervention.ledger.record(
                    "A",
                    "RESPONSE",
                    "A_EXTRACTION_RESPONSE_PARSED",
                    opportunity_id=opportunity_id,
                    state_revision=visible.revision,
                    raw_content=raw_content,
                    model_response=model_visible_response(response),
                    response_sha256=hashlib.sha256(
                        raw_content.encode()
                    ).hexdigest(),
                    top_level_keys=(
                        sorted(str(key) for key in payload)
                        if isinstance(payload, dict)
                        else []
                    ),
                    proposal_count=len(proposals),
                )
                return proposals, response, None
            except Exception as exc:  # fail-open is part of the frozen A contract
                raw_content = (
                    str(getattr(response, "content", "") or "")
                    if response is not None
                    else ""
                )
                state.intervention.ledger.record(
                    "A",
                    "RESPONSE",
                    "A_EXTRACTION_RESPONSE_INVALID",
                    opportunity_id=opportunity_id,
                    state_revision=visible.revision,
                    raw_content=raw_content,
                    model_response=(
                        model_visible_response(response)
                        if response is not None
                        else None
                    ),
                    response_sha256=hashlib.sha256(
                        raw_content.encode()
                    ).hexdigest(),
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                return None, response, f"{type(exc).__name__}: {exc}"

        def _tool_message(
            self,
            state: RuntimeInterventionState,
            action: ToolAction,
            *,
            prefix: str,
        ) -> Any:
            if action.tool_name not in self.tool_names:
                raise ValueError(
                    f"intervention references unavailable tool {action.tool_name}"
                )
            call_id = (
                f"{prefix}_{len(state.messages)}_"
                f"{len(state.intervention.ledger.events)}"
            )
            return AssistantMessage(
                role="assistant",
                content=None,
                tool_calls=[
                    ToolCall(
                        id=call_id,
                        name=action.tool_name,
                        arguments=action.arguments,
                        requestor="assistant",
                    )
                ],
            )

        def _emit_transfer(
            self,
            state: RuntimeInterventionState,
            decision: PreWriteDecision,
        ) -> Any:
            if bindings.transfer_tool not in self.tool_names:
                return AssistantMessage.text(
                    "I cannot safely complete that action within the "
                    "intervention budget."
                )
            return self._tool_message(
                state,
                ToolAction(
                    bindings.transfer_tool,
                    {
                        "summary": (
                            "Pre-write control could not safely release "
                            f"{decision.candidate.tool_name}: "
                            f"{decision.reason_code}"
                        )
                    },
                    decision.candidate.source_event_ids or ("policy",),
                ),
                prefix="mri_transfer",
            )

        def _render_prewrite(
            self,
            state: RuntimeInterventionState,
            visible: Any,
            opportunity_id: str,
            decision: PreWriteDecision,
            *,
            original_candidate: Any | None,
        ) -> Any:
            if decision.disposition == PreWriteDisposition.ALLOW_UNCHANGED:
                outgoing = (
                    original_candidate
                    if original_candidate is not None
                    else self._tool_message(
                        state,
                        decision.candidate,
                        prefix="mri_write",
                    )
                )
                call = _single_call(outgoing)
                emitted_id = _call_id(call) if call is not None else ""
                self.orchestrator.record_action_emitted(
                    state.intervention,
                    visible,
                    opportunity_id=opportunity_id,
                    action=decision.candidate,
                    emitted_call_id=emitted_id,
                    role=(
                        "native_candidate_write"
                        if original_candidate is not None
                        else "revalidated_candidate_write"
                    ),
                )
                self.orchestrator.record_final_disposition(
                    state.intervention,
                    visible,
                    opportunity_id=opportunity_id,
                    disposition="executed_unchanged",
                    reason_code=decision.reason_code,
                    emitted_call_id=emitted_id,
                )
                return outgoing
            if decision.disposition == PreWriteDisposition.REQUEST_EVIDENCE:
                return self._tool_message(
                    state,
                    decision.evidence_action,
                    prefix="mri_b_read",
                )
            if decision.disposition == PreWriteDisposition.REQUEST_CONFIRMATION:
                return AssistantMessage.text(
                    decision.confirmation_ticket.message
                )
            if decision.disposition == PreWriteDisposition.TRANSFER:
                outgoing = self._emit_transfer(state, decision)
                call = _single_call(outgoing)
                emitted_id = _call_id(call) if call is not None else None
                self.orchestrator.record_final_disposition(
                    state.intervention,
                    visible,
                    opportunity_id=opportunity_id,
                    disposition=(
                        "transferred"
                        if emitted_id is not None
                        else "blocked_transfer_unavailable"
                    ),
                    reason_code=decision.reason_code,
                    emitted_call_id=emitted_id,
                )
                return outgoing
            outgoing = AssistantMessage.text(
                f"I cannot execute that action: {decision.reason_code}."
            )
            self.orchestrator.record_final_disposition(
                state.intervention,
                visible,
                opportunity_id=opportunity_id,
                disposition="blocked",
                reason_code=decision.reason_code,
            )
            return outgoing

        def _govern_candidate(
            self,
            state: RuntimeInterventionState,
            visible: Any,
            candidate: Any,
        ) -> Any:
            calls = list(getattr(candidate, "tool_calls", None) or [])
            write_calls = [
                call
                for call in calls
                if str(getattr(call, "name", "")) in bindings.write_tools
            ]
            if not write_calls:
                return candidate
            if (
                not self.runtime_config.factors.prewrite_control
                and len(write_calls) > 1
            ):
                for call in write_calls:
                    started = time.perf_counter()
                    opportunity_id, decision = (
                        self.orchestrator.evaluate_candidate(
                            state.intervention,
                            visible,
                            _action(call),
                            original_call_id=_call_id(call),
                        )
                    )
                    state.prewrite_seconds += time.perf_counter() - started
                    self.orchestrator.record_action_emitted(
                        state.intervention,
                        visible,
                        opportunity_id=opportunity_id,
                        action=decision.candidate,
                        emitted_call_id=_call_id(call),
                        role="native_candidate_write",
                    )
                    self.orchestrator.record_final_disposition(
                        state.intervention,
                        visible,
                        opportunity_id=opportunity_id,
                        disposition="executed_unchanged",
                        reason_code=decision.reason_code,
                        emitted_call_id=_call_id(call),
                    )
                return candidate
            if (
                self.runtime_config.factors.prewrite_control
                and len(calls) != 1
            ):
                for call in write_calls:
                    opportunity_id, decision = (
                        self.orchestrator.reject_invalid_message_shape(
                            state.intervention,
                            visible,
                            _action(call),
                            original_call_id=_call_id(call),
                            tool_call_count=len(calls),
                        )
                    )
                    self.orchestrator.record_final_disposition(
                        state.intervention,
                        visible,
                        opportunity_id=opportunity_id,
                        disposition="blocked_invalid_message_shape",
                        reason_code=decision.reason_code,
                    )
                return AssistantMessage.text(
                    "I cannot execute multiple or mixed actions in one "
                    "transactional step."
                )
            call = write_calls[0]
            started = time.perf_counter()
            opportunity_id, decision = self.orchestrator.evaluate_candidate(
                state.intervention,
                visible,
                _action(call),
                original_call_id=_call_id(call),
            )
            state.prewrite_seconds += time.perf_counter() - started
            return self._render_prewrite(
                state,
                visible,
                opportunity_id,
                decision,
                original_candidate=candidate,
            )

        def _resume_prewrite(
            self,
            state: RuntimeInterventionState,
            visible: Any,
            incoming: Any,
        ) -> Any | None:
            pending = state.intervention.pending_prewrite
            if pending is None:
                return None
            if pending.confirmation_ticket is not None:
                if not isinstance(incoming, UserMessage):
                    return None
                source_id = (
                    visible.visible_user_event_ids[-1]
                    if visible.visible_user_event_ids
                    else ""
                )
                resumed = self.orchestrator.resume_after_confirmation(
                    state.intervention,
                    visible,
                    user_text=str(incoming.content or ""),
                    user_event_id=source_id,
                )
            else:
                if message_role(incoming) != "tool":
                    return None
                resumed = self.orchestrator.resume_after_evidence(
                    state.intervention,
                    visible,
                )
            if resumed is None:
                return None
            opportunity_id, decision = resumed
            return self._render_prewrite(
                state,
                visible,
                opportunity_id,
                decision,
                original_candidate=None,
            )

        def generate_next_message(
            self,
            message: ValidAgentInputMessage,
            state: RuntimeInterventionState,
        ):
            if isinstance(message, MultiToolMessage):
                state.messages.extend(message.tool_messages)
            else:
                state.messages.append(message)
            visible = bindings.project_visible_state(state.messages)
            self.orchestrator.reconcile_goals(state.intervention, visible)

            pending = state.intervention.pending_prewrite
            is_confirmation_response = bool(
                pending is not None
                and pending.confirmation_ticket is not None
                and isinstance(message, UserMessage)
                and bindings.is_explicit_confirmation_response(
                    str(message.content or "")
                )
            )
            is_confirmation_revision = bool(
                pending is not None
                and pending.confirmation_ticket is not None
                and isinstance(message, UserMessage)
                and not is_confirmation_response
            )
            if is_confirmation_response:
                source_id = (
                    visible.visible_user_event_ids[-1]
                    if visible.visible_user_event_ids
                    else ""
                )
                self.orchestrator.start_semantic_opportunity(
                    state.intervention,
                    visible,
                    source_event_id=source_id,
                    skip_reason="B_CONFIRMATION_RESPONSE",
                )
            if is_confirmation_revision:
                invalidated = self.orchestrator.resume_after_confirmation(
                    state.intervention,
                    visible,
                    user_text=str(message.content or ""),
                    user_event_id=(
                        visible.visible_user_event_ids[-1]
                        if visible.visible_user_event_ids
                        else ""
                    ),
                )
                if invalidated is not None:
                    opportunity_id, decision = invalidated
                    self.orchestrator.record_final_disposition(
                        state.intervention,
                        visible,
                        opportunity_id=opportunity_id,
                        disposition="invalidated_by_user_revision",
                        reason_code=decision.reason_code,
                    )
            resumed = self._resume_prewrite(state, visible, message)
            if resumed is not None:
                state.messages.append(resumed)
                return resumed, state

            hidden_usage: list[Any] = []
            private_context: str | None = None
            if isinstance(message, UserMessage) and not is_confirmation_response:
                source_id = (
                    visible.visible_user_event_ids[-1]
                    if visible.visible_user_event_ids
                    else ""
                )
                opportunity = self.orchestrator.start_semantic_opportunity(
                    state.intervention,
                    visible,
                    source_event_id=source_id,
                )
                proposals = None
                extraction_response = None
                extraction_error = None
                if opportunity.should_extract:
                    (
                        proposals,
                        extraction_response,
                        extraction_error,
                    ) = self._extract(
                        state,
                        visible,
                        opportunity.opportunity_id,
                    )
                    if extraction_response is not None:
                        hidden_usage.append(extraction_response)
                semantic = self.orchestrator.complete_semantic_opportunity(
                    state.intervention,
                    visible,
                    opportunity,
                    proposals=proposals,
                    extraction_error=extraction_error,
                )
                if semantic.disposition == SemanticDisposition.REQUEST_READ:
                    outgoing = self._tool_message(
                        state,
                        semantic.action,
                        prefix="mri_a_read",
                    )
                    if hidden_usage:
                        outgoing = _with_aggregated_usage(
                            outgoing,
                            hidden_usage,
                        )
                    state.messages.append(outgoing)
                    return outgoing, state
                if semantic.card is not None:
                    private_context = semantic.card.content
            elif state.intervention.pending_semantic_opportunity_id is not None:
                semantic = self.orchestrator.complete_semantic_after_read(
                    state.intervention,
                    visible,
                )
                if semantic is not None and semantic.card is not None:
                    private_context = semantic.card.content

            candidate = self._native(
                state,
                private_context=private_context,
            )
            governed = self._govern_candidate(state, visible, candidate)
            outgoing = governed
            if governed is not candidate:
                outgoing = _with_aggregated_usage(outgoing, [candidate])
            if hidden_usage:
                outgoing = _with_aggregated_usage(outgoing, hidden_usage)
            state.messages.append(outgoing)
            return outgoing, state

    return RuntimeInterventionAgent


def create_runtime_intervention_agent(
    bindings: DomainRuntimeBindings,
    **kwargs: Any,
):
    """Tau registry factory that explicitly discards evaluator task objects."""

    from support.runtime_config import (
        split_agent_runtime_kwargs,
    )

    kwargs.pop("task", None)
    llm_args, agent_kwargs = split_agent_runtime_kwargs(kwargs.get("llm_args"))
    kwargs["llm_args"] = llm_args
    kwargs.update(agent_kwargs)
    condition = str(kwargs.get("condition") or "C0_NATIVE")
    kwargs["runtime_config"] = kwargs.get(
        "runtime_config"
    ) or load_frozen_configuration(condition)
    return create_runtime_intervention_agent_class(bindings)(**kwargs)
