from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from types import SimpleNamespace

from artifact.factorial.contracts import (
    FeasibilityDisposition,
)
from artifact.factorial.prewrite_validation import (
    evaluate_bundle,
    evaluate_write,
    explain_evaluation,
)
from artifact.factorial.semantic_support import (
    build_support_card,
    merge_commitments,
)
from artifact.factorial.tau2_adapter import (
    create_factorial_retail_runtime_agent,
    create_factorial_retail_runtime_agent_class,
    factorial_runtime_record,
)
from artifact.factorial.semantic_support import (
    is_transaction_request_text,
    parse_snapshot_records,
    snapshot_prompt,
)
from artifact.shared.contracts import (
    GroundedField,
    VisibleProcessState,
)
from artifact.shared.configuration import (
    load_frozen_configuration,
)


TOOL_NAMES = (
    "find_user_id_by_email",
    "get_user_details",
    "get_order_details",
    "get_product_details",
    "cancel_pending_order",
    "modify_pending_order_address",
    "modify_pending_order_items",
    "modify_pending_order_payment",
    "modify_user_address",
    "return_delivered_order_items",
    "exchange_delivered_order_items",
    "transfer_to_human_agents",
)
TOOLS = [SimpleNamespace(name=name) for name in TOOL_NAMES]


def _config(condition: str):
    config = load_frozen_configuration(condition)
    base = deepcopy(config.base)
    base["module_a"]["model"] = "test"
    return replace(config, agent_model="test", base=base)


def _assistant_calls(*rows):
    from tau2.data_model.message import AssistantMessage, ToolCall

    return AssistantMessage(
        role="assistant",
        content=None,
        tool_calls=[
            ToolCall(
                id=call_id,
                name=name,
                arguments=arguments,
                requestor="assistant",
            )
            for call_id, name, arguments in rows
        ],
        cost=0.01,
    )


def _tool_result(call_id: str, result):
    from tau2.data_model.message import ToolMessage

    return ToolMessage(
        id=call_id,
        role="tool",
        requestor="assistant",
        content=json.dumps(result),
        error=False,
    )


def _call(call_id: str, name: str, arguments: dict):
    return SimpleNamespace(id=call_id, name=name, arguments=arguments)


def _state(*, status: str = "pending") -> VisibleProcessState:
    return VisibleProcessState(
        revision=4,
        authenticated_user_id=GroundedField("u1", ("auth",)),
        user_utterances=(
            GroundedField(
                "Please cancel order #P because I ordered it by mistake.",
                ("user-request",),
            ),
        ),
        users={
            "u1": GroundedField(
                {
                    "user_id": "u1",
                    "payment_methods": {
                        "card-1": {"source": "card", "balance": 999}
                    },
                },
                ("user",),
            )
        },
        orders={
            "#P": GroundedField(
                {
                    "order_id": "#P",
                    "user_id": "u1",
                    "status": status,
                    "items": [],
                    "payment_history": [],
                },
                ("order",),
            )
        },
    )


def test_a_card_is_one_turn_advice_from_validated_sources_only():
    state = _state()
    proposals, rejected = parse_snapshot_records(
        state,
        [
            {
                "kind": "cancel_pending_order",
                "fields": {
                    "order_id": {
                        "value": "#P",
                        "source_event_ids": ["user-request"],
                    },
                    "reason": {
                        "value": "ordered it by mistake",
                        "source_event_ids": ["user-request"],
                    },
                },
            },
            {
                "kind": "cancel_pending_order",
                "fields": {
                    "order_id": {
                        "value": "#GOLD",
                        "source_event_ids": ["user-request"],
                    }
                },
                "goal_id": "model-owned-id",
            },
        ],
    )
    assert len(proposals) == 1
    assert len(rejected) == 1
    card = build_support_card(proposals)
    assert card is not None
    assert card.accepted_records == 1
    assert card.source_event_ids == ("user-request",)
    assert "#P" in card.content
    assert "#GOLD" not in card.content
    assert build_support_card(()) is None


