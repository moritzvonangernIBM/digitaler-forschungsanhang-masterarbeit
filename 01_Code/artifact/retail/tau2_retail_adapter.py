"""Retail binding for the shared Tau2 runtime-intervention adapter."""

from __future__ import annotations

from typing import Any

from artifact.retail.bindings import (
    RETAIL_BINDINGS,
)
from artifact.shared.tau2_adapter import (
    NATIVE_AGENT_INSTRUCTION,
    NATIVE_SYSTEM_PROMPT,
    RuntimeInterventionState,
    create_runtime_intervention_agent,
    create_runtime_intervention_agent_class,
    runtime_record,
)

RetailRuntimeInterventionState = RuntimeInterventionState


def create_retail_runtime_intervention_agent_class():
    """Create the shared agent class with the frozen Retail bindings."""

    return create_runtime_intervention_agent_class(RETAIL_BINDINGS)


def create_retail_runtime_intervention_agent(**kwargs: Any):
    """Tau registry factory with Retail bindings and no evaluator access."""

    return create_runtime_intervention_agent(RETAIL_BINDINGS, **kwargs)


__all__ = [
    "RetailRuntimeInterventionState",
    "NATIVE_AGENT_INSTRUCTION",
    "NATIVE_SYSTEM_PROMPT",
    "create_retail_runtime_intervention_agent",
    "create_retail_runtime_intervention_agent_class",
    "runtime_record",
]
