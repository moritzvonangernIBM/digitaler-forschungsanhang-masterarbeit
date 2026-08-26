"""One-turn, source-grounded advisory factor A."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any

from artifact.retail.state_projection import (
    WRITE_TOOLS,
)
from artifact.shared.contracts import (
    GroundedField,
    VisibleProcessState,
)

from .contracts import CommitmentEntry, GoalProposal, SemanticSupportCard

TRANSACTIONAL_FIELDS: dict[str, frozenset[str]] = {
    "cancel_pending_order": frozenset({"order_id", "reason", "scope"}),
    "modify_pending_order_address": frozenset(
        {
            "order_id",
            "address1",
            "address2",
            "city",
            "state",
            "country",
            "zip",
            "scope",
            "address_reference",
        }
    ),
    "modify_pending_order_items": frozenset(
        {
            "order_id",
            "item_ids",
            "new_item_ids",
            "payment_method_id",
            "item_descriptions",
            "desired_variant_constraints",
            "fallback_constraints",
            "scope",
        }
    ),
    "modify_pending_order_payment": frozenset(
        {"order_id", "payment_method_id", "scope"}
    ),
    "modify_user_address": frozenset(
        {
            "user_id",
            "address1",
            "address2",
            "city",
            "state",
            "country",
            "zip",
            "address_reference",
        }
    ),
    "return_delivered_order_items": frozenset(
        {
            "order_id",
            "item_ids",
            "item_descriptions",
            "payment_method_id",
            "reason",
            "scope",
        }
    ),
    "exchange_delivered_order_items": frozenset(
        {
            "order_id",
            "item_ids",
            "new_item_ids",
            "item_descriptions",
            "payment_method_id",
            "desired_variant_constraints",
            "fallback_constraints",
            "scope",
        }
    ),
}
SHORT_ACK = re.compile(
    r"^\s*(?:yes|no|ok|okay|sure|correct|confirmed|go ahead|please proceed|"
    r"do it|thanks|thank you)[.!]?\s*$",
    re.IGNORECASE,
)
TRANSACTION_REQUEST = re.compile(
    r"\b(?:cancel|return|refund|exchange|switch|replace|change|modify|update|"
    r"correct|fix|address|payment|no longer want|instead of)\b",
    re.IGNORECASE,
)
POST_COMPLETION_ACK = re.compile(
    r"\b(?:thank|thanks|appreciate|great)\b.*\b(?:handling|handled|"
    r"completed|confirming|done|starting|started|processing|processed)\b",
    re.IGNORECASE | re.DOTALL,
)

def is_transaction_request_text(text: str) -> bool:
    # Authentication statements such as "I do not remember my email
    # address" are not requests to mutate a postal address.
    candidate = re.sub(
        r"\be-?mail address\b",
        "email",
        text,
        flags=re.IGNORECASE,
    )
    return bool(
        candidate.strip()
        and not SHORT_ACK.fullmatch(candidate)
        and not POST_COMPLETION_ACK.search(candidate)
        and TRANSACTION_REQUEST.search(candidate)
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


def _scalars(value: Any):
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
        return bool(value) and all(_entailed(item, evidence) for item in value)
    if isinstance(value, dict) or value is None or isinstance(value, bool):
        return False
    visible = list(_scalars(evidence))
    if value in visible:
        return True
    if not isinstance(value, str):
        return False
    needle = value.casefold().strip()
    if not needle:
        return False
    bounded = re.compile(
        rf"(?<![a-z0-9_]){re.escape(needle)}(?![a-z0-9_])",
        re.IGNORECASE,
    )
    return any(
        bool(bounded.search(item))
        for item in visible
        if isinstance(item, str)
    )


def _valid_identifier(field_name: str, value: Any) -> bool:
    values = value if isinstance(value, list) else [value]
    if not values or any(not isinstance(item, str) for item in values):
        return False
    if field_name == "order_id":
        return all(bool(re.fullmatch(r"#[A-Za-z0-9_-]+", item)) for item in values)
    if field_name in {"item_ids", "new_item_ids"}:
        return all(
            bool(re.fullmatch(r"[A-Za-z0-9_-]+", item))
            and any(character.isdigit() for character in item)
            for item in values
        )
    if field_name == "user_id":
        return all(bool(re.fullmatch(r"[A-Za-z0-9_-]+", item)) for item in values)
    if field_name == "payment_method_id":
        return all(
            bool(re.fullmatch(r"[A-Za-z0-9_-]+", item))
            and "_" in item
            and any(character.isdigit() for character in item)
            for item in values
        )
    return True


def snapshot_prompt(state: VisibleProcessState) -> str:
    # Factor A is incremental: it extracts only the newest visible user
    # statement. Earlier commitments live in the deterministic ledger and are
    # never re-created from tool or assistant text.
    latest_user = list(state.user_utterances[-1:])
    evidence = [
        {"event_ids": list(field.source_event_ids), "value": field.value}
        for field in latest_user
    ]
    schema = {
        "goals": [
            {
                "kind": sorted(TRANSACTIONAL_FIELDS),
                "fields": {
                    "field_name": {
                        "value": "one verbatim visible scalar or list",
                        "source_event_ids": ["visible event id"],
                    }
                },
            }
        ]
    }
    allowed = {
        key: sorted(value) for key, value in TRANSACTIONAL_FIELDS.items()
    }
    return (
        "Extract only explicit transactional customer goals from the newest "
        "visible USER statement. Preserve explicit plural scope and relational "
        "references such as 'all pending orders' or 'the address already used "
        "by one order' in the allowed scope/address_reference fields. "
        "Return semantic content only. Never create goal IDs, "
        "revisions, status values, dependencies, policies, permissions, or "
        "completion claims. Omit unknown fields. Every field must use an "
        "allowed name and cite visible USER events containing that value. "
        "Tool, assistant, policy, and database values are context only and "
        "must never be promoted into customer intent. "
        "Return strict JSON only; use {\"goals\":[]} when none exist.\n"
        f"SCHEMA={json.dumps(schema, sort_keys=True)}\n"
        f"ALLOWED_FIELDS={json.dumps(allowed, sort_keys=True)}\n"
        f"VISIBLE_EVIDENCE={json.dumps(evidence, sort_keys=True)}"
    )


def parse_snapshot_records(
    state: VisibleProcessState,
    proposals: list[Any],
) -> tuple[tuple[GoalProposal, ...], tuple[dict[str, Any], ...]]:
    """Validate each record independently against visible source evidence."""

    catalog = _catalog(state)
    user_source_ids = {
        source_id
        for field in state.user_utterances
        for source_id in field.source_event_ids
    }
    accepted: list[GoalProposal] = []
    rejected: list[dict[str, Any]] = []
    for index, proposal in enumerate(proposals):
        try:
            if not isinstance(proposal, dict):
                raise ValueError("record must be an object")
            if set(proposal) - {"kind", "fields"}:
                raise ValueError("record contains technical or unknown keys")
            kind = str(proposal.get("kind") or "")
            allowed = TRANSACTIONAL_FIELDS.get(kind)
            if allowed is None or kind not in WRITE_TOOLS:
                raise ValueError("unsupported transactional goal kind")
            raw_fields = proposal.get("fields")
            if not isinstance(raw_fields, dict) or not raw_fields:
                raise ValueError("record requires at least one grounded field")
            fields: dict[str, GroundedField] = {}
            for key, raw in raw_fields.items():
                try:
                    if key not in allowed:
                        raise ValueError(
                            f"field {key!r} is invalid for {kind}"
                        )
                    if not isinstance(raw, dict) or set(raw) != {
                        "value",
                        "source_event_ids",
                    }:
                        raise ValueError(
                            f"field {key!r} requires value and source_event_ids"
                        )
                    source_ids = tuple(
                        str(item)
                        for item in raw.get("source_event_ids") or ()
                    )
                    if not source_ids or any(
                        item not in catalog for item in source_ids
                    ):
                        raise ValueError(
                            f"field {key!r} cites non-visible evidence"
                        )
                    if any(item not in user_source_ids for item in source_ids):
                        raise ValueError(
                            f"field {key!r} is not grounded in user authority"
                        )
                    evidence = [
                        value
                        for source_id in source_ids
                        for value in catalog[source_id]
                    ]
                    value = raw.get("value")
                    if not _entailed(value, evidence):
                        raise ValueError(
                            f"field {key!r} value is not entailed by cited evidence"
                        )
                    if key in {
                        "order_id",
                        "user_id",
                        "item_ids",
                        "new_item_ids",
                        "payment_method_id",
                    } and not _valid_identifier(key, value):
                        raise ValueError(
                            f"field {key!r} has an invalid identifier"
                        )
                    fields[str(key)] = GroundedField(value, source_ids)
                except (KeyError, TypeError, ValueError) as exc:
                    rejected.append(
                        {
                            "record_index": index,
                            "field": str(key),
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        }
                    )
            if not fields:
                raise ValueError("record has no valid grounded fields")
            accepted.append(GoalProposal(kind=kind, fields=fields))
        except (KeyError, TypeError, ValueError) as exc:
            rejected.append(
                {
                    "record_index": index,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
    return tuple(accepted), tuple(rejected)


def build_support_card(
    proposals: Iterable[GoalProposal],
    *,
    max_chars: int = 1600,
) -> SemanticSupportCard | None:
    """Render validated records only; empty input is a deterministic no-op."""

    rows = tuple(proposals)
    if not rows:
        return None
    payload = []
    source_ids: list[str] = []
    for proposal in rows:
        fields = {}
        for key in sorted(proposal.fields):
            field = proposal.fields[key]
            fields[key] = field.value
            source_ids.extend(field.source_event_ids)
        payload.append({"operation": proposal.kind, "explicit_fields": fields})
    body = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    prefix = (
        "Advisory only. Preserve these explicitly stated, source-grounded "
        "customer goals when deciding the next response. Do not infer missing "
        "values and continue to follow the Retail policy: "
    )
    content = (prefix + body)[:max_chars]
    return SemanticSupportCard(
        content=content,
        accepted_records=len(rows),
        source_event_ids=tuple(dict.fromkeys(source_ids)),
    )


def proposal_signature(proposal: GoalProposal) -> str:
    """Canonical semantic identity used only for deterministic deduplication."""

    payload = {
        "operation": proposal.kind,
        "fields": {
            key: proposal.fields[key].value for key in sorted(proposal.fields)
        },
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _identity_tokens(value: Any) -> set[str]:
    tokens: set[str] = set()
    for scalar in _scalars(value):
        if not isinstance(scalar, str):
            continue
        for token in re.findall(r"[a-z0-9]+", scalar.casefold()):
            if token in {"a", "an", "the", "my", "that", "this", "please"}:
                continue
            tokens.add(token[:-1] if token.endswith("s") and len(token) > 3 else token)
    return tokens


def _compatible_commitment(left: GoalProposal, right: GoalProposal) -> bool:
    if left.kind != right.kind:
        return False
    identifier_fields = ("order_id", "item_ids", "new_item_ids")
    matched_identifier = False
    for key in identifier_fields:
        if key not in left.fields or key not in right.fields:
            continue
        left_values = set(_scalars(left.fields[key].value))
        right_values = set(_scalars(right.fields[key].value))
        if left_values.isdisjoint(right_values):
            return False
        matched_identifier = True
    if matched_identifier:
        return True
    for key in (
        "item_descriptions",
        "address_reference",
        "desired_variant_constraints",
        "reason",
        "scope",
    ):
        if key not in left.fields or key not in right.fields:
            continue
        if _identity_tokens(left.fields[key].value) & _identity_tokens(
            right.fields[key].value
        ):
            return True
    return False


def _merge_compatible_proposals(
    left: GoalProposal,
    right: GoalProposal,
) -> GoalProposal:
    fields = dict(left.fields)
    for key, incoming in right.fields.items():
        current = fields.get(key)
        if current is None:
            fields[key] = incoming
            continue
        if current.value == incoming.value or (
            key
            in {
                "item_descriptions",
                "address_reference",
                "desired_variant_constraints",
                "reason",
                "scope",
            }
            and _identity_tokens(current.value) & _identity_tokens(incoming.value)
        ):
            fields[key] = GroundedField(
                current.value,
                tuple(
                    dict.fromkeys(
                        current.source_event_ids + incoming.source_event_ids
                    )
                ),
            )
    return GoalProposal(kind=left.kind, fields=fields)


def merge_commitments(
    existing: Iterable[CommitmentEntry],
    proposals: Iterable[GoalProposal],
    *,
    revision: int,
) -> tuple[tuple[CommitmentEntry, ...], tuple[CommitmentEntry, ...]]:
    """Append only semantically new commitments; never rewrite old evidence."""

    rows = list(existing)
    signatures = {proposal_signature(row.proposal) for row in rows}
    changed: list[CommitmentEntry] = []
    for proposal in proposals:
        signature = proposal_signature(proposal)
        if signature in signatures:
            continue
        compatible_index = next(
            (
                index
                for index, row in enumerate(rows)
                if _compatible_commitment(row.proposal, proposal)
            ),
            None,
        )
        if compatible_index is not None:
            current = rows[compatible_index]
            updated = CommitmentEntry(
                commitment_id=current.commitment_id,
                proposal=_merge_compatible_proposals(
                    current.proposal,
                    proposal,
                ),
                created_revision=current.created_revision,
            )
            signatures.discard(proposal_signature(current.proposal))
            rows[compatible_index] = updated
            signatures.add(proposal_signature(updated.proposal))
            if updated.proposal != current.proposal:
                changed.append(updated)
            continue
        entry = CommitmentEntry(
            commitment_id=f"G-{len(rows) + 1:04d}",
            proposal=proposal,
            created_revision=revision,
        )
        rows.append(entry)
        changed.append(entry)
        signatures.add(signature)
    return tuple(rows), tuple(changed)


def build_commitment_card(
    commitments: Iterable[CommitmentEntry],
    state: VisibleProcessState,
    *,
    max_chars: int = 2048,
) -> SemanticSupportCard | None:
    """Render a truthful compound checklist or fail open when it cannot fit."""

    entries = tuple(commitments)
    if len(entries) < 2:
        return None
    customer_rows: list[dict[str, Any]] = []
    source_ids: list[str] = []
    for entry in entries:
        fields: dict[str, Any] = {}
        for key in sorted(entry.proposal.fields):
            field = entry.proposal.fields[key]
            fields[key] = field.value
            source_ids.extend(field.source_event_ids)
        customer_rows.append(
            {
                "commitment_id": entry.commitment_id,
                "operation": entry.proposal.kind,
                "explicit_fields": fields,
            }
        )

    completed_rows: list[dict[str, Any]] = []
    for field in state.completed_writes:
        value = field.value if isinstance(field.value, dict) else {}
        completed_rows.append(
            {
                "tool_name": value.get("tool_name"),
                "arguments": value.get("arguments") or {},
            }
        )
        source_ids.extend(field.source_event_ids)

    payload = {
        "customer_commitments": customer_rows,
        "verified_completed_writes": completed_rows,
    }
    prefix = (
        "Selective advisory for a compound request. CUSTOMER_COMMITMENTS "
        "contain only source-grounded user statements; they are not "
        "permissions or completion claims. VERIFIED_COMPLETED_WRITES contain "
        "only successful visible tool outcomes. Use them as a checklist, do "
        "not repeat completed writes, do not infer missing values, and follow "
        "Retail policy. Do not alter an otherwise valid choice "
        "unless it conflicts with an explicit customer field: "
    )
    content = prefix + json.dumps(payload, sort_keys=True, ensure_ascii=True)
    if len(content) > max_chars:
        return None
    return SemanticSupportCard(
        content=content,
        accepted_records=len(entries),
        source_event_ids=tuple(dict.fromkeys(source_ids)),
    )
