"""Source-grounded semantic support with deterministic rendering and reads."""

from __future__ import annotations

import json
import re
from typing import Any, Iterable

from artifact.shared.contracts import (
    GoalKind,
    GoalRecord,
    GoalStatus,
    GroundedField,
    SemanticDecision,
    SemanticDisposition,
    SupportCard,
    ToolAction,
    VisibleProcessState,
)
from artifact.shared.visible_trace import (
    canonical_tool_action,
)

ALLOWED_GOAL_FIELDS = frozenset(
    {
        "user_id",
        "order_id",
        "item_ids",
        "new_item_ids",
        "product_id",
        "payment_method_id",
        "reason",
        "address1",
        "address2",
        "city",
        "state",
        "country",
        "zip",
        "item_descriptions",
        "desired_variant_constraints",
        "fallback_constraints",
    }
)
TERMINAL_STATUSES = {GoalStatus.COMPLETED, GoalStatus.WITHDRAWN}
TRUNCATION_MARKER = "... [CARD TRUNCATED]"


def active_goals(goals: Iterable[GoalRecord]) -> tuple[GoalRecord, ...]:
    latest: dict[str, GoalRecord] = {}
    for goal in goals:
        current = latest.get(goal.goal_id)
        if current is None or goal.revision > current.revision:
            latest[goal.goal_id] = goal
    return tuple(
        sorted(
            (
                goal
                for goal in latest.values()
                if goal.status not in TERMINAL_STATUSES
            ),
            key=lambda item: (item.kind.value, item.goal_id),
        )
    )


def _catalog(state: VisibleProcessState) -> dict[str, list[Any]]:
    result: dict[str, list[Any]] = {}
    fields = (
        list(state.user_utterances)
        + list(state.users.values())
        + list(state.orders.values())
        + list(state.products.values())
        + list(state.completed_writes)
    )
    if state.authenticated_user_id is not None:
        fields.append(state.authenticated_user_id)
    for field in fields:
        for source_id in field.source_event_ids:
            result.setdefault(source_id, []).append(field.value)
    return result


def _scalars(value: Any) -> Iterable[Any]:
    if isinstance(value, dict):
        for child in value.values():
            yield from _scalars(child)
    elif isinstance(value, list):
        for child in value:
            yield from _scalars(child)
    else:
        yield value


def _entailed(value: Any, evidence: list[Any]) -> bool:
    if isinstance(value, list):
        return bool(value) and all(_entailed(child, evidence) for child in value)
    visible = list(_scalars(evidence))
    if value in visible:
        return True
    if isinstance(value, str):
        needle = value.casefold().strip()
        if not needle:
            return False
        bounded = re.compile(
            rf"(?<![a-z0-9_]){re.escape(needle)}(?![a-z0-9_])",
            re.IGNORECASE,
        )
        return any(
            bool(bounded.search(candidate))
            for candidate in visible
            if isinstance(candidate, str)
        )
    return False


def parse_goal_records(
    state: VisibleProcessState,
    existing: Iterable[GoalRecord],
    proposals: list[dict[str, Any]],
) -> tuple[GoalRecord, ...]:
    """Validate a complete extraction atomically; never repair model output."""

    catalog = _catalog(state)
    latest = {goal.goal_id: goal for goal in active_goals(existing)}
    for goal in existing:
        current = latest.get(goal.goal_id)
        if current is None or goal.revision > current.revision:
            latest[goal.goal_id] = goal

    parsed: list[GoalRecord] = []
    for proposal in proposals:
        if not isinstance(proposal, dict):
            raise ValueError("every goal proposal must be an object")
        goal_id = str(proposal.get("goal_id") or "")
        revision = int(proposal.get("revision") or 0)
        expected_revision = latest[goal_id].revision + 1 if goal_id in latest else 1
        if revision != expected_revision:
            raise ValueError(
                f"goal {goal_id!r} must use revision {expected_revision}"
            )
        raw_fields = proposal.get("fields") or {}
        if not isinstance(raw_fields, dict):
            raise ValueError("goal fields must be an object")
        fields: dict[str, GroundedField] = {}
        for key, raw in raw_fields.items():
            if key not in ALLOWED_GOAL_FIELDS:
                raise ValueError(f"field {key!r} is outside the frozen schema")
            if not isinstance(raw, dict):
                raise ValueError(f"field {key!r} must contain value and sources")
            source_ids = tuple(
                str(item) for item in raw.get("source_event_ids") or ()
            )
            if not source_ids or any(item not in catalog for item in source_ids):
                raise ValueError(f"field {key!r} cites non-visible evidence")
            evidence = [
                value for source_id in source_ids for value in catalog[source_id]
            ]
            value = raw.get("value")
            if not _entailed(value, evidence):
                raise ValueError(f"field {key!r} is not entailed by its sources")
            fields[str(key)] = GroundedField(value, source_ids)

        status = GoalStatus(str(proposal.get("status") or GoalStatus.OPEN))
        if status not in {
            GoalStatus.OPEN,
            GoalStatus.UNRESOLVED,
            GoalStatus.WITHDRAWN,
        }:
            raise ValueError("semantic support cannot assert completion")
        record = GoalRecord(
            goal_id=goal_id,
            revision=revision,
            kind=GoalKind(str(proposal["kind"])),
            status=status,
            fields=fields,
            depends_on=tuple(
                str(item) for item in proposal.get("depends_on") or ()
            ),
        )
        parsed.append(record)
        latest[goal_id] = record

    known_ids = set(latest)
    if any(
        dependency not in known_ids
        for record in parsed
        for dependency in record.depends_on
    ):
        raise ValueError("goal dependency is not visible")
    return tuple(parsed)


