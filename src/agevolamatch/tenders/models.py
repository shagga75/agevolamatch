"""Result models for tender matching - deliberately parallel to, but separate
from, matching/models.py's Incentive-typed MatchResult/HardFilterResult. This
mirrors the "módulo separado" (separate module) requirement from the Fase 5
spec: gare/tenders is a distinct domain with much thinner structured data
(no beneficiary type, no eligible costs, no support form) than incentives,
and forcing it through the same result types would either bloat those types
with tender-only fields or silently misuse incentive-shaped fields for a
different domain.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from agevolamatch.matching.models import CheckStatus, FilterCheck
from agevolamatch.models.opportunity import Tender


class TenderHardFilterResult(BaseModel):
    eligible: bool
    checks: list[FilterCheck]

    @property
    def failed_checks(self) -> list[FilterCheck]:
        return [c for c in self.checks if c.status == CheckStatus.FAILED]

    @property
    def unverifiable_checks(self) -> list[FilterCheck]:
        return [c for c in self.checks if c.status == CheckStatus.UNVERIFIABLE]


class TenderScoreComponent(BaseModel):
    criterion: str
    weight: float
    achieved: float
    detail: str


class TenderMatchExplanation(BaseModel):
    reasons_for: list[str] = Field(default_factory=list)
    reasons_against: list[str] = Field(default_factory=list)
    unverifiable: list[str] = Field(default_factory=list)


class TenderMatchResult(BaseModel):
    tender: Tender
    eligible: bool
    score: float = Field(description="0-100, only meaningful when eligible")
    hard_filter: TenderHardFilterResult
    score_breakdown: list[TenderScoreComponent]
    explanation: TenderMatchExplanation
