"""Domain-aware offline oracle for successful transactional write effects."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
from typing import Any, Iterable, Mapping

from evaluation.offline.compound_effect_oracle import (
    compare_effect_sets as compare_retail_effect_sets,
)


DOMAIN_WRITE_TOOLS = {
    "retail": frozenset(
        {
            "cancel_pending_order",
            "modify_pending_order_address",
            "modify_pending_order_items",
            "modify_pending_order_payment",
            "modify_user_address",
            "return_delivered_order_items",
            "exchange_delivered_order_items",
        }
    ),
    "airline": frozenset(
        {
            "book_reservation",
            "cancel_reservation",
            "send_certificate",
            "update_reservation_baggages",
            "update_reservation_flights",
            "update_reservation_passengers",
        }
    ),
}
TARGET_KEYS = {
    "retail": ("order_id", "user_id", "item_id"),
    "airline": ("reservation_id", "user_id"),
}


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _value(record: Any, key: str, default: Any = None) -> Any:
    if isinstance(record, Mapping):
        return record.get(key, default)
    return getattr(record, key, default)


def _action(action: Any) -> tuple[str, dict[str, Any]]:
    name = str(
        _value(action, "operation")
        or _value(action, "name")
        or ""
    )
    arguments = _value(action, "arguments", {}) or {}
    if not isinstance(arguments, Mapping):
        raise ValueError("action arguments must be an object")
    return name, dict(arguments)


def _filter_actions(
    domain: str,
    actions: Iterable[Any],
) -> tuple[dict[str, Any], ...]:
    tools = DOMAIN_WRITE_TOOLS.get(domain)
    if tools is None:
        raise ValueError(f"unsupported transactional domain: {domain!r}")
    result: list[dict[str, Any]] = []
    for action in actions:
        name, arguments = _action(action)
        if name in tools:
            result.append({"operation": name, "arguments": arguments})
    return tuple(result)


@dataclass(frozen=True, slots=True)
class DomainEffectDiagnostic:
    kind: str
    expected: dict[str, Any] | None
    actual: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "expected": self.expected,
            "actual": self.actual,
        }


@dataclass(frozen=True, slots=True)
class DomainEffectScore:
    domain: str
    exact: bool
    expected_count: int
    actual_count: int
    missing: tuple[dict[str, Any], ...]
    extra: tuple[dict[str, Any], ...]
    diagnostics: tuple[DomainEffectDiagnostic, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "exact_mutation": int(self.exact),
            "expected_write_count": self.expected_count,
            "actual_write_count": self.actual_count,
            "missing_write_count": len(self.missing),
            "extra_write_count": len(self.extra),
            "missing_writes": list(self.missing),
            "extra_writes": list(self.extra),
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }


def _airline_signature(action: Mapping[str, Any]) -> str:
    return _canonical(
        {
            "operation": action["operation"],
            "arguments": action["arguments"],
        }
    )


def _airline_diagnostics(
    missing: list[dict[str, Any]],
    extra: list[dict[str, Any]],
) -> tuple[DomainEffectDiagnostic, ...]:
    remaining_missing = list(missing)
    remaining_extra = list(extra)
    diagnostics: list[DomainEffectDiagnostic] = []
    for expected in list(remaining_missing):
        expected_name = expected["operation"]
        expected_args = expected["arguments"]
        expected_target = tuple(
            (key, _canonical(expected_args[key]))
            for key in TARGET_KEYS["airline"]
            if key in expected_args
        )
        match = next(
            (
                actual
                for actual in remaining_extra
                if actual["operation"] == expected_name
                and tuple(
                    (key, _canonical(actual["arguments"][key]))
                    for key in TARGET_KEYS["airline"]
                    if key in actual["arguments"]
                )
                == expected_target
            ),
            None,
        )
        if match is not None:
            diagnostics.append(
                DomainEffectDiagnostic("wrong_parameter", expected, match)
            )
            remaining_missing.remove(expected)
            remaining_extra.remove(match)
    for expected in list(remaining_missing):
        match = next(
            (
                actual
                for actual in remaining_extra
                if actual["operation"] == expected["operation"]
            ),
            None,
        )
        if match is not None:
            diagnostics.append(
                DomainEffectDiagnostic("wrong_target", expected, match)
            )
            remaining_missing.remove(expected)
            remaining_extra.remove(match)
    diagnostics.extend(
        DomainEffectDiagnostic("missing_write", expected, None)
        for expected in remaining_missing
    )
    diagnostics.extend(
        DomainEffectDiagnostic("extra_write", None, actual)
        for actual in remaining_extra
    )
    return tuple(diagnostics)


def compare_domain_effects(
    domain: str,
    expected_actions: Iterable[Any],
    actual_actions: Iterable[Any],
) -> DomainEffectScore:
    """Compare successful write effects without runtime or reward access."""

    expected = _filter_actions(domain, expected_actions)
    actual = _filter_actions(domain, actual_actions)
    if domain == "retail":
        score = compare_retail_effect_sets(expected, actual)
        diagnostics = tuple(
            DomainEffectDiagnostic(
                item.kind,
                None if item.expected is None else item.expected.to_dict(),
                None if item.actual is None else item.actual.to_dict(),
            )
            for item in score.diagnostics
        )
        return DomainEffectScore(
            domain=domain,
            exact=score.exact,
            expected_count=score.expected_count,
            actual_count=score.actual_count,
            missing=tuple(item.to_dict() for item in score.missing),
            extra=tuple(item.to_dict() for item in score.extra),
            diagnostics=diagnostics,
        )

    expected_counter = Counter(_airline_signature(item) for item in expected)
    actual_counter = Counter(_airline_signature(item) for item in actual)
    missing = [
        json.loads(signature)
        for signature, count in sorted(
            (expected_counter - actual_counter).items()
        )
        for _ in range(count)
    ]
    extra = [
        json.loads(signature)
        for signature, count in sorted(
            (actual_counter - expected_counter).items()
        )
        for _ in range(count)
    ]
    return DomainEffectScore(
        domain=domain,
        exact=not missing and not extra,
        expected_count=len(expected),
        actual_count=len(actual),
        missing=tuple(missing),
        extra=tuple(extra),
        diagnostics=_airline_diagnostics(missing, extra),
    )


def extract_successful_write_actions(
    messages: Iterable[Any],
    *,
    domain: str,
) -> tuple[dict[str, Any], ...]:
    """Extract backend-observed, non-error Assistant write calls."""

    tools = DOMAIN_WRITE_TOOLS.get(domain)
    if tools is None:
        raise ValueError(f"unsupported transactional domain: {domain!r}")
    materialized = list(messages)
    results: dict[str, Any] = {}
    for message in materialized:
        role = str(_value(message, "role", ""))
        if role != "tool":
            continue
        call_id = str(_value(message, "id", "") or "")
        if call_id:
            results[call_id] = message
    actions: list[dict[str, Any]] = []
    observed: set[str] = set()
    for message in materialized:
        if str(_value(message, "role", "")) != "assistant":
            continue
        for call in _value(message, "tool_calls", []) or []:
            name = str(_value(call, "name", "") or "")
            if name not in tools:
                continue
            call_id = str(_value(call, "id", "") or "")
            if not call_id or call_id in observed:
                continue
            result = results.get(call_id)
            if result is None or bool(_value(result, "error", False)):
                continue
            observed.add(call_id)
            arguments = _value(call, "arguments", {}) or {}
            actions.append(
                {
                    "operation": name,
                    "arguments": dict(arguments),
                }
            )
    return tuple(actions)


def score_task_messages(
    *,
    domain: str,
    expected_actions: Iterable[Any],
    messages: Iterable[Any],
) -> DomainEffectScore:
    return compare_domain_effects(
        domain,
        expected_actions,
        extract_successful_write_actions(messages, domain=domain),
    )
