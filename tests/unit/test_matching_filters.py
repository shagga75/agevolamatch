from __future__ import annotations

from datetime import UTC, date, datetime

from agevolamatch.matching.filters import apply_hard_filters
from agevolamatch.matching.models import CheckStatus
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


class TestStatusCheck:
    def test_open_incentive_passes(self, incentive_factory):
        incentive = incentive_factory(status="open", close_date=datetime(2099, 1, 1, tzinfo=UTC))
        result = apply_hard_filters(incentive, make_profile(), as_of=date(2024, 6, 1))
        status_check = next(c for c in result.checks if c.name == "status")
        assert status_check.status == CheckStatus.PASSED

    def test_closed_incentive_fails_and_is_ineligible(self, incentive_factory):
        incentive = incentive_factory(close_date=datetime(2020, 1, 1, tzinfo=UTC))
        result = apply_hard_filters(incentive, make_profile(), as_of=date(2024, 6, 1))
        status_check = next(c for c in result.checks if c.name == "status")
        assert status_check.status == CheckStatus.FAILED
        assert result.eligible is False


class TestRegionCheck:
    def test_matching_region_passes(self, incentive_factory):
        incentive = incentive_factory(regions=["Lazio", "Toscana"])
        result = apply_hard_filters(incentive, make_profile(region=Region.LAZIO), as_of=date(2024, 6, 1))
        assert next(c for c in result.checks if c.name == "region").status == CheckStatus.PASSED

    def test_non_matching_region_fails(self, incentive_factory):
        incentive = incentive_factory(regions=["Sicilia"])
        result = apply_hard_filters(incentive, make_profile(region=Region.LAZIO), as_of=date(2024, 6, 1))
        assert next(c for c in result.checks if c.name == "region").status == CheckStatus.FAILED
        assert result.eligible is False

    def test_missing_regions_is_unverifiable_not_disqualifying(self, incentive_factory):
        incentive = incentive_factory(regions=[])
        result = apply_hard_filters(incentive, make_profile(), as_of=date(2024, 6, 1))
        assert next(c for c in result.checks if c.name == "region").status == CheckStatus.UNVERIFIABLE
        assert result.eligible is True


class TestSizeCheck:
    def test_matching_size_passes(self, incentive_factory):
        incentive = incentive_factory(company_sizes=["Microimpresa"])
        result = apply_hard_filters(incentive, make_profile(size=CompanySize.MICRO), as_of=date(2024, 6, 1))
        assert next(c for c in result.checks if c.name == "size").status == CheckStatus.PASSED

    def test_non_matching_size_fails(self, incentive_factory):
        incentive = incentive_factory(company_sizes=["Grande Impresa"])
        result = apply_hard_filters(incentive, make_profile(size=CompanySize.MICRO), as_of=date(2024, 6, 1))
        assert next(c for c in result.checks if c.name == "size").status == CheckStatus.FAILED
        assert result.eligible is False


class TestBeneficiaryTypeCheck:
    def test_generic_impresa_passes_for_any_profile(self, incentive_factory):
        incentive = incentive_factory(beneficiary_types=["Impresa"])
        result = apply_hard_filters(incentive, make_profile(), as_of=date(2024, 6, 1))
        assert next(c for c in result.checks if c.name == "beneficiary_type").status == CheckStatus.PASSED

    def test_startup_innovativa_flag_matches_ambiguous_source_value(self, incentive_factory):
        incentive = incentive_factory(
            beneficiary_types=["Impresa - SU/PMI innovativa"], startup_or_pmi_innovativa_ambiguous=True
        )
        profile = make_profile(is_startup_innovativa=True)
        result = apply_hard_filters(incentive, profile, as_of=date(2024, 6, 1))
        check = next(c for c in result.checks if c.name == "beneficiary_type")
        assert check.status == CheckStatus.PASSED
        assert "no distingue" in check.detail

    def test_cooperativa_only_incentive_fails_for_plain_company(self, incentive_factory):
        incentive = incentive_factory(beneficiary_types=["Cooperative/Associazioni Non Profit"])
        result = apply_hard_filters(incentive, make_profile(), as_of=date(2024, 6, 1))
        assert next(c for c in result.checks if c.name == "beneficiary_type").status == CheckStatus.FAILED


class TestAtecoCheck:
    def test_all_sectors_passes(self, incentive_factory):
        incentive = incentive_factory(ateco_all_sectors=True, ateco_codes=None)
        result = apply_hard_filters(incentive, make_profile(), as_of=date(2024, 6, 1))
        assert next(c for c in result.checks if c.name == "ateco").status == CheckStatus.PASSED

    def test_no_overlap_fails(self, incentive_factory):
        incentive = incentive_factory(ateco_all_sectors=False, ateco_codes=["10.01"])
        result = apply_hard_filters(incentive, make_profile(ateco_codes=[AtecoCode(code="62.01")]), as_of=date(2024, 6, 1))
        assert next(c for c in result.checks if c.name == "ateco").status == CheckStatus.FAILED
        assert result.eligible is False


class TestAlwaysUnverifiableChecks:
    def test_age_requirement_is_always_unverifiable(self, incentive_factory):
        incentive = incentive_factory()
        result = apply_hard_filters(incentive, make_profile(), as_of=date(2024, 6, 1))
        assert next(c for c in result.checks if c.name == "age_requirement").status == CheckStatus.UNVERIFIABLE

    def test_municipalities_restriction_is_unverifiable_when_present(self, incentive_factory):
        incentive = incentive_factory(municipalities=["Roma", "Frosinone"])
        result = apply_hard_filters(incentive, make_profile(), as_of=date(2024, 6, 1))
        check = next((c for c in result.checks if c.name == "municipalities"), None)
        assert check is not None
        assert check.status == CheckStatus.UNVERIFIABLE
        assert result.eligible is True

    def test_municipalities_check_absent_when_not_restricted(self, incentive_factory):
        incentive = incentive_factory(municipalities=None)
        result = apply_hard_filters(incentive, make_profile(), as_of=date(2024, 6, 1))
        assert next((c for c in result.checks if c.name == "municipalities"), None) is None

    def test_special_territory_is_unverifiable_when_present(self, incentive_factory):
        incentive = incentive_factory(special_territory=["ZES"])
        result = apply_hard_filters(incentive, make_profile(), as_of=date(2024, 6, 1))
        check = next(c for c in result.checks if c.name == "special_territory")
        assert check.status == CheckStatus.UNVERIFIABLE
        assert result.eligible is True


def test_fully_eligible_generic_incentive(incentive_factory):
    incentive = incentive_factory()
    result = apply_hard_filters(incentive, make_profile(), as_of=date(2024, 6, 1))
    assert result.eligible is True
    assert result.failed_checks == []
