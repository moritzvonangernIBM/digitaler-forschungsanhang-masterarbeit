"""Oracle-free typed contracts shared across transactional domains."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class GoalKind(StrEnum):
    CANCEL_PENDING_ORDER = "cancel_pending_order"
    MODIFY_PENDING_ORDER_ADDRESS = "modify_pending_order_address"
    MODIFY_PENDING_ORDER_ITEMS = "modify_pending_order_items"
    MODIFY_PENDING_ORDER_PAYMENT = "modify_pending_order_payment"
    MODIFY_USER_ADDRESS = "modify_user_address"
    RETURN_DELIVERED_ORDER_ITEMS = "return_delivered_order_items"
    EXCHANGE_DELIVERED_ORDER_ITEMS = "exchange_delivered_order_items"
    INFORMATIONAL = "informational"
    BOOK_RESERVATION = "book_reservation"
    CANCEL_RESERVATION = "cancel_reservation"
    UPDATE_RESERVATION_BAGGAGES = "update_reservation_baggages"
    UPDATE_RESERVATION_FLIGHTS = "update_reservation_flights"
    UPDATE_RESERVATION_PASSENGERS = "update_reservation_passengers"
    SEND_CERTIFICATE = "send_certificate"


class GoalStatus(StrEnum):
    OPEN = "open"
    UNRESOLVED = "unresolved"
    WITHDRAWN = "withdrawn"
    COMPLETED = "completed"


class SemanticDisposition(StrEnum):
    NO_OP = "NO_OP"
    REQUEST_READ = "REQUEST_READ"
    SUPPORT_CARD = "SUPPORT_CARD"


class PreWriteDisposition(StrEnum):
    ALLOW_UNCHANGED = "ALLOW_UNCHANGED"
    REQUEST_EVIDENCE = "REQUEST_EVIDENCE"
    REQUEST_CONFIRMATION = "REQUEST_CONFIRMATION"
    REJECT = "REJECT"
    TRANSFER = "TRANSFER"


@dataclass(frozen=True, slots=True)
class GroundedField:
    value: Any
    source_event_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.source_event_ids or any(not item for item in self.source_event_ids):
            raise ValueError("grounded values require non-empty visible source IDs")


@dataclass(frozen=True, slots=True)
class GoalRecord:
    goal_id: str
    revision: int
    kind: GoalKind
    status: GoalStatus
    fields: dict[str, GroundedField] = field(default_factory=dict)
    depends_on: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.goal_id:
            raise ValueError("goal_id is required")
        if self.revision < 1:
            raise ValueError("goal revision must be positive")
        if self.goal_id in self.depends_on:
            raise ValueError("a goal cannot depend on itself")


@dataclass(slots=True)
class VisibleProcessState:
    revision: int = 0
    authenticated_user_id: GroundedField | None = None
    identified_user_id: GroundedField | None = None
    users: dict[str, GroundedField] = field(default_factory=dict)
    orders: dict[str, GroundedField] = field(default_factory=dict)
    products: dict[str, GroundedField] = field(default_factory=dict)
    reservations: dict[str, GroundedField] = field(default_factory=dict)
    flights: dict[str, GroundedField] = field(default_factory=dict)
    completed_writes: list[GroundedField] = field(default_factory=list)
    user_utterances: list[GroundedField] = field(default_factory=list)
    visible_user_event_ids: list[str] = field(default_factory=list)
    assistant_utterances: list[GroundedField] = field(default_factory=list)
    visible_assistant_event_ids: list[str] = field(default_factory=list)
    failed_tool_actions: set[tuple[str, str]] = field(default_factory=set)


@dataclass(frozen=True, slots=True)
class ToolAction:
    tool_name: str
    arguments: dict[str, Any]
    source_event_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.tool_name:
            raise ValueError("tool_name is required")


@dataclass(frozen=True, slots=True)
class SupportCard:
    content: str
    goal_bindings: tuple[str, ...]
    source_event_ids: tuple[str, ...]
    truncated: bool

    def __post_init__(self) -> None:
        if not self.content:
            raise ValueError("support cards must not be empty")


@dataclass(frozen=True, slots=True)
class SemanticOpportunity:
    opportunity_id: str
    should_extract: bool
    reason_code: str


@dataclass(frozen=True, slots=True)
class SemanticDecision:
    disposition: SemanticDisposition
    reason_code: str
    opportunity_id: str
    action: ToolAction | None = None
    card: SupportCard | None = None

    def __post_init__(self) -> None:
        if self.disposition == SemanticDisposition.REQUEST_READ and self.action is None:
            raise ValueError("REQUEST_READ requires one read action")
        if self.disposition != SemanticDisposition.REQUEST_READ and self.action is not None:
            raise ValueError("only REQUEST_READ can contain an action")
        if self.disposition == SemanticDisposition.SUPPORT_CARD and self.card is None:
            raise ValueError("SUPPORT_CARD requires a card")
        if self.disposition != SemanticDisposition.SUPPORT_CARD and self.card is not None:
            raise ValueError("only SUPPORT_CARD can contain a card")


@dataclass(frozen=True, slots=True)
class ConfirmationTicket:
    action_digest: str
    source_state_revision: int
    canonical_action: str
    message: str


@dataclass(frozen=True, slots=True)
class ConfirmationToken:
    action_digest: str
    source_state_revision: int
    confirmed_state_revision: int
    user_event_id: str


@dataclass(frozen=True, slots=True)
class PreWriteDecision:
    disposition: PreWriteDisposition
    reason_code: str
    candidate: ToolAction
    evidence_action: ToolAction | None = None
    confirmation_ticket: ConfirmationTicket | None = None

    def __post_init__(self) -> None:
        if (
            self.disposition == PreWriteDisposition.REQUEST_EVIDENCE
            and self.evidence_action is None
        ):
            raise ValueError("REQUEST_EVIDENCE requires one read action")
        if (
            self.disposition != PreWriteDisposition.REQUEST_EVIDENCE
            and self.evidence_action is not None
        ):
            raise ValueError("only REQUEST_EVIDENCE can contain a read action")
        if (
            self.disposition == PreWriteDisposition.REQUEST_CONFIRMATION
            and self.confirmation_ticket is None
        ):
            raise ValueError("REQUEST_CONFIRMATION requires one ticket")
        if (
            self.disposition != PreWriteDisposition.REQUEST_CONFIRMATION
            and self.confirmation_ticket is not None
        ):
            raise ValueError("only REQUEST_CONFIRMATION can contain a ticket")


@dataclass(frozen=True, slots=True)
class FactorAssignment:
    semantic_support: bool
    prewrite_control: bool