def test_return_descriptions_are_grounded_but_completion_thanks_do_not_trigger():
    state = VisibleProcessState(
        user_utterances=(
            GroundedField(
                "I want to return a cleaner, a headphone, and a smart watch.",
                ("request",),
            ),
        )
    )
    accepted, rejected = parse_snapshot_records(
        state,
        [
            {
                "kind": "return_delivered_order_items",
                "fields": {
                    "item_descriptions": {
                        "value": ["a cleaner", "a headphone", "a smart watch"],
                        "source_event_ids": ["request"],
                    }
                },
            }
        ],
    )
    assert not rejected
    assert accepted[0].fields["item_descriptions"].value == [
        "a cleaner",
        "a headphone",
        "a smart watch",
    ]
    assert is_transaction_request_text(
        "I want to return a cleaner and a smart watch."
    )


def test_incremental_extraction_keeps_only_latest_user_event_and_relations():
    state = VisibleProcessState(
        user_utterances=(
            GroundedField("Old request to cancel order #OLD.", ("message:0:user",)),
            GroundedField(
                "Use the Washington address already used by one pending order "
                "for all pending orders and my default address.",
                ("message:2:user",),
            ),
        )
    )
    prompt = snapshot_prompt(state)
    assert "#OLD" not in prompt
    assert "Washington address" in prompt
    accepted, rejected = parse_snapshot_records(
        state,
        [
            {
                "kind": "modify_pending_order_address",
                "fields": {
                    "scope": {
                        "value": "all pending orders",
                        "source_event_ids": ["message:2:user"],
                    },
                    "address_reference": {
                        "value": "the Washington address already used by one pending order",
                        "source_event_ids": ["message:2:user"],
                    },
                },
            },
            {
                "kind": "modify_user_address",
                "fields": {
                    "address_reference": {
                        "value": "the Washington address already used by one pending order",
                        "source_event_ids": ["message:2:user"],
                    }
                },
            },
        ],
    )
    assert not rejected
    assert len(accepted) == 2


def test_commitment_merge_deduplicates_rephrasing_and_adds_new_binding():
    state = VisibleProcessState(
        user_utterances=(
            GroundedField("Return a smart watch.", ("message:0:user",)),
            GroundedField(
                "Return the watch from order #W1.", ("message:2:user",)
            ),
        )
    )
    first, _ = parse_snapshot_records(
        state,
        [
            {
                "kind": "return_delivered_order_items",
                "fields": {
                    "item_descriptions": {
                        "value": "a smart watch",
                        "source_event_ids": ["message:0:user"],
                    }
                },
            }
        ],
    )
    ledger, changed = merge_commitments((), first, revision=1)
    assert len(ledger) == len(changed) == 1
    second, _ = parse_snapshot_records(
        state,
        [
            {
                "kind": "return_delivered_order_items",
                "fields": {
                    "item_descriptions": {
                        "value": "the watch",
                        "source_event_ids": ["message:2:user"],
                    },
                    "order_id": {
                        "value": "#W1",
                        "source_event_ids": ["message:2:user"],
                    },
                },
            }
        ],
    )
    ledger, changed = merge_commitments(ledger, second, revision=3)
    assert len(ledger) == 1
    assert len(changed) == 1
    assert ledger[0].commitment_id == "G-0001"
    assert ledger[0].proposal.fields["order_id"].value == "#W1"


def test_b_does_not_reclassify_post_item_modification_as_pending():
    call = _call(
        "w1",
        "cancel_pending_order",
        {"order_id": "#P", "reason": "ordered by mistake"},
    )
    for status in ("pending (items modifed)", "pending (item modified)"):
        result = evaluate_write(_state(status=status), call, enabled=True)
        assert result.disposition == FeasibilityDisposition.INVALID
        assert result.reason_code == "B_INELIGIBLE_STATUS"


