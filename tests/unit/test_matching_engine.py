from __future__ import annotations

from datetime import UTC, date, datetime

from agevolamatch.matching.engine import match_incentive, match_profile
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


def test_ineligible_incentive_has_zero_score_and_no_breakdown(incentive_factory):
    incentive = incentive_factory(regions=["Sicilia"])
    result = match_incentive(incentive, make_profile(), as_of=date(2024, 6, 1))
    assert result.eligible is False
    assert result.score == 0.0
    assert result.score_breakdown == []
    assert result.explanation.reasons_against  # the failed region check should be surfaced


def test_eligible_incentive_has_populated_explanation(incentive_factory):
    incentive = incentive_factory(ateco_all_sectors=True)
    result = match_incentive(incentive, make_profile(), as_of=date(2024, 6, 1))
    assert result.eligible is True
    assert result.score_breakdown
    assert result.explanation.reasons_for  # at least the passing hard-filter checks


def test_match_profile_filters_out_ineligible_by_default(incentive_factory):
    eligible = incentive_factory(source_id="1", regions=["Lazio"])
    ineligible = incentive_factory(source_id="2", regions=["Sicilia"])
    results = match_profile([eligible, ineligible], make_profile(), as_of=date(2024, 6, 1))
    assert {r.incentive.source_id for r in results} == {"1"}


def test_match_profile_can_include_ineligible(incentive_factory):
    eligible = incentive_factory(source_id="1", regions=["Lazio"])
    ineligible = incentive_factory(source_id="2", regions=["Sicilia"])
    results = match_profile(
        [eligible, ineligible], make_profile(), as_of=date(2024, 6, 1), include_ineligible=True
    )
    assert {r.incentive.source_id for r in results} == {"1", "2"}


def test_match_profile_is_sorted_by_score_descending(incentive_factory):
    # Both must stay ATECO-eligible (a mismatch is a hard fail, not just a low
    # score) - "low" differs on cost overlap and urgency instead.
    low = incentive_factory(
        source_id="low",
        ateco_all_sectors=True,
        eligible_costs=["Fabbricati e terreni"],
        close_date=datetime(2026, 1, 1, tzinfo=UTC),
    )
    high = incentive_factory(
        source_id="high",
        ateco_all_sectors=False,
        ateco_codes=["62.01"],
        close_date=datetime(2024, 6, 5, tzinfo=UTC),
        eligible_costs=["Costo del personale"],
    )
    profile = make_profile(
        ateco_codes=[AtecoCode(code="62.01")], planned_expense_types=["Costo del personale"]
    )
    results = match_profile([low, high], profile, as_of=date(2024, 6, 1))
    assert [r.incentive.source_id for r in results] == ["high", "low"]


def test_startup_profile_fixture_produces_a_coherent_ranking(startup_profile, incentivi_gov_it_raw_docs):
    """End-to-end sanity check using the real example profile against the real
    curated fixture data - this is what `agevolamatch match --profile
    examples/startup_profile.yaml` exercises against the live DB."""
    from agevolamatch.sources.incentivi_gov_it import IncentiviGovItSource

    source = IncentiviGovItSource()
    incentives = [source.normalize(doc) for doc in incentivi_gov_it_raw_docs]

    results = match_profile(incentives, startup_profile, as_of=date(2026, 9, 23))

    assert results  # at least one eligible incentive in the curated sample
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)
    for r in results:
        assert r.eligible is True
        assert 0.0 <= r.score <= 100.0
        assert r.explanation.reasons_for or r.explanation.reasons_against or r.explanation.unverifiable
