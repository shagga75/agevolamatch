from __future__ import annotations

from datetime import date

from agevolamatch.matching.models import CheckStatus
from agevolamatch.models.company_profile import CompanyProfile
from agevolamatch.models.opportunity import Tender
from agevolamatch.tenders.filters import apply_tender_hard_filters
from agevolamatch.tenders.models import TenderMatchExplanation, TenderMatchResult
from agevolamatch.tenders.scoring import (
    DEFAULT_TENDER_WEIGHTS,
    TenderScoringWeights,
    compute_tender_score,
)

_STRONG_FRACTION = 0.7
_WEAK_FRACTION = 0.3


def _build_explanation(hard_filter_checks, score_breakdown) -> TenderMatchExplanation:
    reasons_for, reasons_against, unverifiable = [], [], []

    for check in hard_filter_checks:
        if check.status == CheckStatus.PASSED:
            reasons_for.append(check.detail)
        elif check.status == CheckStatus.UNVERIFIABLE:
            unverifiable.append(check.detail)

    for component in score_breakdown:
        if component.weight <= 0:
            continue
        fraction = component.achieved / component.weight
        if fraction >= _STRONG_FRACTION:
            reasons_for.append(component.detail)
        elif fraction <= _WEAK_FRACTION:
            reasons_against.append(component.detail)

    return TenderMatchExplanation(reasons_for=reasons_for, reasons_against=reasons_against, unverifiable=unverifiable)


def match_tender(
    tender: Tender,
    profile: CompanyProfile,
    weights: TenderScoringWeights = DEFAULT_TENDER_WEIGHTS,
    as_of: date | None = None,
) -> TenderMatchResult:
    hard_filter = apply_tender_hard_filters(tender, profile, as_of=as_of)

    if not hard_filter.eligible:
        return TenderMatchResult(
            tender=tender,
            eligible=False,
            score=0.0,
            hard_filter=hard_filter,
            score_breakdown=[],
            explanation=TenderMatchExplanation(
                reasons_against=[c.detail for c in hard_filter.failed_checks],
                unverifiable=[c.detail for c in hard_filter.unverifiable_checks],
            ),
        )

    score, breakdown = compute_tender_score(tender, profile, weights, as_of=as_of)
    explanation = _build_explanation(hard_filter.checks, breakdown)
    return TenderMatchResult(
        tender=tender,
        eligible=True,
        score=round(score, 1),
        hard_filter=hard_filter,
        score_breakdown=breakdown,
        explanation=explanation,
    )


def match_tender_profile(
    tenders: list[Tender],
    profile: CompanyProfile,
    weights: TenderScoringWeights = DEFAULT_TENDER_WEIGHTS,
    as_of: date | None = None,
    include_ineligible: bool = False,
) -> list[TenderMatchResult]:
    results = [match_tender(t, profile, weights, as_of=as_of) for t in tenders]
    if not include_ineligible:
        results = [r for r in results if r.eligible]
    return sorted(results, key=lambda r: r.score, reverse=True)