def test_b_validity_is_feasibility_not_a_second_confirmation_dialogue():
    result = evaluate_write(
        _state(),
        _call(
            "w1",
            "cancel_pending_order",
            {"order_id": "#P", "reason": "ordered by mistake"},
        ),
        enabled=True,
    )
    assert result.disposition == FeasibilityDisposition.VALID_UNCHANGED
    assert result.reason_code == "B_FEASIBILITY_VALID_CONFIRMATION_NATIVE_SCOPE"


def test_b_bundle_form_and_order_do_not_change_call_level_decisions():
    valid = _call(
        "w1",
        "cancel_pending_order",
        {"order_id": "#P", "reason": "ordered by mistake"},
    )
    read = _call("r1", "get_order_details", {"order_id": "#P"})
    first = evaluate_bundle(
        _state(), (valid, read), enabled=True, bundle_id="b1"
    )
    second = evaluate_bundle(
        _state(), (read, deepcopy(valid)), enabled=True, bundle_id="b2"
    )
    assert first.valid and second.valid
    assert first.tool_call_count == second.tool_call_count == 2
    assert first.write_evaluations[0].action == second.write_evaluations[0].action


def test_b_disabled_is_explicit_pass_through():
    result = evaluate_write(
        _state(status="cancelled"),
        _call(
            "w1",
            "cancel_pending_order",
            {"order_id": "#P", "reason": "invalid"},
        ),
        enabled=False,
    )
    assert result.disposition == FeasibilityDisposition.VALID_UNCHANGED
    assert result.reason_code == "B_DISABLED_PASS_THROUGH"


def test_b_trace_exposes_candidate_and_visible_evidence_for_independent_audit():
    visible = VisibleProcessState(
        revision=5,
        authenticated_user_id=GroundedField("u1", ("auth-event",)),
        users={
            "u1": GroundedField(
                {
                    "user_id": "u1",
                    "payment_methods": {
                        "gift-1": {"source": "gift_card", "balance": 50.0}
                    },
                },
                ("user-read",),
            )
        },
        orders={
            "#P": GroundedField(
                {
                    "order_id": "#P",
                    "user_id": "u1",
                    "status": "pending",
                    "items": [
                        {
                            "item_id": "old",
                            "product_id": "p1",
                            "price": 10.0,
                        }
                    ],
                    "payment_history": [
                        {
                            "transaction_type": "payment",
                            "payment_method_id": "card-1",
                            "amount": 10.0,
                        }
                    ],
                },
                ("order-read",),
            )
        },
        products={
            "p1": GroundedField(
                {
                    "product_id": "p1",
                    "variants": {
                        "new": {
                            "item_id": "new",
                            "available": False,
                            "price": 12.0,
                        }
                    },
                },
                ("product-read",),
            )
        },
    )
    candidate = _call(
        "w1",
        "modify_pending_order_items",
        {
            "order_id": "#P",
            "item_ids": ["old"],
            "new_item_ids": ["new"],
            "payment_method_id": "gift-1",
        },
    )
    result = evaluate_write(visible, candidate, enabled=True)
    trace = explain_evaluation(visible, result)

    assert result.disposition == FeasibilityDisposition.INVALID
    assert result.reason_code == "B_VARIANT_UNAVAILABLE"
    assert trace["candidate_arguments"] == candidate.arguments
    assert trace["observed"]["authentication_source_event_ids"] == [
        "auth-event"
    ]
    assert trace["observed"]["order"]["items"] == [
        {"item_id": "old", "product_id": "p1", "price": 10.0}
    ]
    assert trace["observed"]["order"]["source_event_ids"] == ["order-read"]
    assert trace["observed"]["products"] == [
        {
            "product_id": "p1",
            "observed": True,
            "candidate_variants": [
                {"item_id": "new", "available": False, "price": 12.0}
            ],
            "source_event_ids": ["product-read"],
        }
    ]
    assert trace["observed"]["user_profile"]["candidate_payment_method"] == {
        "payment_method_id": "gift-1",
        "source": "gift_card",
        "balance": 50.0,
    }


