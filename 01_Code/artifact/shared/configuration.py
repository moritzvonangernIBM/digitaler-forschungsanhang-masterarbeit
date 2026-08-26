"""Small final configuration loader for the submitted artifact code."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from artifact.shared.contracts import (
    FactorAssignment,
)

CODE_ROOT = Path(__file__).resolve().parents[2]
FINAL_DESIGN_REL = Path("config/final_design.json")


@dataclass(frozen=True, slots=True)
class ModuleABudgets:
    max_extractions_per_episode: int
    max_evidence_reads_per_episode: int
    max_evidence_reads_per_agent_turn: int
    max_support_cards_per_opportunity: int
    max_support_cards_per_episode: int
    max_support_card_chars: int


@dataclass(frozen=True, slots=True)
class ModuleBBudgets:
    max_evidence_reads_per_candidate: int
    max_evidence_reads_per_episode: int
    max_evidence_reads_per_agent_turn: int
    max_confirmation_requests_per_action_digest: int
    max_confirmation_cycles_per_episode: int
    max_rejections_per_action_digest: int
    max_transfers_per_episode: int


@dataclass(frozen=True, slots=True)
class FrozenRuntimeConfiguration:
    condition: str
    factors: FactorAssignment
    module_a: ModuleABudgets
    module_b: ModuleBBudgets
    agent_model: str
    user_model: str
    temperature: float
    reasoning_effort: str
    max_steps: int
    base: dict[str, Any]


def _load(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"configuration must be a JSON object: {path}")
    return value


def _positive_int(record: dict[str, Any], key: str) -> int:
    value = record.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{key} must be a positive integer")
    return value


def load_frozen_configuration(
    condition: str,
    *,
    repo_root: Path | None = None,
) -> FrozenRuntimeConfiguration:
    """Load one of the four final C0-C3 condition settings."""

    root = (repo_root or CODE_ROOT).resolve()
    design = _load(root / FINAL_DESIGN_REL)
    conditions = design["conditions"]
    if condition not in conditions:
        raise ValueError(f"unknown intervention condition: {condition}")
    factors = conditions[condition]
    module_a = design["module_a_limits"]
    module_b = design["module_b_limits"]
    shared = design["runtime"]

    # Minimal fields expected by adapters that still inspect the full config.
    base = {
        "module_a": {"model": shared["agent_model"], **module_a},
        "module_b": module_b,
        "shared_runtime": shared,
        "conditions": conditions,
    }

    return FrozenRuntimeConfiguration(
        condition=condition,
        factors=FactorAssignment(**factors),
        module_a=ModuleABudgets(
            max_extractions_per_episode=_positive_int(
                module_a, "max_extractions_per_episode"
            ),
            max_evidence_reads_per_episode=_positive_int(
                module_a, "max_evidence_reads_per_episode"
            ),
            max_evidence_reads_per_agent_turn=_positive_int(
                module_a, "max_evidence_reads_per_agent_turn"
            ),
            max_support_cards_per_opportunity=_positive_int(
                module_a, "max_support_cards_per_opportunity"
            ),
            max_support_cards_per_episode=_positive_int(
                module_a, "max_support_cards_per_episode"
            ),
            max_support_card_chars=_positive_int(
                module_a, "max_support_card_chars"
            ),
        ),
        module_b=ModuleBBudgets(
            max_evidence_reads_per_candidate=_positive_int(
                module_b, "max_evidence_reads_per_candidate"
            ),
            max_evidence_reads_per_episode=_positive_int(
                module_b, "max_evidence_reads_per_episode"
            ),
            max_evidence_reads_per_agent_turn=_positive_int(
                module_b, "max_evidence_reads_per_agent_turn"
            ),
            max_confirmation_requests_per_action_digest=_positive_int(
                module_b, "max_confirmation_requests_per_action_digest"
            ),
            max_confirmation_cycles_per_episode=_positive_int(
                module_b, "max_confirmation_cycles_per_episode"
            ),
            max_rejections_per_action_digest=_positive_int(
                module_b, "max_rejections_per_action_digest"
            ),
            max_transfers_per_episode=_positive_int(
                module_b, "max_transfers_per_episode"
            ),
        ),
        agent_model=str(shared["agent_model"]),
        user_model=str(shared["user_model"]),
        temperature=float(shared["temperature"]),
        reasoning_effort=str(shared["reasoning_effort"]),
        max_steps=_positive_int(shared, "max_steps"),
        base=base,
    )
