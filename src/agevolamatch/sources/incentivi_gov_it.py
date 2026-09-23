"""Source for incentivi.gov.it Open Data (IODL 2.0 license).

The site has no documented public API: the "Scarica JSON/CSV" buttons on
https://www.incentivi.gov.it/it/open-data trigger a client-side call to an
embedded Solr backend. This was reverse-engineered from the site's own JS
bundle (main.min.js) on 2026-09-23 - see docs/sources.md for the full field
mapping and how it was found. We call the same endpoint directly rather than
scraping HTML, per the project's "prefer official APIs over scraping" rule.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

from agevolamatch.models.enums import OpportunitySourceName
from agevolamatch.models.opportunity import Incentive
from agevolamatch.sources.base import BaseSource
from agevolamatch.sources.http_cache import CachedHttpClient
from agevolamatch.sources.http_client import RateLimitedHttpClient
from agevolamatch.sources.parsing import (
    compute_content_hash,
    compute_status,
    parse_ateco,
    parse_iso_datetime,
    parse_italian_money,
)

logger = logging.getLogger(__name__)

SOLR_ENDPOINT = "https://www.incentivi.gov.it/solr/coredrupal/select"
SOLR_INDEX = "incentivi"
USER_AGENT = "AgevolaMatch/0.1 (+https://github.com/shagga75/agevolamatch; open-source incentive matcher)"

# Alias (our field name) -> internal Solr field, as used by incentivi.gov.it's own
# "Scarica JSON" export (aliases_file in the site's main.min.js bundle).
FIELD_ALIASES: dict[str, str] = {
    "ID_Incentivo": "zs_nid",
    "Titolo": "zs_title",
    "Descrizione": "zs_body",
    "Obiettivo_Finalita": "zm_field_scopes_value",
    "Data_apertura": "zs_field_open_date",
    "Data_chiusura": "zs_field_close_date",
    "Note_di_apertura_chiusura": "zs_field_close_date_descriptor",
    "Dimensioni": "zm_field_dimensions_value",
    "Tipologia_Soggetto": "zm_field_subject_type_value",
    "Forma_agevolazione": "zm_field_support_form_value",
    "Costi_Ammessi": "zm_field_granted_costs_value",
    "Spesa_Ammessa_min": "zs_field_cost_min",
    "Spesa_Ammessa_max": "zs_field_cost_max",
    "Agevolazione_Concedibile_min": "zs_field_support_grant_type_min",
    "Agevolazione_Concedibile_max": "zs_field_support_grant_type_max",
    "Settore_Attivita": "zm_field_activity_sector_value",
    "Codici_ATECO": "zs_field_ateco",
    "Regioni": "zm_field_regions_value",
    "Comuni": "zs_field_comuni",
    "Ambito_territoriale": "zm_field_special_territory_value",
    "Soggetto_Concedente": "zs_field_subject_grant",
    "Base_normativa_primaria": "zs_field_primary_ruleset",
    "Base_normativa_secondaria": "zs_field_secondary_ruleset",
    "Provvedimento_attuativo": "zs_field_implementation_ruleset",
    "Gazzetta_ufficiale": "zs_field_official_references",
    "Stanziamento_incentivo": "zs_field_budget_allocation",
    "Link_istituzionale": "zs_field_link",
    "Altre_caratteristiche": "zs_field_other_characteristic",
    "Data_ultimo_aggiornamento": "ds_last_update",
}

STARTUP_OR_PMI_INNOVATIVA = "Impresa - SU/PMI innovativa"


def _build_fl_param() -> str:
    return ",".join(f"{alias}:{field}" for alias, field in FIELD_ALIASES.items())


def build_query_url(rows: int, start: int = 0) -> str:
    params = {
        "q.op": "OR",
        "wt": "json",
        "rows": str(rows),
        "start": str(start),
        "fl": _build_fl_param(),
        "q": f"index_id:{SOLR_INDEX}",
    }
    return f"{SOLR_ENDPOINT}?{urlencode(params)}"


@dataclass
class IncentiviGovItSource(BaseSource):
    """fetch() paginates the Solr endpoint; parse() flattens pages into records;
    normalize() maps one Solr document to an Incentive."""

    name: str = OpportunitySourceName.INCENTIVI_GOV_IT.value
    page_size: int = 2000
    http: RateLimitedHttpClient = field(
        default_factory=lambda: RateLimitedHttpClient(user_agent=USER_AGENT, http_cache=CachedHttpClient())
    )

    def fetch(self) -> list[dict[str, Any]]:
        """Paginates through the Solr endpoint and returns all raw documents."""
        docs: list[dict[str, Any]] = []
        start = 0
        num_found = None
        while num_found is None or start < num_found:
            url = build_query_url(rows=self.page_size, start=start)
            payload = json.loads(self.http.get(url))
            response = payload["response"]
            num_found = response["numFound"]
            page_docs = response["docs"]
            docs.extend(page_docs)
            if not page_docs:
                break
            start += len(page_docs)
        return docs

    def parse(self, raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return raw

    def normalize(self, record: dict[str, Any]) -> Incentive:
        source_id = str(record["ID_Incentivo"])
        open_date = parse_iso_datetime(record.get("Data_apertura"))
        close_date = parse_iso_datetime(record.get("Data_chiusura"))
        source_last_updated = parse_iso_datetime(record.get("Data_ultimo_aggiornamento"))
        status = compute_status(open_date, close_date)

        ateco_codes, ateco_all_sectors = parse_ateco(record.get("Codici_ATECO"))
        beneficiary_types = record.get("Tipologia_Soggetto", [])

        now = datetime.now(tz=UTC)

        fields_for_hash = {
            "source": OpportunitySourceName.INCENTIVI_GOV_IT.value,
            "source_id": source_id,
            "title": record.get("Titolo"),
            "description": record.get("Descrizione"),
            "url": record.get("Link_istituzionale"),
            "open_date": open_date,
            "close_date": close_date,
            "granting_body": record.get("Soggetto_Concedente"),
            "scope": record.get("Obiettivo_Finalita", []),
            "beneficiary_types": beneficiary_types,
            "company_sizes": record.get("Dimensioni", []),
            "support_forms": record.get("Forma_agevolazione", []),
            "eligible_costs": record.get("Costi_Ammessi", []),
            "activity_sectors": record.get("Settore_Attivita", []),
            "ateco_raw": record.get("Codici_ATECO"),
            "regions": record.get("Regioni", []),
            "municipalities": record.get("Comuni"),
            "special_territory": record.get("Ambito_territoriale", []),
            "cost_min": _to_float(record.get("Spesa_Ammessa_min")),
            "cost_max": _to_float(record.get("Spesa_Ammessa_max")),
            "grant_min": _to_float(record.get("Agevolazione_Concedibile_min")),
            "grant_max": _to_float(record.get("Agevolazione_Concedibile_max")),
            "budget_allocation_raw": record.get("Stanziamento_incentivo"),
            "primary_legal_basis": record.get("Base_normativa_primaria"),
            "secondary_legal_basis": record.get("Base_normativa_secondaria"),
            "implementation_ruling": record.get("Provvedimento_attuativo"),
            "official_gazette_ref": record.get("Gazzetta_ufficiale"),
            "other_characteristics": record.get("Altre_caratteristiche"),
            "close_date_note": record.get("Note_di_apertura_chiusura"),
        }
        content_hash = compute_content_hash(fields_for_hash)

        return Incentive(
            source=OpportunitySourceName.INCENTIVI_GOV_IT,
            source_id=source_id,
            title=record["Titolo"],
            description=record.get("Descrizione"),
            url=record.get("Link_istituzionale"),
            open_date=open_date,
            close_date=close_date,
            status=status,
            content_hash=content_hash,
            first_seen=now,
            last_seen_at=now,
            source_last_updated=source_last_updated,
            granting_body=record.get("Soggetto_Concedente"),
            scope=record.get("Obiettivo_Finalita", []),
            beneficiary_types=beneficiary_types,
            startup_or_pmi_innovativa_ambiguous=STARTUP_OR_PMI_INNOVATIVA in beneficiary_types,
            company_sizes=record.get("Dimensioni", []),
            support_forms=record.get("Forma_agevolazione", []),
            eligible_costs=record.get("Costi_Ammessi", []),
            activity_sectors=record.get("Settore_Attivita", []),
            ateco_codes=ateco_codes,
            ateco_all_sectors=ateco_all_sectors,
            ateco_raw=record.get("Codici_ATECO"),
            regions=record.get("Regioni", []),
            municipalities=_split_municipalities(record.get("Comuni")),
            special_territory=record.get("Ambito_territoriale", []),
            cost_min=_to_float(record.get("Spesa_Ammessa_min")),
            cost_max=_to_float(record.get("Spesa_Ammessa_max")),
            grant_min=_to_float(record.get("Agevolazione_Concedibile_min")),
            grant_max=_to_float(record.get("Agevolazione_Concedibile_max")),
            budget_allocation_raw=record.get("Stanziamento_incentivo"),
            budget_allocation_amount=parse_italian_money(record.get("Stanziamento_incentivo")),
            primary_legal_basis=record.get("Base_normativa_primaria"),
            secondary_legal_basis=record.get("Base_normativa_secondaria"),
            implementation_ruling=record.get("Provvedimento_attuativo"),
            official_gazette_ref=record.get("Gazzetta_ufficiale"),
            other_characteristics=record.get("Altre_caratteristiche"),
            close_date_note=record.get("Note_di_apertura_chiusura"),
        )


def _to_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _split_municipalities(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    return [m.strip() for m in raw.split(";") if m.strip()]


__all__ = ["IncentiviGovItSource", "build_query_url"]
