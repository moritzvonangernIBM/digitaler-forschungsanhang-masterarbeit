"""Domain-neutral action identity and explicit-confirmation binding."""

from __future__ import annotations

import hashlib
import json
import re

from artifact.shared.contracts import (
    ConfirmationTicket,
    ConfirmationToken,
    ToolAction,
    VisibleProcessState,
)

AFFIRMATIVE = re.compile(
    r"\b(?:yes|yes please|i confirm|confirmed|go ahead|please proceed|do it|okay|ok)\b",
    re.IGNORECASE,
)
NEGATIVE = re.compile(
    r"^\s*(?:no\b|not yet\b|do not\b|don't\b)",
    re.IGNORECASE,
)


def canonical_action(action: ToolAction) -> str:
    return json.dumps(
        {"tool_name": action.tool_name, "arguments": action.arguments},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def action_digest(action: ToolAction) -> str:
    return hashlib.sha256(canonical_action(action).encode("utf-8")).hexdigest()


def issue_confirmation(
    state: VisibleProcessState,
    action: ToolAction,
) -> ConfirmationTicket:
    rendered = canonical_action(action)
    return ConfirmationTicket(
        action_digest=action_digest(action),
        source_state_revision=state.revision,
        canonical_action=rendered,
        message=f"Please confirm this exact action: {rendered}. Shall I proceed?",
    )


def bind_confirmation(
    ticket: ConfirmationTicket,
    *,
    user_text: str,
    user_event_id: str,
    current_state_revision: int,
) -> ConfirmationToken | None:
    if (
        not user_event_id
        or NEGATIVE.search(user_text)
        or not AFFIRMATIVE.search(user_text)
        or current_state_revision <= ticket.source_state_revision
    ):
        return None
    return ConfirmationToken(
        action_digest=ticket.action_digest,
        source_state_revision=ticket.source_state_revision,
        confirmed_state_revision=current_state_revision,
        user_event_id=user_event_id,
    )


def is_explicit_confirmation_response(user_text: str) -> bool:
    return bool(AFFIRMATIVE.search(user_text) or NEGATIVE.search(user_text))


def confirmation_matches(
    token: ConfirmationToken | None,
    state: VisibleProcessState,
    action: ToolAction,
) -> bool:
    return bool(
        token is not None
        and token.action_digest == action_digest(action)
        and token.confirmed_state_revision == state.revision
        and token.source_state_revision < token.confirmed_state_revision
    )

