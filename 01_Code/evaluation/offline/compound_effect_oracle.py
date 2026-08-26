"""Independent offline oracle for compound Retail business effects.

This evaluator converts reference or observed writes into a multiset of
atomic business effects. It intentionally has no dependency on an artifact
runtime, contract builder, or reconciliation implementation.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
from typing import Any, Iterable, Mapping, Sequence


WRITE_TO_FAMILY = {
    "return_delivered_order_items": "return",
    "exchange_delivered_order_items": "exchange",
    "modify_pending_order_items": "pending_item",
    "cancel_pending_order": "cancel_pending",
    "modify_pending_order_address": "pending_address",
    "modify_user_address": "user_address",
    "modify_pending_order_payment": "pending_payment",
}
WRITE_TOOLS = frozenset(WRITE_TO_FAMILY)
TARGET_KEYS = ("order_id", "user_id", "item_id")


def _json_key(value: Mapping[str, Any]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


@dataclass(frozen=True, slots=True)
class AtomicEffect:
    operation: str
    attributes: tuple[tuple[str, str], ...]

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "AtomicEffect":
        operation = str(value.get("operation") or "")
        if operation not in WRITE_TOOLS:
            raise ValueError(f"unsupported write operation: {operation!r}")
        attributes = tuple(
            (str(key), _json_key({"value": child}))
            for key, child in sorted(value.items())
            if key != "operation"
        )
        return cls(operation, attributes)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"operation": self.operation}
        for key, frozen in self.attributes:
            result[key] = json.loads(frozen)["value"]
        return result

    @property
    def signature(self) -> str:
        return _json_key(self.to_dict())

    @property
    def target_signature(self) -> tuple[tuple[str, str], ...]:
        value = self.to_dict()
        return tuple(
            (key, _json_key({"value": value[key]}))
            for key in TARGET_KEYS
            if key in value
        )


@dataclass(frozen=True, slots=True)
class EffectDiagnostic:
    kind: str
    expected: AtomicEffect | None
    actual: AtomicEffect | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "expected": None if self.expected is None else self.expected.to_dict(),
            "actual": None if self.actual is None else self.actual.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class EffectSetScore:
    exact: bool
    exact_sequence: bool
    expected_count: int
    actual_count: int
    missing: tuple[AtomicEffect, ...]
    extra: tuple[AtomicEffect, ...]
    diagnostics: tuple[EffectDiagnostic, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "exact_effect_set_fulfilment": self.exact,
            "exact_effect_sequence": self.exact_sequence,
            "expected_effect_count": self.expected_count,
            "actual_effect_count": self.actual_count,
            "missing_effect_count": len(self.missing),
            "extra_effect_count": len(self.extra),
            "missing_effects": [effect.to_dict() for effect in self.missing],
            "extra_effects": [effect.to_dict() for effect in self.extra],
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }


def _action_parts(action: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    operation = str(action.get("operation") or action.get("name") or "")
    if operation not in WRITE_TOOLS:
        raise ValueError(f"unsupported write operation: {operation!r}")
    arguments = action.get("arguments") or {}
    if not isinstance(arguments, Mapping):
        raise ValueError("write arguments must be an object")
    return operation, dict(arguments)


def atomize_action(action: Mapping[str, Any]) -> tuple[AtomicEffect, ...]:
    """Return atomic effects while preserving item/new-item pairing."""

    operation, arguments = _action_parts(action)
    item_ids = arguments.pop("item_ids", None)
    new_item_ids = arguments.pop("new_item_ids", None)
    if item_ids is None:
        if new_item_ids is not None:
            raise ValueError("new_item_ids cannot exist without item_ids")
        return (AtomicEffect.from_dict({"operation": operation, **arguments}),)
    if not isinstance(item_ids, list) or not item_ids:
        raise ValueError("item_ids must be a non-empty list")
    if new_item_ids is not None:
        if not isinstance(new_item_ids, list):
            raise ValueError("new_item_ids must be a list")
        if len(new_item_ids) != len(item_ids):
            raise ValueError("item_ids and new_item_ids must have equal length")
    effects: list[AtomicEffect] = []
    for index, item_id in enumerate(item_ids):
        value = {
            "operation": operation,
            **arguments,
            "item_id": item_id,
        }
        if new_item_ids is not None:
            value["new_item_id"] = new_item_ids[index]
        effects.append(AtomicEffect.from_dict(value))
    return tuple(effects)


def atomize_actions(
    actions: Iterable[Mapping[str, Any]],
) -> tuple[AtomicEffect, ...]:
    return tuple(
        effect
        for action in actions
        for effect in atomize_action(action)
    )


def _counter(effects: Iterable[AtomicEffect]) -> Counter[str]:
    return Counter(effect.signature for effect in effects)


def _expand(counter: Counter[str]) -> list[AtomicEffect]:
    return [
        AtomicEffect.from_dict(json.loads(signature))
        for signature, count in sorted(counter.items())
        for _ in range(count)
    ]


def _diagnose(
    missing: Sequence[AtomicEffect],
    extra: Sequence[AtomicEffect],
) -> tuple[EffectDiagnostic, ...]:
    remaining_missing = list(missing)
    remaining_extra = list(extra)
    diagnostics: list[EffectDiagnostic] = []

    # Same operation and target, but another field differs.
    for expected in list(remaining_missing):
        match = next(
            (
                actual
                for actual in remaining_extra
                if actual.operation == expected.operation
                and actual.target_signature == expected.target_signature
            ),
            None,
        )
        if match is None:
            continue
        diagnostics.append(EffectDiagnostic("wrong_parameter", expected, match))
        remaining_missing.remove(expected)
        remaining_extra.remove(match)

    # Same operation, but target differs.
    for expected in list(remaining_missing):
        match = next(
            (
                actual
                for actual in remaining_extra
                if actual.operation == expected.operation
            ),
            None,
        )
        if match is None:
            continue
        diagnostics.append(EffectDiagnostic("wrong_target", expected, match))
        remaining_missing.remove(expected)
        remaining_extra.remove(match)

    diagnostics.extend(
        EffectDiagnostic("missing_effect", expected, None)
        for expected in remaining_missing
    )
    diagnostics.extend(
        EffectDiagnostic("extra_effect", None, actual)
        for actual in remaining_extra
    )
    return tuple(diagnostics)


def compare_effect_sets(
    expected_actions: Iterable[Mapping[str, Any]],
    actual_actions: Iterable[Mapping[str, Any]],
) -> EffectSetScore:
    expected = atomize_actions(expected_actions)
    actual = atomize_actions(actual_actions)
    expected_counter = _counter(expected)
    actual_counter = _counter(actual)
    missing = tuple(_expand(expected_counter - actual_counter))
    extra = tuple(_expand(actual_counter - expected_counter))
    return EffectSetScore(
        exact=not missing and not extra,
        exact_sequence=(
            tuple(effect.signature for effect in expected)
            == tuple(effect.signature for effect in actual)
        ),
        expected_count=len(expected),
        actual_count=len(actual),
        missing=missing,
        extra=extra,
        diagnostics=_diagnose(missing, extra),
    )


def extract_successful_write_actions(
    messages: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Extract only write calls with an observed non-error tool result."""

    materialized = list(messages)
    results: dict[str, Mapping[str, Any]] = {}
    for message in materialized:
        if message.get("role") != "tool":
            continue
        call_id = str(message.get("id") or "")
        if call_id:
            results[call_id] = message
    actions: list[dict[str, Any]] = []
    observed_call_ids: set[str] = set()
    for message in materialized:
        if message.get("role") != "assistant":
            continue
        for call in message.get("tool_calls") or []:
            operation = str(call.get("name") or "")
            if operation not in WRITE_TOOLS:
                continue
            call_id = str(call.get("id") or "")
            if not call_id or call_id in observed_call_ids:
                continue
            result = results.get(call_id)
            if result is None or result.get("error") is True:
                continue
            observed_call_ids.add(call_id)
            actions.append(
                {
                    "operation": operation,
                    "arguments": dict(call.get("arguments") or {}),
                }
            )
    return tuple(actions)
