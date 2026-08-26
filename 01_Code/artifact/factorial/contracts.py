"""Minimal contracts for the final Retail 2x2 factors."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from artifact.shared.contracts import (
    GroundedField,
    ToolAction,
)


class FeasibilityDisposition(StrEnum):
    VALID_UNCHANGED = "VALID_UNCHANGED"
    EVIDENCE_REQUIRED = "EVIDENCE_REQUIRED"
    INVALID = "INVALID"


@dataclass(frozen=True, slots=True)
class SemanticSupportCard:
    """Selective advisory output; it has no action or blocking authority."""

    content: str
    accepted_records: int
    source_event_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.content.strip():
            raise ValueError("support card content is required")
        if self.accepted_records < 1:
            raise ValueError("a support card requires an accepted record")
        if not self.source_event_ids:
            raise ValueError("a support card requires visible sources")


@dataclass(frozen=True, slots=True)
class GoalProposal:
    """Semantic content only; all runtime bookkeeping is excluded."""

    kind: str
    fields: dict[str, GroundedField]


@dataclass(frozen=True, slots=True)
class CommitmentEntry:
    """One deduplicated, user-grounded transactional commitment."""

    commitment_id: str
    proposal: GoalProposal
    created_revision: int

    def __post_init__(self) -> None:
        if not self.commitment_id:
            raise ValueError("commitment_id is required")
        if self.created_revision < 0:
            raise ValueError("created_revision must be non-negative")


@dataclass(frozen=True, slots=True)
class FeasibilityEvaluation:
    call_id: str
    action: ToolAction
    disposition: FeasibilityDisposition
    reason_code: str
    evidence_action: ToolAction | None = None

    def __post_init__(self) -> None:
        if not self.call_id:
            raise ValueError("call_id is required")
        needs_evidence = (
            self.disposition == FeasibilityDisposition.EVIDENCE_REQUIRED
        )
        if needs_evidence != (self.evidence_action is not None):
            raise ValueError(
                "only EVIDENCE_REQUIRED has exactly one evidence action"
            )


@dataclass(frozen=True, slots=True)
class FeasibilityBundle:
    bundle_id: str
    tool_call_count: int
    write_evaluations: tuple[FeasibilityEvaluation, ...]

    @property
    def valid(self) -> bool:
        return all(
            row.disposition == FeasibilityDisposition.VALID_UNCHANGED
            for row in self.write_evaluations
        )

    @property
    def evidence_only(self) -> bool:
        unsafe = [
            row
            for row in self.write_evaluations
            if row.disposition
            != FeasibilityDisposition.VALID_UNCHANGED
        ]
        return bool(unsafe) and all(
            row.disposition == FeasibilityDisposition.EVIDENCE_REQUIRED
            for row in unsafe
        )

    def serialise(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "tool_call_count": self.tool_call_count,
            "write_evaluations": [
                {
                    "call_id": row.call_id,
                    "tool_name": row.action.tool_name,
                    "arguments": row.action.arguments,
                    "disposition": row.disposition.value,
                    "reason_code": row.reason_code,
                    "evidence_action": (
                        {
                            "tool_name": row.evidence_action.tool_name,
                            "arguments": row.evidence_action.arguments,
                        }
                        if row.evidence_action
                        else None
                    ),
                }
                for row in self.write_evaluations
            ],
        }
