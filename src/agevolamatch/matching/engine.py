from __future__ import annotations

from datetime import date

from agevolamatch.matching.filters import apply_hard_filters
from agevolamatch.matching.models import CheckStatus, MatchExplanation, MatchResult, ScoreComponent
from agevolamatch.matching.scoring import compute_score
from agevolamatch.matching.weights import DEFAULT_WEIGHTS, ScoringWeights
from agevolamatch.models.company_profile import CompanyProfile
from agevolamatch.models.opportunity import Incentive

_STRONG_FRACTION = 0.7
_WEAK_FRACTION = 0.3


def _build_explanation(hard_filter_checks, score_breakdown: list[ScoreComponent]) -> MatchExplanation:
    reasons_for: list[str] = []
    reasons_against: list[str] = []
    unverifiable: list[str] = []

    for check in hard_filter_checks:
        if check.status == CheckStatus.PASSED:
            reasons_for.append(check.detail)
        elif check.status == CheckStatus.UNVERIFIABLE:
            unverifiable.append(check.detail)
        # FAILED checks aren't expected here: only eligible incentives reach this point.

    for component in score_breakdown:
        if component.weight <= 0:
            continue
        fraction = component.achieved / component.weight
        if fraction >= _STRONG_FRACTION:
            reasons_for.append(component.detail)
        elif fraction <= _WEAK_FRACTION:
            reasons_against.append(component.detail)

    return MatchExplanation(reasons_for=reasons_for, reasons_against=reasons_against, unverifiable=unverifiable)


def match_incentive(
    incentive: Incentive,
    profile: CompanyProfile,
    weights: ScoringWeights = DEFAULT_WEIGHTS,
    as_of: date | None = None,
) -> MatchResult:
    """Runs hard filters, and only scores when eligible (a low score is
    meaningless - and could look misleadingly like a bad-but-possible match -
    for something the company can't even apply to)."""
    hard_filter = apply_hard_filters(incentive, profile, as_of=as_of)

    if not hard_filter.eligible:
        return MatchResult(
            incentive=incentive,
            eligible=False,
            score=0.0,
            hard_filter=hard_filter,
            score_breakdown=[],
            explanation=MatchExplanation(
                reasons_against=[c.detail for c in hard_filter.failed_checks],
                unverifiable=[c.detail for c in hard_filter.unverifiable_checks],
            ),
        )

    score, breakdown = compute_score(incentive, profile, weights, as_of=as_of)
    explanation = _build_explanation(hard_filter.checks, breakdown)
    return MatchResult(
        incentive=incentive,
        eligible=True,
        score=round(score, 1),
        hard_filter=hard_filter,
        score_breakdown=breakdown,
        explanation=explanation,
    )


def match_profile(
    incentives: list[Incentive],
    profile: CompanyProfile,
    weights: ScoringWeights = DEFAULT_WEIGHTS,
    as_of: date | None = None,
    include_ineligible: bool = False,
) -> list[MatchResult]:
    results = [match_incentive(incentive, profile, weights, as_of=as_of) for incentive in incentives]
    if not include_ineligible:
        results = [r for r in results if r.eligible]
    return sorted(results, key=lambda r: r.score, reverse=True)