def test_b_valid_trace_states_that_native_candidate_remains_unchanged():
    result = evaluate_write(
        _state(),
        _call(
            "w1",
            "cancel_pending_order",
            {"order_id": "#P", "reason": "ordered by mistake"},
        ),
        enabled=True,
    )
    trace = explain_evaluation(_state(), result)
    assert "unchanged native candidate" in trace["required_response"]
    assert "native dialogue policy" in trace["required_response"]


def test_c0_adapter_is_exact_native_object_and_has_no_factor_calls():
    from tau2.data_model.message import UserMessage

    candidate = _assistant_calls(
        (
            "w1",
            "cancel_pending_order",
            {"order_id": "#P", "reason": "ordered by mistake"},
        )
    )
    agent = create_factorial_retail_runtime_agent_class()(
        tools=TOOLS,
        domain_policy="policy",
        llm="test",
        condition="C0_NATIVE",
        runtime_config=_config("C0_NATIVE"),
        generate_fn=lambda **_: candidate,
        semantic_generate_fn=lambda **_: (_ for _ in ()).throw(
            AssertionError("C0 called factor A")
        ),
    )
    outgoing, state = agent.generate_next_message(
        UserMessage.text("Cancel order #P."), agent.get_init_state()
    )
    assert outgoing is candidate
    record = factorial_runtime_record(state)
    assert record["counts"]["a_extractions"] == 0
    assert record["counts"]["b_opportunities"] == 0
    assert record["observer_audit"]["pass"]


def test_registry_factory_applies_nested_condition_instead_of_silent_c0():
    from support.runtime_config import (
        HOMS_AGENT_KWARGS_KEY,
    )

    agent = create_factorial_retail_runtime_agent(
        tools=TOOLS,
        domain_policy="policy",
        llm="gpt-5-nano",
        llm_args={
            "temperature": 0.0,
            "reasoning_effort": "medium",
            HOMS_AGENT_KWARGS_KEY: {
                "condition": "C3_COMBINED_INTERVENTION"
            },
        },
        generate_fn=lambda **_: None,
        semantic_generate_fn=lambda **_: None,
    )
    assert agent.condition == "C3_COMBINED_INTERVENTION"
    assert agent.runtime_config.factors.semantic_support
    assert agent.runtime_config.factors.prewrite_control


def test_c1_simple_commitment_is_stored_but_native_decision_is_untouched():
    from tau2.data_model.message import AssistantMessage, UserMessage

    captured = {}

    def native(**kwargs):
        captured["messages"] = kwargs["messages"]
        return AssistantMessage.text("I can help.", cost=0.01)

    semantic = {
        "goals": [
            {
                "kind": "cancel_pending_order",
                "fields": {
                    "order_id": {
                        "value": "#P",
                        "source_event_ids": ["message:0:user"],
                    }
                },
            }
        ]
    }
    agent = create_factorial_retail_runtime_agent_class()(
        tools=TOOLS,
        domain_policy="policy",
        llm="test",
        condition="C1_SEMANTIC_SUPPORT",
        runtime_config=_config("C1_SEMANTIC_SUPPORT"),
        generate_fn=native,
        semantic_generate_fn=lambda **_: AssistantMessage.text(
            json.dumps(semantic), cost=0.002
        ),
    )
    outgoing, state = agent.generate_next_message(
        UserMessage.text("Cancel order #P."), agent.get_init_state()
    )
    assert outgoing.content == "I can help."
    private = [
        str(message.content or "")
        for message in captured["messages"]
        if "private_source_grounded_support" in str(message.content or "")
    ]
    assert private == []
    record = factorial_runtime_record(state)
    assert record["counts"]["a_commitments"] == 1
    assert record["counts"]["a_support_cards"] == 0
    assert record["counts"]["b_opportunities"] == 0
    assert record["observer_audit"]["pass"]
    decision = next(
        event
        for event in record["events"]
        if event["reason_code"] == "A_LEDGER_UPDATED"
    )
    assert decision["disposition"] == "STORED_SILENTLY"
    assert decision["validated_records"][0]["fields"]["order_id"] == {
        "value": "#P",
        "source_event_ids": ["message:0:user"],
    }


