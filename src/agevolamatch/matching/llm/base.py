"""Pluggable LLM interface. Disabled by default everywhere - the matching
engine (hard filters + weighted score) is fully deterministic and never
depends on this. When enabled, an LLMProvider is used strictly for
*informational* enrichment (see requirements.py), never to decide
eligibility or to override the score.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """A minimal single-turn text completion interface - deliberately not a
    full chat/tool-use API, since the only current use case (requirement
    extraction) is a single prompt in, single text response out."""

    @abstractmethod
    def complete(self, prompt: str) -> str: ...
