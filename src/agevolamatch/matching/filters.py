"""Hard eligibility filters. Per the project's own rule: a field that is
empty/unknown on the incentive, or that we simply cannot verify against the
CompanyProfile we model (age requirements, municipality-level restrictions,
special territorial status), must never disqualify a match - it's recorded
as "unverifiable" instead. Only a concrete mismatch fails a check.
"""

from __future__ import annotations

from datetime import date

from agevolamatch.matching.ateco import AtecoMatchLevel, match_ateco
from agevolamatch.matching.models import CheckStatus, FilterCheck, HardFilterResult
from agevolamatch.models.company_profile import CompanyProfile
from agevolamatch.models.enums import OpportunityStatus
from agevolamatch.models.opportunity import Incentive
from agevolamatch.sources.parsing import compute_status

STARTUP_OR_PMI_INNOVATIVA = "Impresa - SU/PMI innovativa"
IMPRESA_FEMMINILE = "Impresa - prevalenza femminile"
IMPRESA_GIOVANILE = "Impresa - prevalenza giovanile"
COOPERATIVA = "Cooperative/Associazioni Non Profit"
IMPRESA = "Impresa"


def _expected_beneficiary_types(profile: CompanyProfile) -> set[str]:
    """What Tipologia_Soggetto values this profile could plausibly satisfy.

    The source has no direct "is this a plain company" field - almost every
    incentive that targets companies uses the generic "Impresa" value, so any
    company profile is assumed eligible for that baseline, plus any of the
    special-flag variants it qualifies for.
    """
    expected = {IMPRESA}
    if profile.legal_form and profile.legal_form.value == "cooperativa":
        expected.add(COOPERATIVA)
    if profile.is_startup_innovativa or profile.is_pmi_innovativa:
        expected.add(STARTUP_OR_PMI_INNOVATIVA)
    if profile.is_impresa_femminile:
        expected.add(IMPRESA_FEMMINILE)
    if profile.is_under_35:
        expected.add(IMPRESA_GIOVANILE)
    return expected


def _check_status(incentive: Incentive, as_of: date) -> FilterCheck:
    status = compute_status(incentive.open_date, incentive.close_date, as_of=as_of)
    if status in (OpportunityStatus.OPEN, OpportunityStatus.UPCOMING):
        return FilterCheck(name="status", status=CheckStatus.PASSED, detail=f"Bando {status.value}")
    if status == OpportunityStatus.CLOSED:
        return FilterCheck(name="status", status=CheckStatus.FAILED, detail="Bando cerrado")
    return FilterCheck(name="status", status=CheckStatus.UNVERIFIABLE, detail="No se pudo determinar el estado (faltan fechas)")


def _check_region(incentive: Incentive, profile: CompanyProfile) -> FilterCheck:
    if not incentive.regions:
        return FilterCheck(name="region", status=CheckStatus.UNVERIFIABLE, detail="El incentivo no especifica regiones")
    if profile.region.value in incentive.regions:
        return FilterCheck(name="region", status=CheckStatus.PASSED, detail=f"Disponible en {profile.region.value}")
    return FilterCheck(
        name="region",
        status=CheckStatus.FAILED,
        detail=f"No disponible en {profile.region.value} (regiones: {', '.join(incentive.regions)})",
    )


def _check_size(incentive: Incentive, profile: CompanyProfile) -> FilterCheck:
    if not incentive.company_sizes:
        return FilterCheck(name="size", status=CheckStatus.UNVERIFIABLE, detail="El incentivo no especifica tamaños de empresa elegibles")
    if profile.size.value in incentive.company_sizes:
        return FilterCheck(name="size", status=CheckStatus.PASSED, detail=f"Tamaño {profile.size.value} elegible")
    return FilterCheck(
        name="size",
        status=CheckStatus.FAILED,
        detail=f"Tamaño {profile.size.value} no está entre los elegibles ({', '.join(incentive.company_sizes)})",
    )


def _check_beneficiary_type(incentive: Incentive, profile: CompanyProfile) -> FilterCheck:
    if not incentive.beneficiary_types:
        return FilterCheck(name="beneficiary_type", status=CheckStatus.UNVERIFIABLE, detail="El incentivo no especifica tipo de beneficiario")
    expected = _expected_beneficiary_types(profile)
    overlap = expected & set(incentive.beneficiary_types)
    if overlap:
        detail = f"Coincide como {', '.join(sorted(overlap))}"
        if incentive.startup_or_pmi_innovativa_ambiguous and STARTUP_OR_PMI_INNOVATIVA in overlap:
            detail += " (el origen no distingue startup innovativa de PMI innovativa)"
        return FilterCheck(name="beneficiary_type", status=CheckStatus.PASSED, detail=detail)
    return FilterCheck(
        name="beneficiary_type",
        status=CheckStatus.FAILED,
        detail=f"Ninguno de los tipos de beneficiario del incentivo ({', '.join(incentive.beneficiary_types)}) aplica al perfil",
    )


def _check_ateco(incentive: Incentive, profile: CompanyProfile) -> FilterCheck:
    profile_codes = [c.code for c in profile.ateco_codes]
    level, detail = match_ateco(profile_codes, incentive.ateco_codes, incentive.ateco_all_sectors)
    if level == AtecoMatchLevel.NO_MATCH:
        return FilterCheck(name="ateco", status=CheckStatus.FAILED, detail=detail)
    if level == AtecoMatchLevel.UNVERIFIABLE:
        return FilterCheck(name="ateco", status=CheckStatus.UNVERIFIABLE, detail=detail)
    return FilterCheck(name="ateco", status=CheckStatus.PASSED, detail=detail)


def _check_age_requirement(profile: CompanyProfile) -> FilterCheck:
    # incentivi.gov.it publishes no structured minimum/maximum company-age field
    # (see docs/sources.md) - this can never be more than "unverifiable".
    age = profile.age_years()
    detail = "El origen no publica requisitos de antigüedad estructurados"
    if age is not None:
        detail += f" (antigüedad del perfil: {age:.1f} años, verificar en la fuente oficial)"
    return FilterCheck(name="age_requirement", status=CheckStatus.UNVERIFIABLE, detail=detail)


def _check_municipalities(incentive: Incentive) -> FilterCheck | None:
    if not incentive.municipalities:
        return None
    return FilterCheck(
        name="municipalities",
        status=CheckStatus.UNVERIFIABLE,
        detail=(
            f"Restringido a {len(incentive.municipalities)} comune(s) específico(s); "
            "no hay mapeo comune→provincia para verificarlo automáticamente"
        ),
    )


def _check_special_territory(incentive: Incentive) -> FilterCheck | None:
    if not incentive.special_territory:
        return None
    return FilterCheck(
        name="special_territory",
        status=CheckStatus.UNVERIFIABLE,
        detail=f"Requiere ámbito territorial especial ({', '.join(incentive.special_territory)}), no modelado en el perfil",
    )


def apply_hard_filters(incentive: Incentive, profile: CompanyProfile, as_of: date | None = None) -> HardFilterResult:
    today = as_of or date.today()
    checks = [
        _check_status(incentive, today),
        _check_region(incentive, profile),
        _check_size(incentive, profile),
        _check_beneficiary_type(incentive, profile),
        _check_ateco(incentive, profile),
        _check_age_requirement(profile),
    ]
    checks.extend(c for c in (_check_municipalities(incentive), _check_special_territory(incentive)) if c is not None)

    eligible = all(c.status != CheckStatus.FAILED for c in checks)
    return HardFilterResult(eligible=eligible, checks=checks)