def test_c2_adapter_holds_post_item_modification_write_and_replans_once():
    from tau2.data_model.message import AssistantMessage, UserMessage

    bad = _assistant_calls(
        (
            "bad",
            "cancel_pending_order",
            {"order_id": "#P", "reason": "ordered by mistake"},
        )
    )
    native = iter([bad, AssistantMessage.text("I need human support.")])
    history = [
        _assistant_calls(
            ("auth", "find_user_id_by_email", {"email": "a@example.com"})
        ),
        _tool_result("auth", "u1"),
        _assistant_calls(
            ("order", "get_order_details", {"order_id": "#P"})
        ),
        _tool_result(
            "order",
            {
                "order_id": "#P",
                "user_id": "u1",
                "status": "pending (items modifed)",
                "items": [],
                "payment_history": [],
            },
        ),
    ]
    agent = create_factorial_retail_runtime_agent_class()(
        tools=TOOLS,
        domain_policy="policy",
        llm="test",
        condition="C2_PREWRITE_CONTROL",
        runtime_config=_config("C2_PREWRITE_CONTROL"),
        generate_fn=lambda **_: next(native),
        semantic_generate_fn=lambda **_: (_ for _ in ()).throw(
            AssertionError("C2 called factor A")
        ),
    )
    outgoing, state = agent.generate_next_message(
        UserMessage.text("Please proceed."), agent.get_init_state(history)
    )
    assert outgoing.content == "I need human support."
    record = factorial_runtime_record(state)
    assert record["counts"]["b_opportunities"] == 1
    assert record["counts"]["b_replans"] == 1
    assert record["observer_audit"]["pass"]
    assert record["semantic_linkage_audit"]["pass"]
    replan = next(
        event
        for event in record["events"]
        if event["reason_code"] == "B_SINGLE_REPLAN"
    )
    finding = replan["findings"][0]
    assert finding["candidate_arguments"]["order_id"] == "#P"
    assert finding["observed"]["order"]["status"] == (
        "pending (items modifed)"
    )
    assert "Do not repeat" in finding["required_response"]


