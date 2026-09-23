"""Company profile a user maintains to be matched against opportunities.

Unlike Opportunity/Incentive, none of this is sourced from incentivi.gov.it -
the open data feed carries no company registry information. Profiles are
authored by hand (YAML) or eventually pulled from a registry integration.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agevolamatch.models.enums import AtecoVersion, CompanySize, LegalForm, Region


class AtecoCode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(description="e.g. '62.01' or '62.01.00'")
    version: AtecoVersion = AtecoVersion.ATECO_2025

    @field_validator("code")
    @classmethod
    def _normalize(cls, v: str) -> str:
        return v.strip()


class CompanyProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    ateco_codes: list[AtecoCode] = Field(default_factory=list)
    region: Region
    province: str | None = Field(default=None, description="Sigla provincia, e.g. 'RM', or full name")
    size: CompanySize
    founded_on: date | None = None
    legal_form: LegalForm | None = None

    is_startup_innovativa: bool = False
    is_pmi_innovativa: bool = False
    is_impresa_femminile: bool = False
    is_under_35: bool = False

    planned_expense_types: list[str] = Field(
        default_factory=list, description="Values matching EligibleCost, expenses the company plans to incur"
    )
    planned_investment_amount: float | None = Field(
        default=None, description="Amount in EUR the company plans to invest/spend"
    )
    preferred_support_forms: list[str] = Field(
        default_factory=list, description="Values matching SupportForm, ranked by preference for scoring"
    )

    cpv_codes: list[str] = Field(
        default_factory=list,
        description=(
            "CPV (Common Procurement Vocabulary) codes for tender matching (Fase 5, gare/tenders) - "
            "a separate classification from ateco_codes, which is for incentives only. No official "
            "ATECO<->CPV crosswalk exists, so this is set independently, not derived from ateco_codes."
        ),
    )

    def age_years(self, as_of: date | None = None) -> float | None:
        if self.founded_on is None:
            return None
        reference = as_of or date.today()
        return (reference - self.founded_on).days / 365.25
