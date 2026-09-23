from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class AlertSubscription(BaseModel):
    """A saved profile plus what to alert on and where to send it."""

    name: str
    profile: Path = Field(description="Path to a CompanyProfile YAML file")
    min_score: float = Field(default=60.0, description="Only alert on matches scoring at or above this")
    channels: list[str] = Field(default_factory=lambda: ["telegram"], description="Channel names to send through")
    weights: Path | None = Field(default=None, description="Optional ScoringWeights YAML override")


def load_subscriptions(path: Path) -> list[AlertSubscription]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [AlertSubscription.model_validate(item) for item in data.get("subscriptions", [])]
