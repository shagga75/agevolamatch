from __future__ import annotations

import os
from dataclasses import dataclass, field

import httpx

from agevolamatch.matching.llm.base import LLMProvider

DEFAULT_HOST = "http://localhost:11434"
DEFAULT_MODEL = "llama3.2"
DEFAULT_TIMEOUT_SECONDS = 120.0


@dataclass
class OllamaProvider(LLMProvider):
    """Calls a local Ollama server's /api/generate. No API key needed - this
    is the "free, local, private" option the project's LLM interface must
    support per the Fase 0 spec.

    Defaults use default_factory (read at instantiation), not a plain
    default (read once at class-definition/import time) - a plain default
    would freeze whatever OLLAMA_HOST happened to be set to when this module
    was first imported, ignoring any later .env load or test monkeypatch.
    """

    host: str = field(default_factory=lambda: os.environ.get("OLLAMA_HOST", DEFAULT_HOST))
    model: str = field(default_factory=lambda: os.environ.get("OLLAMA_MODEL", DEFAULT_MODEL))
    # 120s default: confirmed live that a 3B model on CPU-only hardware can take
    # over 60s to cold-load and generate a short response - 60s was too tight.
    timeout_seconds: float = field(
        default_factory=lambda: float(os.environ.get("OLLAMA_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
    )

    def complete(self, prompt: str) -> str:
        response = httpx.post(
            f"{self.host}/api/generate",
            json={"model": self.model, "prompt": prompt, "stream": False},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()["response"]
