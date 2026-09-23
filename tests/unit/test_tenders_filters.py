from __future__ import annotations

from datetime import UTC, date, datetime

from agevolamatch.matching.models import CheckStatus
from agevolamatch.models.company_profile import CompanyProfile
from agevolamatch.models.enums import CompanySize, Region
from agevolamatch.tenders.filters import apply_tender_hard_filters


def make_profile(**overrides) -> CompanyProfile:
    defaults = {
        "name": "Test Srl",
        "region": Region.LAZIO,
        "size": CompanySize.MICRO,
        "cpv_codes": ["72200000"],
    }
    defaults.update(overrides)
    return CompanyProfile(**defaults)


class TestStatusCheck:
    def test_open_tender_passes(self, tender_factory):
        tender = tender_factory(close_date=datetime(2099, 1, 1, tzinfo=UTC))
        result = apply_tender_hard_filters(tender, make_profile(), as_of=date(2024, 6, 1))
        assert next(c for c in result.checks if c.name == "status").status == CheckStatus.PASSED

    def test_closed_tender_fails_and_is_ineligible(self, tender_factory):
        tender = tender_factory(close_date=datetime(2020, 1, 1, tzinfo=UTC))
        result = apply_tender_hard_filters(tender, make_profile(), as_of=date(2024, 6, 1))
        assert next(c for c in result.checks if c.name == "status").status == CheckStatus.FAILED
        assert result.eligible is False

    def test_falls_back_to_stored_status_when_no_dates(self, tender_factory):
        tender = tender_factory(open_date=None, close_date=None, status="closed")
        result = apply_tender_hard_filters(tender, make_profile(), as_of=date(2024, 6, 1))
        assert next(c for c in result.checks if c.name == "status").status == CheckStatus.FAILED
        assert result.eligible is False


class TestCpvCheck:
    def test_matching_cpv_passes(self, tender_factory):
        tender = tender_factory(cpv_codes=["72200000"])
        result = apply_tender_hard_filters(tender, make_profile(cpv_codes=["72200000"]), as_of=date(2024, 6, 1))
        assert next(c for c in result.checks if c.name == "cpv").status == CheckStatus.PASSED

    def test_non_matching_cpv_fails(self, tender_factory):
        tender = tender_factory(cpv_codes=["45232410"])
        result = apply_tender_hard_filters(tender, make_profile(cpv_codes=["72200000"]), as_of=date(2024, 6, 1))
        assert next(c for c in result.checks if c.name == "cpv").status == CheckStatus.FAILED
        assert result.eligible is False

    def test_missing_tender_cpv_is_unverifiable_not_disqualifying(self, tender_factory):
        tender = tender_factory(cpv_codes=[])
        result = apply_tender_hard_filters(tender, make_profile(), as_of=date(2024, 6, 1))
        assert next(c for c in result.checks if c.name == "cpv").status == CheckStatus.UNVERIFIABLE
        assert result.eligible is True


class TestProvinceCheck:
    def test_absent_when_tender_has_no_province(self, tender_factory):
        tender = tender_factory(province=None)
        result = apply_tender_hard_filters(tender, make_profile(), as_of=date(2024, 6, 1))
        assert next((c for c in result.checks if c.name == "province"), None) is None

    def test_unverifiable_when_tender_restricts_to_a_province(self, tender_factory):
        tender = tender_factory(province="ROMA")
        result = apply_tender_hard_filters(tender, make_profile(), as_of=date(2024, 6, 1))
        check = next(c for c in result.checks if c.name == "province")
        assert check.status == CheckStatus.UNVERIFIABLE
        assert result.eligible is True


def test_fully_eligible_generic_tender(tender_factory):
    tender = tender_factory()
    result = apply_tender_hard_filters(tender, make_profile(), as_of=date(2024, 6, 1))
    assert result.eligible is True
    assert result.failed_checks == []
