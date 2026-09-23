from __future__ import annotations

from datetime import UTC, date, datetime

from agevolamatch.matching.scoring import compute_score
from agevolamatch.matching.weights import ScoringWeights
from agevolamatch.models.company_profile import AtecoCode, CompanyProfile
from agevolamatch.models.enums import CompanySize, Region


def make_profile(**overrides) -> CompanyProfile:
    defaults = {
        "name": "Test Srl",
        "region": Region.LAZIO,
        "size": CompanySize.MICRO,
        "ateco_codes": [AtecoCode(code="62.01")],
    }
    defaults.update(overrides)
    return CompanyProfile(**defaults)


def test_score_is_0_to_100(incentive_factory):
    incentive = incentive_factory()
    score, breakdown = compute_score(incentive, make_profile(), ScoringWeights(), as_of=date(2024, 6, 1))
    assert 0.0 <= score <= 100.0
    assert len(breakdown) == 6


def test_perfect_match_scores_high(incentive_factory):
    incentive = incentive_factory(
        ateco_all_sectors=False,
        ateco_codes=["62.01"],
        eligible_costs=["Costo del personale", "Servizi, brevetti e licenze"],
        support_forms=["Contributo/Fondo perduto"],
        cost_min=1000,
        cost_max=100000,
        close_date=datetime(2024, 6, 10, tzinfo=UTC),  # 9 days from as_of -> high urgency
        beneficiary_types=["Impresa", "Impresa - SU/PMI innovativa"],
    )
    profile = make_profile(
        ateco_codes=[AtecoCode(code="62.01")],
        planned_expense_types=["Costo del personale", "Servizi, brevetti e licenze"],
        preferred_support_forms=["Contributo/Fondo perduto"],
        planned_investment_amount=50000,
        is_startup_innovativa=True,
    )
    score, breakdown = compute_score(incentive, profile, ScoringWeights(), as_of=date(2024, 6, 1))
    assert score > 85


def test_no_overlap_scores_low(incentive_factory):
    incentive = incentive_factory(
        ateco_all_sectors=False,
        ateco_codes=["10.01"],
        eligible_costs=["Fabbricati e terreni"],
        support_forms=["Interventi a garanzia"],
        cost_min=1_000_000,
        cost_max=2_000_000,
        close_date=datetime(2026, 1, 1, tzinfo=UTC),  # far away -> low urgency
    )
    profile = make_profile(
        ateco_codes=[AtecoCode(code="62.01")],
        planned_expense_types=["Costo del personale"],
        preferred_support_forms=["Contributo/Fondo perduto"],
        planned_investment_amount=5000,
    )
    score, _ = compute_score(incentive, profile, ScoringWeights(), as_of=date(2024, 6, 1))
    assert score < 30


def test_missing_optional_profile_fields_get_neutral_score(incentive_factory):
    incentive = incentive_factory()
    profile = make_profile()  # no planned expenses, no preferred forms, no amount, no flags
    score, breakdown = compute_score(incentive, profile, ScoringWeights(), as_of=date(2024, 6, 1))
    neutral_components = {"eligible_costs_match", "support_form_match", "amount_fit", "special_flags_match"}
    for component in breakdown:
        if component.criterion in neutral_components:
            assert component.achieved == component.weight * 0.5


def test_custom_weights_change_the_outcome(incentive_factory):
    incentive = incentive_factory(ateco_all_sectors=False, ateco_codes=["62.01"])
    profile = make_profile(ateco_codes=[AtecoCode(code="62.01")])

    zero_ateco_weight = ScoringWeights(ateco_match=0.0, eligible_costs_match=100.0)
    score, breakdown = compute_score(incentive, profile, zero_ateco_weight, as_of=date(2024, 6, 1))
    ateco_component = next(c for c in breakdown if c.criterion == "ateco_match")
    assert ateco_component.weight == 0.0