def test_a_compound_ledger_persists_and_refreshes_after_verified_write():
    from tau2.data_model.message import AssistantMessage, UserMessage

    captured = []
    native_outputs = iter(
        [
            _assistant_calls(
                ("read", "get_order_details", {"order_id": "#P"})
            ),
            _assistant_calls(
                (
                    "write",
                    "cancel_pending_order",
                    {"order_id": "#P", "reason": "ordered by mistake"},
                )
            ),
            AssistantMessage.text("I will continue with the return."),
            _assistant_calls(
                (
                    "return",
                    "return_delivered_order_items",
                    {
                        "order_id": "#D",
                        "item_ids": ["headphones"],
                        "payment_method_id": "card-1",
                    },
                )
            ),
        ]
    )

    def native(**kwargs):
        captured.append(kwargs["messages"])
        return next(native_outputs)

    semantic_calls = []

    def semantic(**_):
        semantic_calls.append(1)
        return AssistantMessage.text(
            json.dumps(
                {
                    "goals": [
                        {
                            "kind": "cancel_pending_order",
                            "fields": {
                                "order_id": {
                                    "value": "#P",
                                    "source_event_ids": ["message:0:user"],
                                },
                                "reason": {
                                    "value": "ordered it by mistake",
                                    "source_event_ids": ["message:0:user"],
                                },
                            },
                        },
                        {
                            "kind": "return_delivered_order_items",
                            "fields": {
                                "item_descriptions": {
                                    "value": "the headphones",
                                    "source_event_ids": ["message:0:user"],
                                }
                            },
                        },
                    ]
                }
            ),
            cost=0.002,
        )

    agent = create_factorial_retail_runtime_agent_class()(
        tools=TOOLS,
        domain_policy="policy",
        llm="test",
        condition="C1_SEMANTIC_SUPPORT",
        runtime_config=_config("C1_SEMANTIC_SUPPORT"),
        generate_fn=native,
        semantic_generate_fn=semantic,
    )
    state = agent.get_init_state()
    first, state = agent.generate_next_message(
        UserMessage.text(
            "Please cancel order #P because I ordered it by mistake, and "
            "return the headphones."
        ),
        state,
    )
    assert first.tool_calls[0].name == "get_order_details"
    assert state.active_card is not None
    second, state = agent.generate_next_message(
        _tool_result(
            "read",
            {
                "order_id": "#P",
                "user_id": "u1",
                "status": "pending",
                "items": [],
                "payment_history": [],
            },
        ),
        state,
    )
    assert second.tool_calls[0].name == "cancel_pending_order"
    assert state.active_card is not None
    third, state = agent.generate_next_message(
        _tool_result(
            "write",
            {
                "order_id": "#P",
                "user_id": "u1",
                "status": "cancelled",
                "items": [],
                "payment_history": [],
            },
        ),
        state,
    )
    # V2 does not add a post-write completion-review call. The native model's
    # response is therefore returned unchanged after the verified write.
    assert third.content == "I will continue with the return."
    assert len(semantic_calls) == 1
    for messages in captured:
        support = [
            str(message.content or "")
            for message in messages
            if "private_source_grounded_support"
            in str(message.content or "")
        ]
        assert len(support) == 1
        assert "#P" in support[0]
        assert "ordered it by mistake" in support[0]
        assert "the headphones" in support[0]
    final_support = next(
        str(message.content or "")
        for message in captured[-1]
        if "private_source_grounded_support" in str(message.content or "")
    )
    assert "verified_completed_writes" in final_support
    assert "cancel_pending_order" in final_support

    record = factorial_runtime_record(state)
    audit = record["semantic_linkage_audit"]
    assert audit == {
        "pass": True,
        "issues": [],
        "activated_cards": 2,
        "injected_cards": 2,
        "card_injections": 3,
        "write_linkages": 1,
    }
    activation = next(
        event
        for event in record["events"]
        if event["reason_code"] == "A_CARD_ACTIVATED"
    )
    fields = activation["validated_records"][0]["fields"]
    assert fields["order_id"] == {
        "value": "#P",
        "source_event_ids": ["message:0:user"],
    }
    linkage = next(
        event
        for event in record["events"]
        if event["reason_code"] == "A_CARD_REACHED_WRITE_CANDIDATE"
    )
    assert linkage["card_id"] == activation["card_id"]
    assert linkage["candidate_calls"][0]["arguments"]["order_id"] == "#P"


def test_invalid_a_sources_cannot_create_or_persist_a_card():
    from tau2.data_model.message import AssistantMessage, UserMessage

    agent = create_factorial_retail_runtime_agent_class()(
        tools=TOOLS,
        domain_policy="policy",
        llm="test",
        condition="C1_SEMANTIC_SUPPORT",
        runtime_config=_config("C1_SEMANTIC_SUPPORT"),
        generate_fn=lambda **_: AssistantMessage.text("Please clarify."),
        semantic_generate_fn=lambda **_: AssistantMessage.text(
            json.dumps(
                {
                    "goals": [
                        {
                            "kind": "cancel_pending_order",
                            "fields": {
                                "order_id": {
                                    "value": "#INVENTED",
                                    "source_event_ids": ["message:0:user"],
                                }
                            },
                        }
                    ]
                }
            )
        ),
    )
    _, state = agent.generate_next_message(
        UserMessage.text("Cancel order #P."), agent.get_init_state()
    )
    assert state.active_card is None
    record = factorial_runtime_record(state)
    assert record["counts"]["a_support_cards"] == 0
    assert record["semantic_linkage_audit"]["pass"]
    decision = next(
        event
        for event in record["events"]
        if event["event_type"] == "DECISION"
    )
    assert decision["reason_code"] == "A_VALIDATED_NO_OP"
    assert decision["rejection_details"]
