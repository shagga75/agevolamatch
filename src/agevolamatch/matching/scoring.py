"""Soft 0-100 score. Only called for incentives that already passed the hard
filters (matching/filters.py) - a low score here means "eligible but not a
great fit", never "ineligible".

Every component that can't be evaluated because the profile simply didn't
configure the relevant optional field (e.g. no preferred_support_forms) gets
a neutral half-credit rather than 0 or full weight, so an incomplete profile
doesn't get unfairly punished or flattered on that axis.
"""

from __future__ import annotations

import math
from datetime import date

from agevolamatch.matching.ateco import AtecoMatchLevel, match_ateco
from agevolamatch.matching.filters import (
    IMPRESA_FEMMINILE,
    IMPRESA_GIOVANILE,
    STARTUP_OR_PMI_INNOVATIVA,
)
from agevolamatch.matching.models import ScoreComponent
from agevolamatch.matching.weights import ScoringWeights
from agevolamatch.models.company_profile import CompanyProfile
from agevolamatch.models.enums import OpportunityStatus
from agevolamatch.models.opportunity import Incentive
from agevolamatch.sources.parsing import compute_status

_URGENCY_HORIZON_DAYS = 90
_NEUTRAL_FRACTION = 0.5
_OUT_OF_RANGE_FRACTION = 0.3
_ATECO_PREFIX_FRACTION = 0.6
_ATECO_ALL_SECTORS_FRACTION = 0.4


def _score_ateco(incentive: Incentive, profile: CompanyProfile, weight: float) -> ScoreComponent:
    profile_codes = [c.code for c in profile.ateco_codes]
    level, detail = match_ateco(profile_codes, incentive.ateco_codes, incentive.ateco_all_sectors)
    fraction = {
        AtecoMatchLevel.EXACT: 1.0,
        AtecoMatchLevel.PREFIX: _ATECO_PREFIX_FRACTION,
        AtecoMatchLevel.ALL_SECTORS: _ATECO_ALL_SECTORS_FRACTION,
        AtecoMatchLevel.NO_MATCH: 0.0,
        AtecoMatchLevel.UNVERIFIABLE: _NEUTRAL_FRACTION,
    }[level]
    return ScoreComponent(criterion="ateco_match", weight=weight, achieved=weight * fraction, detail=detail)


def _score_eligible_costs(incentive: Incentive, profile: CompanyProfile, weight: float) -> ScoreComponent:
    if not profile.planned_expense_types:
        return ScoreComponent(
            criterion="eligible_costs_match",
            weight=weight,
            achieved=weight * _NEUTRAL_FRACTION,
            detail="El perfil no especifica tipos de gasto previstos",
        )
    planned = set(profile.planned_expense_types)
    eligible = set(incentive.eligible_costs)
    overlap = planned & eligible
    fraction = len(overlap) / len(planned) if planned else 0.0
    detail = (
        f"Cubre {len(overlap)}/{len(planned)} de tus gastos previstos ({', '.join(sorted(overlap)) or 'ninguno'})"
    )
    return ScoreComponent(criterion="eligible_costs_match", weight=weight, achieved=weight * fraction, detail=detail)


def _score_support_form(incentive: Incentive, profile: CompanyProfile, weight: float) -> ScoreComponent:
    if not profile.preferred_support_forms:
        return ScoreComponent(
            criterion="support_form_match",
            weight=weight,
            achieved=weight * _NEUTRAL_FRACTION,
            detail="El perfil no especifica una forma de agevolación preferida",
        )
    preferred = set(profile.preferred_support_forms)
    offered = set(incentive.support_forms)
    overlap = preferred & offered
    fraction = len(overlap) / len(preferred) if preferred else 0.0
    detail = f"Ofrece {', '.join(sorted(overlap)) or 'ninguna'} de tus formas de agevolación preferidas"
    return ScoreComponent(criterion="support_form_match", weight=weight, achieved=weight * fraction, detail=detail)


