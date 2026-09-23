"""Soft 0-100 score for tenders. Only 3 components (vs. incentives' 6) -
gare/tenders data genuinely doesn't carry the richer structured signal
(eligible costs, support form, special flags) that incentivi.gov.it does;
padding this out with fabricated criteria would be worse than a shorter,
honest list. Only called for tenders that already passed the hard filters.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from agevolamatch.models.company_profile import CompanyProfile
from agevolamatch.models.enums import OpportunityStatus
from agevolamatch.models.opportunity import Tender
from agevolamatch.sources.parsing import compute_status
from agevolamatch.tenders.cpv import CpvMatchLevel, match_cpv
from agevolamatch.tenders.models import TenderScoreComponent


class TenderScoringWeights(BaseModel):
    cpv_match: float = Field(default=50.0, description="CPV code match: exact > prefix")
    amount_fit: float = Field(default=30.0, description="Estimated contract value near the profile's target deal size")
    urgency: float = Field(default=20.0, description="Closer deadline scores higher")


DEFAULT_TENDER_WEIGHTS = TenderScoringWeights()

_URGENCY_HORIZON_DAYS = 60
_NEUTRAL_FRACTION = 0.5
_OUT_OF_RANGE_FRACTION = 0.3
_CPV_PREFIX_FRACTION = 0.6


def _score_cpv(tender: Tender, profile: CompanyProfile, weight: float) -> TenderScoreComponent:
    level, detail = match_cpv(profile.cpv_codes, tender.cpv_codes)
    fraction = {
        CpvMatchLevel.EXACT: 1.0,
        CpvMatchLevel.PREFIX: _CPV_PREFIX_FRACTION,
        CpvMatchLevel.NO_MATCH: 0.0,
        CpvMatchLevel.UNVERIFIABLE: _NEUTRAL_FRACTION,
    }[level]
    return TenderScoreComponent(criterion="cpv_match", weight=weight, achieved=weight * fraction, detail=detail)


def _score_amount_fit(tender: Tender, profile: CompanyProfile, weight: float) -> TenderScoreComponent:
    # planned_investment_amount is an approximation here: it's defined on
    # CompanyProfile as the amount the company plans to *spend* (for
    # incentive matching), reused as a rough proxy for "the contract size
    # the company is looking for" - there's no dedicated tender-target-size
    # field, and adding one for a single scoring component felt like more
    # model surface than the signal is worth. Documented, not hidden.
    target = profile.planned_investment_amount
    if target is None or tender.estimated_value is None:
        return TenderScoreComponent(
            criterion="amount_fit",
            weight=weight,
            achieved=weight * _NEUTRAL_FRACTION,
            detail="Falta el importe estimado del bando o el importe objetivo del perfil",
        )
    ratio = tender.estimated_value / target if target else float("inf")
    # Within half to 5x the target amount counts as a reasonable fit for a
    # company sizing up whether a contract is worth bidding on.
    if 0.5 <= ratio <= 5:
        detail = f"Importe estimado del bando ({tender.estimated_value:.0f}€) es compatible con tu escala de proyecto"
        return TenderScoreComponent(criterion="amount_fit", weight=weight, achieved=weight, detail=detail)
    detail = f"Importe estimado del bando ({tender.estimated_value:.0f}€) está muy alejado de tu escala de proyecto"
    return TenderScoreComponent(criterion="amount_fit", weight=weight, achieved=weight * _OUT_OF_RANGE_FRACTION, detail=detail)


def _score_urgency(tender: Tender, weight: float, as_of: date) -> TenderScoreComponent:
    status = compute_status(tender.open_date, tender.close_date, as_of=as_of) if tender.close_date else tender.status
    if status == OpportunityStatus.UPCOMING:
        return TenderScoreComponent(criterion="urgency", weight=weight, achieved=weight * 0.3, detail="Todavía no ha abierto")
    if tender.close_date is None:
        return TenderScoreComponent(
            criterion="urgency", weight=weight, achieved=weight * _NEUTRAL_FRACTION, detail="Sin fecha límite definida"
        )
    days_left = (tender.close_date.date() - as_of).days
    fraction = max(0.0, min(1.0, 1 - days_left / _URGENCY_HORIZON_DAYS))
    detail = f"Cierra en {days_left} día(s)" if days_left >= 0 else "Fecha límite ya pasada"
    return TenderScoreComponent(criterion="urgency", weight=weight, achieved=weight * fraction, detail=detail)


def compute_tender_score(
    tender: Tender,
    profile: CompanyProfile,
    weights: TenderScoringWeights = DEFAULT_TENDER_WEIGHTS,
    as_of: date | None = None,
) -> tuple[float, list[TenderScoreComponent]]:
    today = as_of or date.today()
    components = [
        _score_cpv(tender, profile, weights.cpv_match),
        _score_amount_fit(tender, profile, weights.amount_fit),
        _score_urgency(tender, weights.urgency, today),
    ]
    total_weight = sum(c.weight for c in components) or 1.0
    total_achieved = sum(c.achieved for c in components)
    return 100.0 * total_achieved / total_weight, components
