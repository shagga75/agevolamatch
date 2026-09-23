"""Configurable weights for the soft score. Defaults sum to 100 so the total
score lands in 0-100; a custom YAML file may use any scale since the engine
normalizes by the sum of weights actually in play.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class ScoringWeights(BaseModel):
    ateco_match: float = Field(default=25.0, description="ATECO code match: exact > prefix > all-sectors")
    eligible_costs_match: float = Field(default=20.0, description="Overlap between planned and eligible expenses")
    support_form_match: float = Field(default=15.0, description="Overlap with preferred support forms")
    amount_fit: float = Field(default=20.0, description="Planned investment falling within cost/grant range")
    urgency: float = Field(default=10.0, description="Closer close_date scores higher (encourages timely action)")
    special_flags_match: float = Field(
        default=10.0, description="Startup innovativa / PMI innovativa / femminile / under-35 bonus"
    )

    @classmethod
    def from_yaml(cls, path: Path) -> ScoringWeights:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls.model_validate(data)

    @property
    def total(self) -> float:
        return (
            self.ateco_match
            + self.eligible_costs_match
            + self.support_form_match
            + self.amount_fit
            + self.urgency
            + self.special_flags_match
        )


DEFAULT_WEIGHTS = ScoringWeights()
