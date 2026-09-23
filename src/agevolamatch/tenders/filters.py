"""Hard eligibility filters for tenders. Much thinner than incentives'
(matching/filters.py): public procurement has no beneficiary-type or
eligible-cost concept in the data available here, and any company can
generally bid regardless of size (some tenders set a minimum turnover/
capacity requirement, but that's buried in tender documents this dataset
doesn't expose - never fabricated here, always left unverifiable like every
other gap in this project).
"""

from __future__ import annotations

from datetime import date

from agevolamatch.matching.models import CheckStatus, FilterCheck
from agevolamatch.models.company_profile import CompanyProfile
from agevolamatch.models.enums import OpportunityStatus
from agevolamatch.models.opportunity import Tender
from agevolamatch.sources.parsing import compute_status
from agevolamatch.tenders.cpv import CpvMatchLevel, match_cpv
from agevolamatch.tenders.models import TenderHardFilterResult


def _check_status(tender: Tender, as_of: date) -> FilterCheck:
    # Same fallback-to-stored-status principle as matching/filters.py: prefer
    # recomputing from dates when we have them, fall back to the status
    # already resolved at ingest time otherwise (relevant for a source that
    # might not carry both open_date and close_date).
    if tender.open_date is not None or tender.close_date is not None:
        status = compute_status(tender.open_date, tender.close_date, as_of=as_of)
    else:
        status = tender.status
    if status in (OpportunityStatus.OPEN, OpportunityStatus.UPCOMING):
        return FilterCheck(name="status", status=CheckStatus.PASSED, detail=f"Bando {status.value}")
    if status == OpportunityStatus.CLOSED:
        return FilterCheck(name="status", status=CheckStatus.FAILED, detail="Plazo de presentación de ofertas vencido")
    return FilterCheck(name="status", status=CheckStatus.UNVERIFIABLE, detail="No se pudo determinar el estado (faltan fechas)")


def _check_cpv(tender: Tender, profile: CompanyProfile) -> FilterCheck:
    level, detail = match_cpv(profile.cpv_codes, tender.cpv_codes)
    if level == CpvMatchLevel.NO_MATCH:
        return FilterCheck(name="cpv", status=CheckStatus.FAILED, detail=detail)
    if level == CpvMatchLevel.UNVERIFIABLE:
        return FilterCheck(name="cpv", status=CheckStatus.UNVERIFIABLE, detail=detail)
    return FilterCheck(name="cpv", status=CheckStatus.PASSED, detail=detail)


def _check_province(tender: Tender) -> FilterCheck | None:
    if not tender.province:
        return None
    return FilterCheck(
        name="province",
        status=CheckStatus.UNVERIFIABLE,
        detail=(
            f"Restringido a la provincia de {tender.province}; no hay mapeo comune/provincia→regione "
            "para verificarlo automáticamente contra la región del perfil (mismo TODO que para incentivi.gov.it)"
        ),
    )


def apply_tender_hard_filters(tender: Tender, profile: CompanyProfile, as_of: date | None = None) -> TenderHardFilterResult:
    today = as_of or date.today()
    checks = [_check_status(tender, today), _check_cpv(tender, profile)]
    province_check = _check_province(tender)
    if province_check is not None:
        checks.append(province_check)

    eligible = all(c.status != CheckStatus.FAILED for c in checks)
    return TenderHardFilterResult(eligible=eligible, checks=checks)
