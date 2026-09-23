"""Disabled unless AGEVOLAMATCH_LLM_PROVIDER is explicitly set - this is the
single switch that keeps the whole LLM feature opt-in, per the Fase 0 spec
("el sistema tiene que funcionar al 100% sin él")."""

from __future__ import annotations

import os

from agevolamatch.matching.llm.base import LLMProvider
from agevolamatch.matching.llm.ollama_provider import OllamaProvider
from agevolamatch.matching.llm.openai_compatible_provider import OpenAICompatibleProvider

_PROVIDERS = {
    "ollama": OllamaProvider,
    "openai": OpenAICompatibleProvider,
}


def get_llm_provider() -> LLMProvider | None:
    provider_name = os.environ.get("AGEVOLAMATCH_LLM_PROVIDER", "").strip().lower()
    if not provider_name:
        return None
    provider_cls = _PROVIDERS.get(provider_name)
    if provider_cls is None:
        raise ValueError(
            f"Unknown AGEVOLAMATCH_LLM_PROVIDER={provider_name!r}. Valid values: {', '.join(_PROVIDERS)}"
        )
    return provider_cls()
