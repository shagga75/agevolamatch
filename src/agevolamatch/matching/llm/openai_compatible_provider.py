from __future__ import annotations

import os
from dataclasses import dataclass, field

import httpx

from agevolamatch.matching.llm.base import LLMProvider

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"


@dataclass
class OpenAICompatibleProvider(LLMProvider):
    """Calls a paid API using the OpenAI chat-completions shape - works with
    OpenAI itself and any OpenAI-compatible endpoint (OpenRouter, a self-hosted
    vLLM/TGI server, etc.) by pointing LLM_API_BASE_URL elsewhere.

    Defaults use default_factory (read at instantiation), not a plain default
    (read once at class-definition/import time) - see OllamaProvider for why.
    """

    api_key: str = field(default_factory=lambda: os.environ.get("LLM_API_KEY", ""))
    base_url: str = field(default_factory=lambda: os.environ.get("LLM_API_BASE_URL", DEFAULT_BASE_URL))
    model: str = field(default_factory=lambda: os.environ.get("LLM_MODEL", DEFAULT_MODEL))
    timeout_seconds: float = 30.0

    def complete(self, prompt: str) -> str:
        if not self.api_key:
            raise RuntimeError("LLM_API_KEY is not set - required for the OpenAI-compatible provider")
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "messages": [{"role": "user", "content": prompt}]},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