def goal_extractor_prompt(
    state: VisibleProcessState, existing: Iterable[GoalRecord]
) -> str:
    """Create a fixed prompt containing visible evidence and schema only."""

    evidence = [
        {"event_ids": list(field.source_event_ids), "value": field.value}
        for field in (
            list(state.user_utterances)
            + list(state.users.values())
            + list(state.orders.values())
            + list(state.products.values())
        )
    ]
    prior = [
        {
            "goal_id": goal.goal_id,
            "revision": goal.revision,
            "kind": goal.kind.value,
            "status": goal.status.value,
        }
        for goal in existing
    ]
    schema = {
        "goals": [
            {
                "goal_id": "stable local ID such as g1",
                "revision": "positive integer",
                "kind": [kind.value for kind in GoalKind],
                "status": [
                    GoalStatus.OPEN.value,
                    GoalStatus.UNRESOLVED.value,
                    GoalStatus.WITHDRAWN.value,
                ],
                "fields": {
                    "allowed_keys": sorted(ALLOWED_GOAL_FIELDS),
                    "value_shape": {
                        "value": "verbatim visible value",
                        "source_event_ids": ["visible event id"],
                    },
                },
                "depends_on": ["visible goal_id"],
            }
        ]
    }
    return (
        "Extract only new or revised customer goals from visible evidence. "
        "A new goal must use the smallest unused local ID g1, g2, and so on "
        "with revision 1. A revised goal must reuse its existing goal_id and "
        "increment its revision by exactly one. Local goal IDs are bookkeeping "
        "labels; never invent domain identifiers or field values. Every field "
        "must cite visible events containing that value. Do not decide whether "
        "a write is safe or allowed. Return strict JSON only; use "
        "{\"goals\":[]} when no new or revised goal exists.\n"
        f"SCHEMA={json.dumps(schema, sort_keys=True)}\n"
        f"EXISTING={json.dumps(prior, sort_keys=True)}\n"
        f"VISIBLE_EVIDENCE={json.dumps(evidence, sort_keys=True)}"
    )


def next_evidence_read(
    state: VisibleProcessState,
    goals: Iterable[GoalRecord],
    *,
    opportunity_id: str,
) -> SemanticDecision:
    """Return at most one unique source-bound read for active goals."""

    failed_candidate_seen = False
    user_id = (
        str(state.authenticated_user_id.value)
        if state.authenticated_user_id is not None
        else ""
    )
    if not user_id:
        return SemanticDecision(
            SemanticDisposition.NO_OP,
            "A_AUTHENTICATION_REQUIRED",
            opportunity_id,
        )
    if user_id and user_id not in state.users and active_goals(goals):
        sources = state.authenticated_user_id.source_event_ids
        action = ToolAction("get_user_details", {"user_id": user_id}, sources)
        if canonical_tool_action(action.tool_name, action.arguments) in state.failed_tool_actions:
            failed_candidate_seen = True
        else:
            return SemanticDecision(
                SemanticDisposition.REQUEST_READ,
                "A_READ_AUTHENTICATED_USER",
                opportunity_id,
                action=action,
            )

    for goal in active_goals(goals):
        for field_name, tool_name, argument_name, observed in (
            ("order_id", "get_order_details", "order_id", state.orders),
            ("product_id", "get_product_details", "product_id", state.products),
        ):
            field = goal.fields.get(field_name)
            if field is None or str(field.value) in observed:
                continue
            if field_name == "order_id" and not str(field.value).startswith("#"):
                continue
            action = ToolAction(
                tool_name,
                {argument_name: str(field.value)},
                field.source_event_ids,
            )
            if (
                canonical_tool_action(action.tool_name, action.arguments)
                in state.failed_tool_actions
            ):
                failed_candidate_seen = True
                continue
            return SemanticDecision(
                SemanticDisposition.REQUEST_READ,
                f"A_READ_{field_name.upper()}",
                opportunity_id,
                action=action,
            )
    return SemanticDecision(
        SemanticDisposition.NO_OP,
        (
            "A_DUPLICATE_FAILED_READ_SUPPRESSED"
            if failed_candidate_seen
            else "A_NO_EVIDENCE_READ"
        ),
        opportunity_id,
    )


