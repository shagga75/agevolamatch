from __future__ import annotations

from datetime import UTC, date, datetime

from agevolamatch.models.company_profile import CompanyProfile
from agevolamatch.models.enums import CompanySize, Region
from agevolamatch.tenders.scoring import DEFAULT_TENDER_WEIGHTS, compute_tender_score


def make_profile(**overrides) -> CompanyProfile:
    defaults = {
        "name": "Test Srl",
        "region": Region.LAZIO,
        "size": CompanySize.MICRO,
        "cpv_codes": ["72200000"],
    }
    defaults.update(overrides)
    return CompanyProfile(**defaults)


def test_score_is_0_to_100(tender_factory):
    tender = tender_factory()
    score, breakdown = compute_tender_score(tender, make_profile(), DEFAULT_TENDER_WEIGHTS, as_of=date(2024, 6, 1))
    assert 0.0 <= score <= 100.0
    assert len(breakdown) == 3


def test_perfect_match_scores_high(tender_factory):
    tender = tender_factory(
        cpv_codes=["72200000"],
        estimated_value=50000.0,
        close_date=datetime(2024, 6, 5, tzinfo=UTC),
    )
    profile = make_profile(cpv_codes=["72200000"], planned_investment_amount=50000.0)
    score, _ = compute_tender_score(tender, profile, DEFAULT_TENDER_WEIGHTS, as_of=date(2024, 6, 1))
    assert score > 85


def test_no_overlap_scores_low(tender_factory):
    tender = tender_factory(
        cpv_codes=["45232410"],
        estimated_value=5_000_000.0,
        close_date=datetime(2026, 1, 1, tzinfo=UTC),
    )
    profile = make_profile(cpv_codes=["72200000"], planned_investment_amount=10_000.0)
    score, _ = compute_tender_score(tender, profile, DEFAULT_TENDER_WEIGHTS, as_of=date(2024, 6, 1))
    assert score < 30


def test_missing_optional_fields_get_neutral_score(tender_factory):
    tender = tender_factory(estimated_value=None)
    profile = make_profile(planned_investment_amount=None)
    _, breakdown = compute_tender_score(tender, profile, DEFAULT_TENDER_WEIGHTS, as_of=date(2024, 6, 1))
    amount_component = next(c for c in breakdown if c.criterion == "amount_fit")
    assert amount_component.achieved == amount_component.weight * 0.5


def test_amount_within_5x_target_counts_as_fit(tender_factory):
    tender = tender_factory(estimated_value=40000.0)
    profile = make_profile(planned_investment_amount=10000.0)  # ratio = 4, within 0.5-5x
    _, breakdown = compute_tender_score(tender, profile, DEFAULT_TENDER_WEIGHTS, as_of=date(2024, 6, 1))
    amount_component = next(c for c in breakdown if c.criterion == "amount_fit")
    assert amount_component.achieved == amount_component.weight


def test_amount_far_outside_target_is_penalized(tender_factory):
    tender = tender_factory(estimated_value=1_000_000.0)
    profile = make_profile(planned_investment_amount=10000.0)  # ratio = 100
    _, breakdown = compute_tender_score(tender, profile, DEFAULT_TENDER_WEIGHTS, as_of=date(2024, 6, 1))
    amount_component = next(c for c in breakdown if c.criterion == "amount_fit")
    assert amount_component.achieved < amount_component.weight * 0.5
