"""Explicit domain bindings for one shared intervention runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True, slots=True)
class DomainRuntimeBindings:
    """Domain-specific behavior injected into the treatment-neutral core."""

    name: str
    write_tools: frozenset[str]
    project_visible_state: Callable[[Any], Any]
    goal_extractor_prompt: Callable[[Any, Any], str]
    parse_goal_records: Callable[[Any, Any, list[dict[str, Any]]], Any]
    next_evidence_read: Callable[..., Any]
    render_support_card: Callable[..., Any]
    reconcile_completed_goals: Callable[..., Any]
    enabled_prewrite_factory: Callable[[], Any]
    disabled_prewrite_factory: Callable[[], Any]
    action_digest: Callable[[Any], str]
    bind_confirmation: Callable[..., Any]
    is_explicit_confirmation_response: Callable[[str], bool]
    transfer_tool: str = "transfer_to_human_agents"

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("domain binding name is required")
        if not self.write_tools:
            raise ValueError("at least one write tool must be bound")

