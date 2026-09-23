"""Common base model for anything a company can apply to: incentives today,
tenders (gare d'appalto) in Fase 5. Matching and alerting operate on this base
so both domains can share the same pipeline without mixing their fields."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from agevolamatch.models.enums import OpportunitySourceName, OpportunityStatus


class Opportunity(BaseModel):
    """Fields shared by every kind of funding/procurement opportunity."""

    model_config = ConfigDict(extra="forbid")

    source: OpportunitySourceName
    source_id: str = Field(description="Identifier assigned by the origin system, e.g. the Drupal nid")
    title: str
    description: str | None = None
    url: str | None = None

    open_date: datetime | None = None
    close_date: datetime | None = None
    status: OpportunityStatus = OpportunityStatus.UNKNOWN

    content_hash: str = Field(description="sha256 of the normalized payload, used to detect changes")
    first_seen: datetime
    last_seen_at: datetime
    source_last_updated: datetime | None = Field(
        default=None, description="Origin system's own last-modified timestamp, when available"
    )


class Incentive(Opportunity):
    """An Italian public incentive (finanza agevolata) - subtype of Opportunity."""

    granting_body: str | None = Field(default=None, description="Soggetto_Concedente")

    scope: list[str] = Field(default_factory=list, description="Obiettivo_Finalita")
    beneficiary_types: list[str] = Field(default_factory=list, description="Tipologia_Soggetto")
    startup_or_pmi_innovativa_ambiguous: bool = Field(
        default=False,
        description=(
            "True when beneficiary_types includes the source's combined "
            "'SU/PMI innovativa' value, which cannot be split into "
            "startup innovativa vs PMI innovativa."
        ),
    )
    company_sizes: list[str] = Field(default_factory=list, description="Dimensioni")
    support_forms: list[str] = Field(default_factory=list, description="Forma_agevolazione")
    eligible_costs: list[str] = Field(default_factory=list, description="Costi_Ammessi")
    activity_sectors: list[str] = Field(
        default_factory=list, description="Settore_Attivita (informative, not authoritative for filtering)"
    )

    ateco_codes: list[str] | None = Field(default=None, description="Parsed codes when Codici_ATECO has any")
    ateco_all_sectors: bool = Field(
        default=False, description="True when Codici_ATECO is the 'all sectors eligible' free-text pattern"
    )
    ateco_raw: str | None = Field(default=None, description="Unparsed Codici_ATECO for auditing")

    regions: list[str] = Field(default_factory=list, description="Regioni")
    municipalities: list[str] | None = Field(
        default=None, description="Comuni - free-text municipality names, no ISTAT codes in the source"
    )
    special_territory: list[str] = Field(default_factory=list, description="Ambito_territoriale")

    cost_min: float | None = Field(default=None, description="Spesa_Ammessa_min")
    cost_max: float | None = Field(default=None, description="Spesa_Ammessa_max")
    grant_min: float | None = Field(default=None, description="Agevolazione_Concedibile_min")
    grant_max: float | None = Field(default=None, description="Agevolazione_Concedibile_max")

    budget_allocation_raw: str | None = Field(default=None, description="Stanziamento_incentivo, verbatim")
    budget_allocation_amount: float | None = Field(
        default=None, description="Best-effort numeric parse of budget_allocation_raw; never used for hard filters"
    )

    primary_legal_basis: str | None = Field(default=None, description="Base_normativa_primaria")
    secondary_legal_basis: str | None = Field(default=None, description="Base_normativa_secondaria")
    implementation_ruling: str | None = Field(default=None, description="Provvedimento_attuativo")
    official_gazette_ref: str | None = Field(default=None, description="Gazzetta_ufficiale")
    other_characteristics: str | None = Field(default=None, description="Altre_caratteristiche")
    close_date_note: str | None = Field(default=None, description="Note_di_apertura_chiusura")


class Tender(Opportunity):
    """A public tender / gara d'appalto - subtype of Opportunity, fed by ANAC
    (Italian national data) and TED (EU-wide official API). See
    docs/sources.md for the real field mapping from each source - the two
    sources overlap only partially, so most fields here are optional and a
    given Tender will usually have either the ANAC-specific fields (cig,
    province, outcome) or the TED-specific ones (buyer_country, notice_type)
    populated, not both.
    """

    buyer_name: str | None = Field(default=None, description="Contracting authority / stazione appaltante")
    buyer_country: str | None = Field(default=None, description="ISO 3166-1 alpha-3, e.g. 'ITA' (TED only)")
    province: str | None = Field(default=None, description="Italian province name, e.g. 'ROMA' (ANAC only)")

    cpv_codes: list[str] = Field(
        default_factory=list, description="EU procurement classification codes (Common Procurement Vocabulary)"
    )
    contract_type: str | None = Field(
        default=None, description="LAVORI/SERVIZI/FORNITURE (works/services/supplies) - ANAC only"
    )
    procedure_type: str | None = Field(default=None, description="Tender procedure, e.g. open/negotiated")
    notice_type: str | None = Field(default=None, description="eForms notice type, e.g. 'cn-standard' - TED only")

    estimated_value: float | None = Field(default=None, description="Estimated/lot contract value")
    estimated_value_currency: str | None = Field(default=None, description="ISO 4217 currency code")

    outcome: str | None = Field(
        default=None, description="Award outcome when already decided (esito) - ANAC only, informational"
    )
    cig: str | None = Field(default=None, description="Codice Identificativo Gara - ANAC's unique tender ID")
