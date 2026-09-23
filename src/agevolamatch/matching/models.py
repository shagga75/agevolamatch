from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from agevolamatch.models.opportunity import Incentive


class CheckStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    UNVERIFIABLE = "unverifiable"


class FilterCheck(BaseModel):
    name: str
    status: CheckStatus
    detail: str


class HardFilterResult(BaseModel):
    eligible: bool
    checks: list[FilterCheck]

    @property
    def failed_checks(self) -> list[FilterCheck]:
        return [c for c in self.checks if c.status == CheckStatus.FAILED]

    @property
    def unverifiable_checks(self) -> list[FilterCheck]:
        return [c for c in self.checks if c.status == CheckStatus.UNVERIFIABLE]


class ScoreComponent(BaseModel):
    criterion: str
    weight: float
    achieved: float = Field(description="Points actually awarded, between 0 and weight")
    detail: str


class MatchExplanation(BaseModel):
    reasons_for: list[str] = Field(default_factory=list)
    reasons_against: list[str] = Field(default_factory=list)
    unverifiable: list[str] = Field(default_factory=list)


class MatchResult(BaseModel):
    incentive: Incentive
    eligible: bool
    score: float = Field(description="0-100, only meaningful when eligible")
    hard_filter: HardFilterResult
    score_breakdown: list[ScoreComponent]
    explanation: MatchExplanation
