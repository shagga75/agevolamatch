from __future__ import annotations

from datetime import date

from agevolamatch.models.company_profile import CompanyProfile
from agevolamatch.models.enums import CompanySize, Region
from agevolamatch.sources.anac import ANACSource
from agevolamatch.sources.ted import TEDSource
from agevolamatch.tenders.engine import match_tender, match_tender_profile


def make_profile(**overrides) -> CompanyProfile:
    defaults = {
        "name": "Test Srl",
        "region": Region.LAZIO,
        "size": CompanySize.MICRO,
        "cpv_codes": ["72200000"],
    }
    defaults.update(overrides)
    return CompanyProfile(**defaults)


def test_ineligible_tender_has_zero_score(tender_factory):
    tender = tender_factory(cpv_codes=["45232410"])
    result = match_tender(tender, make_profile(), as_of=date(2024, 6, 1))
    assert result.eligible is False
    assert result.score == 0.0
    assert result.explanation.reasons_against


def test_match_tender_profile_filters_out_ineligible_by_default(tender_factory):
    eligible = tender_factory(source_id="1", cpv_codes=["72200000"])
    ineligible = tender_factory(source_id="2", cpv_codes=["45232410"])
    results = match_tender_profile([eligible, ineligible], make_profile(), as_of=date(2024, 6, 1))
    assert {r.tender.source_id for r in results} == {"1"}


def test_match_tender_profile_sorted_descending(tender_factory):
    from datetime import UTC, datetime

    low = tender_factory(source_id="low", cpv_codes=[], close_date=datetime(2026, 1, 1, tzinfo=UTC))
    high = tender_factory(
        source_id="high", cpv_codes=["72200000"], close_date=datetime(2024, 6, 5, tzinfo=UTC)
    )
    results = match_tender_profile([low, high], make_profile(), as_of=date(2024, 6, 1))
    assert [r.tender.source_id for r in results] == ["high", "low"]


def test_real_fixture_data_from_both_sources_produces_a_coherent_ranking(
    anac_cig_raw_rows, ted_notices_raw, startup_profile
):
    """End-to-end sanity check with real curated fixture data from both ANAC
    and TED, using the real example profile's cpv_codes - the same path
    `agevolamatch gare match --profile examples/startup_profile.yaml`
    exercises against the live DB."""
    anac_source = ANACSource()
    ted_source = TEDSource()
    tenders = [anac_source.normalize(r) for r in anac_cig_raw_rows] + [
        ted_source.normalize(n) for n in ted_notices_raw
    ]

    results = match_tender_profile(tenders, startup_profile, as_of=date(2026, 9, 23))

    assert results  # at least one eligible tender in the curated sample
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)
    for r in results:
        assert r.eligible is True
        assert 0.0 <= r.score <= 100.0
        assert r.explanation.reasons_for or r.explanation.reasons_against or r.explanation.unverifiable
