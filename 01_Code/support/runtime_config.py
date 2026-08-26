from __future__ import annotations

from typing import Any


HOMS_AGENT_KWARGS_KEY = "__homs_agent_kwargs__"


def split_agent_runtime_kwargs(
    llm_args: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Separate HOMS architecture kwargs from provider-facing LLM kwargs."""
    provider_llm_args = dict(llm_args or {})
    agent_kwargs = dict(provider_llm_args.pop(HOMS_AGENT_KWARGS_KEY, {}) or {})
    return provider_llm_args, agent_kwargs