def _score_amount_fit(incentive: Incentive, profile: CompanyProfile, weight: float) -> ScoreComponent:
    amount = profile.planned_investment_amount
    if amount is None:
        return ScoreComponent(
            criterion="amount_fit",
            weight=weight,
            achieved=weight * _NEUTRAL_FRACTION,
            detail="El perfil no especifica un importe de inversión previsto",
        )
    if incentive.cost_min is None and incentive.cost_max is None:
        return ScoreComponent(
            criterion="amount_fit",
            weight=weight,
            achieved=weight * _NEUTRAL_FRACTION,
            detail="El incentivo no publica un rango de gasto admisible",
        )
    lower = incentive.cost_min or 0.0
    upper = incentive.cost_max if incentive.cost_max is not None else math.inf
    if lower <= amount <= upper:
        detail = f"Tu inversión prevista ({amount:.0f}€) está dentro del rango admitido ({lower:.0f}-{incentive.cost_max or '∞'}€)"
        return ScoreComponent(criterion="amount_fit", weight=weight, achieved=weight, detail=detail)
    detail = f"Tu inversión prevista ({amount:.0f}€) está fuera del rango admitido ({lower:.0f}-{incentive.cost_max or '∞'}€)"
    return ScoreComponent(criterion="amount_fit", weight=weight, achieved=weight * _OUT_OF_RANGE_FRACTION, detail=detail)


def _score_urgency(incentive: Incentive, weight: float, as_of: date) -> ScoreComponent:
    status = compute_status(incentive.open_date, incentive.close_date, as_of=as_of)
    if status == OpportunityStatus.UPCOMING:
        return ScoreComponent(
            criterion="urgency", weight=weight, achieved=weight * 0.3, detail="Todavía no ha abierto"
        )
    if incentive.close_date is None:
        return ScoreComponent(
            criterion="urgency", weight=weight, achieved=weight * _NEUTRAL_FRACTION, detail="Sin fecha de cierre definida"
        )
    days_left = (incentive.close_date.date() - as_of).days
    fraction = max(0.0, min(1.0, 1 - days_left / _URGENCY_HORIZON_DAYS))
    detail = f"Cierra en {days_left} día(s)" if days_left >= 0 else "Fecha de cierre ya pasada"
    return ScoreComponent(criterion="urgency", weight=weight, achieved=weight * fraction, detail=detail)


def _score_special_flags(incentive: Incentive, profile: CompanyProfile, weight: float) -> ScoreComponent:
    flag_targets = {
        "startup_or_pmi_innovativa": profile.is_startup_innovativa or profile.is_pmi_innovativa,
        "impresa_femminile": profile.is_impresa_femminile,
        "under_35": profile.is_under_35,
    }
    active_flags = {name for name, active in flag_targets.items() if active}
    if not active_flags:
        return ScoreComponent(
            criterion="special_flags_match",
            weight=weight,
            achieved=weight * _NEUTRAL_FRACTION,
            detail="El perfil no marca flags especiales (startup/PMI innovativa, femminile, under 35)",
        )

    beneficiary_hits = {
        "startup_or_pmi_innovativa": STARTUP_OR_PMI_INNOVATIVA in incentive.beneficiary_types,
        "impresa_femminile": IMPRESA_FEMMINILE in incentive.beneficiary_types,
        "under_35": IMPRESA_GIOVANILE in incentive.beneficiary_types,
    }
    scope_hits = {
        "impresa_femminile": "Imprenditoria femminile" in incentive.scope,
        "under_35": "Imprenditoria giovanile" in incentive.scope,
    }
    matched = {f for f in active_flags if beneficiary_hits.get(f) or scope_hits.get(f)}
    fraction = len(matched) / len(active_flags)
    detail = f"Coincide en {len(matched)}/{len(active_flags)} flags especiales del perfil"
    return ScoreComponent(criterion="special_flags_match", weight=weight, achieved=weight * fraction, detail=detail)


def compute_score(
    incentive: Incentive,
    profile: CompanyProfile,
    weights: ScoringWeights,
    as_of: date | None = None,
) -> tuple[float, list[ScoreComponent]]:
    today = as_of or date.today()
    components = [
        _score_ateco(incentive, profile, weights.ateco_match),
        _score_eligible_costs(incentive, profile, weights.eligible_costs_match),
        _score_support_form(incentive, profile, weights.support_form_match),
        _score_amount_fit(incentive, profile, weights.amount_fit),
        _score_urgency(incentive, weights.urgency, today),
        _score_special_flags(incentive, profile, weights.special_flags_match),
    ]
    total_weight = sum(c.weight for c in components) or 1.0
    total_achieved = sum(c.achieved for c in components)
    score = 100.0 * total_achieved / total_weight
    return score, components