def _card_lines(goals: Iterable[GoalRecord]) -> tuple[list[str], tuple[str, ...], tuple[str, ...]]:
    lines = ["ACTIVE CUSTOMER GOALS"]
    bindings: list[str] = []
    source_ids: list[str] = []
    for goal in active_goals(goals):
        if not goal.fields:
            continue
        bindings.append(f"{goal.goal_id}@{goal.revision}")
        lines.append(f"- {goal.kind.value} [{goal.goal_id}@{goal.revision}]")
        lines.append("  grounded request:")
        for field_name in sorted(goal.fields):
            field = goal.fields[field_name]
            value = json.dumps(
                field.value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            sources = ",".join(sorted(field.source_event_ids))
            lines.append(f"    {field_name}={value} [sources: {sources}]")
            source_ids.extend(field.source_event_ids)
    if not bindings:
        return [], (), ()
    lines.extend(
        [
            "",
            "Use this card only as a source-grounded reminder.",
            "Follow the public policy and verify missing information.",
            "Do not infer values that are not listed.",
        ]
    )
    return (
        lines,
        tuple(bindings),
        tuple(dict.fromkeys(source_ids)),
    )


def render_support_card(
    goals: Iterable[GoalRecord],
    *,
    opportunity_id: str,
    max_chars: int,
) -> SemanticDecision:
    """Render a deterministic bounded card without a model call."""

    if max_chars < len(TRUNCATION_MARKER):
        raise ValueError("card limit is too small for deterministic truncation")
    lines, bindings, source_ids = _card_lines(goals)
    if not lines:
        return SemanticDecision(
            SemanticDisposition.NO_OP,
            "A_EMPTY_CARD",
            opportunity_id,
        )
    full = "\n".join(lines)
    if len(full) <= max_chars:
        card = SupportCard(full, bindings, source_ids, False)
        return SemanticDecision(
            SemanticDisposition.SUPPORT_CARD,
            "A_SUPPORT_CARD",
            opportunity_id,
            card=card,
        )

    kept: list[str] = []
    reserve = len(TRUNCATION_MARKER) + 1
    for line in lines:
        candidate = "\n".join(kept + [line])
        if len(candidate) + reserve > max_chars:
            break
        kept.append(line)
    content = "\n".join(kept + [TRUNCATION_MARKER])
    card = SupportCard(content, bindings, source_ids, True)
    return SemanticDecision(
        SemanticDisposition.SUPPORT_CARD,
        "A_SUPPORT_CARD_TRUNCATED",
        opportunity_id,
        card=card,
    )


def reconcile_completed_goals(
    goals: list[GoalRecord],
    state: VisibleProcessState,
    processed_write_events: set[str],
) -> tuple[GoalRecord, ...]:
    """Mark matching active goals complete from visible successful writes."""

    completed: list[GoalRecord] = []
    current = list(goals)
    for write_field in state.completed_writes:
        event_id = write_field.source_event_ids[0]
        if event_id in processed_write_events:
            continue
        processed_write_events.add(event_id)
        payload = write_field.value if isinstance(write_field.value, dict) else {}
        name = payload.get("tool_name")
        arguments = payload.get("arguments") or {}
        for goal in active_goals(current):
            if goal.kind.value != name:
                continue
            comparable = {
                key: field.value
                for key, field in goal.fields.items()
                if key in arguments
            }
            if any(arguments[key] != value for key, value in comparable.items()):
                continue
            record = GoalRecord(
                goal.goal_id,
                goal.revision + 1,
                goal.kind,
                GoalStatus.COMPLETED,
                goal.fields,
                goal.depends_on,
            )
            current.append(record)
            completed.append(record)
    goals.extend(completed)
    return tuple(completed)
