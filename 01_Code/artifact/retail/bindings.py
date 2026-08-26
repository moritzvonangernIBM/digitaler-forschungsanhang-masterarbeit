"""Retail bindings for the shared runtime-intervention core."""

from artifact.retail.prewrite_control import (
    DeterministicPreWriteControl,
    PassThroughPreWriteControl,
    action_digest,
    bind_confirmation,
    is_explicit_confirmation_response,
)
from artifact.retail.semantic_support import (
    goal_extractor_prompt,
    next_evidence_read,
    parse_goal_records,
    reconcile_completed_goals,
    render_support_card,
)
from artifact.retail.state_projection import (
    WRITE_TOOLS,
    project_visible_state,
)
from artifact.shared.domain import (
    DomainRuntimeBindings,
)

RETAIL_BINDINGS = DomainRuntimeBindings(
    name="retail",
    write_tools=WRITE_TOOLS,
    project_visible_state=project_visible_state,
    goal_extractor_prompt=goal_extractor_prompt,
    parse_goal_records=parse_goal_records,
    next_evidence_read=next_evidence_read,
    render_support_card=render_support_card,
    reconcile_completed_goals=reconcile_completed_goals,
    enabled_prewrite_factory=DeterministicPreWriteControl,
    disabled_prewrite_factory=PassThroughPreWriteControl,
    action_digest=action_digest,
    bind_confirmation=bind_confirmation,
    is_explicit_confirmation_response=is_explicit_confirmation_response,
)
