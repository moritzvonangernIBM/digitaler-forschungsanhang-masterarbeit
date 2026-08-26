from evaluation.offline.transactional_effect_oracle import (
    compare_domain_effects,
    extract_successful_write_actions,
    score_task_messages,
)


def airline_action(
    name="update_reservation_flights",
    reservation_id="R1",
    flight_number="HAT001",
):
    return {
        "name": name,
        "arguments": {
            "reservation_id": reservation_id,
            "cabin": "economy",
            "flights": [
                {
                    "flight_number": flight_number,
                    "date": "2024-05-20",
                }
            ],
            "payment_id": "credit_card_1",
        },
    }


def test_airline_effect_multiset_is_order_independent_and_exact():
    first = airline_action()
    second = {
        "name": "cancel_reservation",
        "arguments": {"reservation_id": "R2"},
    }
    score = compare_domain_effects(
        "airline",
        [first, second],
        [second, first],
    )
    assert score.exact
    assert score.expected_count == score.actual_count == 2


def test_airline_wrong_nested_argument_is_diagnosed():
    score = compare_domain_effects(
        "airline",
        [airline_action()],
        [airline_action(flight_number="HAT999")],
    )
    assert not score.exact
    assert [item.kind for item in score.diagnostics] == ["wrong_parameter"]


def test_airline_wrong_reservation_is_wrong_target():
    score = compare_domain_effects(
        "airline",
        [airline_action()],
        [airline_action(reservation_id="WRONG")],
    )
    assert [item.kind for item in score.diagnostics] == ["wrong_target"]


def test_no_write_gold_detects_overexecution():
    actual = {
        "name": "cancel_reservation",
        "arguments": {"reservation_id": "R1"},
    }
    score = compare_domain_effects("airline", [], [actual])
    assert not score.exact
    assert score.expected_count == 0
    assert score.actual_count == 1
    assert [item.kind for item in score.diagnostics] == ["extra_write"]


def test_extraction_requires_observed_successful_tool_result():
    messages = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "ok",
                    "name": "cancel_reservation",
                    "arguments": {"reservation_id": "R1"},
                },
                {
                    "id": "failed",
                    "name": "send_certificate",
                    "arguments": {"user_id": "u1", "amount": 100},
                },
            ],
        },
        {"role": "tool", "id": "ok", "content": "done", "error": False},
        {"role": "tool", "id": "failed", "content": "no", "error": True},
    ]
    actions = extract_successful_write_actions(messages, domain="airline")
    assert actions == (
        {
            "operation": "cancel_reservation",
            "arguments": {"reservation_id": "R1"},
        },
    )


def test_retail_path_preserves_atomic_item_equivalence():
    expected = {
        "name": "return_delivered_order_items",
        "arguments": {
            "order_id": "#O1",
            "item_ids": ["i1", "i2"],
            "payment_method_id": "card_1",
        },
    }
    actual = [
        {
            "name": "return_delivered_order_items",
            "arguments": {
                "order_id": "#O1",
                "item_ids": [item],
                "payment_method_id": "card_1",
            },
        }
        for item in ("i1", "i2")
    ]
    score = compare_domain_effects("retail", [expected], actual)
    assert score.exact
    assert score.expected_count == score.actual_count == 2


def test_score_task_messages_filters_non_write_gold_actions():
    expected = [
        {"name": "get_reservation_details", "arguments": {"reservation_id": "R1"}},
        {"name": "cancel_reservation", "arguments": {"reservation_id": "R1"}},
    ]
    messages = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "write",
                    "name": "cancel_reservation",
                    "arguments": {"reservation_id": "R1"},
                }
            ],
        },
        {"role": "tool", "id": "write", "content": "done", "error": False},
    ]
    assert score_task_messages(
        domain="airline",
        expected_actions=expected,
        messages=messages,
    ).exact

