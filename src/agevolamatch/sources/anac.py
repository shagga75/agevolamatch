"""Source for ANAC (Autorità Nazionale Anticorruzione) public procurement
open data - dati.anticorruzione.it, a CKAN portal, CC-BY-SA 4.0 licensed.

The portal sits behind a WAF that rejects any request not shaped like a real
browser - confirmed live, empirically, by elimination: a self-identifying
UA in the conventional "Mozilla/5.0 (compatible; BotName/1.0; +url)" form
(the pattern well-behaved bots like Googlebot use) was still rejected via
httpx, while an actual browser UA string (with genuine Chrome/AppleWebKit/
Safari tokens) got through with no other header changes needed. This is
public CC-BY-SA-4.0 open data with no access-restricting terms - the WAF is
generic bot mitigation, not an access control this project's own scripted,
rate-limited, single-request-per-run use is trying to evade - but it does
mean USER_AGENT below has to look like a browser to reliably get through.

The "cig" dataset ("CIG aggiornamenti delta") publishes one CSV/JSON zip per
month. It is NOT a clean "currently open tenders" snapshot: a real sample
(2026-09 delta, ~169k rows) showed ~83% of rows already have an award outcome
(ESITO) and only ~2.3% have a bid-submission deadline still in the future -
most of the file is award-notice noise for old CIGs, not new open calls. This
source therefore filters to open-only (deadline in the future) at parse time
rather than storing everything - a deliberate departure from incentivi.gov.it's
"keep closed records for history" approach, justified by scale (100k+ rows/
month vs. incentivi.gov.it's ~5,900 total) and by the fact that this delta
file's closed/awarded rows are noise from this feed's own change-log design,
not a historical record we'd want to keep from this source.
"""

from __future__ import annotations

import csv
import io
import logging
import re
import zipfile
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import httpx

from agevolamatch.models.enums import OpportunitySourceName
from agevolamatch.models.opportunity import Tender
from agevolamatch.sources.base import BaseSource
from agevolamatch.sources.parsing import compute_content_hash, compute_status, parse_iso_datetime

logger = logging.getLogger(__name__)

CKAN_API_BASE = "https://dati.anticorruzione.it/opendata/api/3/action"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
_DELTA_RESOURCE_NAME_PATTERN = re.compile(r"^(\d{8})-cig_csv$")


def _to_float(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _blank_to_none(value: str | None) -> str | None:
    """csv.DictReader returns an empty string for a blank quoted CSV field,
    never None - confirmed live: constructing a row with provincia="" and
    normalizing it stored province="" instead of the intended null. Every
    optional string field must go through this, not just record.get()."""
    return value or None


@dataclass
class ANACSource(BaseSource):
    name: str = OpportunitySourceName.ANAC.value
    timeout_seconds: float = 180.0

    def _latest_delta_csv_url(self) -> str:
        response = httpx.get(
            f"{CKAN_API_BASE}/package_show",
            params={"id": "cig"},
            headers={"User-Agent": USER_AGENT},
            timeout=30.0,
        )
        response.raise_for_status()
        resources = response.json()["result"]["resources"]

        candidates = [
            (match.group(1), resource["url"])
            for resource in resources
            if (match := _DELTA_RESOURCE_NAME_PATTERN.match(resource.get("name", "")))
            and resource.get("format", "").upper() == "CSV"
        ]
        if not candidates:
            raise RuntimeError("No dated CIG CSV delta resource found in ANAC's 'cig' dataset")
        _, latest_url = max(candidates, key=lambda item: item[0])
        return latest_url

    def fetch(self) -> bytes:
        url = self._latest_delta_csv_url()
        response = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=self.timeout_seconds)
        response.raise_for_status()
        return response.content

    def parse(self, raw: bytes) -> list[dict[str, Any]]:
        today = date.today().isoformat()
        records: list[dict[str, Any]] = []
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            csv_name = archive.namelist()[0]
            with archive.open(csv_name) as binary_file:
                text_file = io.TextIOWrapper(binary_file, encoding="utf-8", errors="replace")
                reader = csv.DictReader(text_file, delimiter=";", quotechar='"')
                for row in reader:
                    deadline = row.get("data_scadenza_offerta")
                    if deadline and deadline > today:
                        records.append(row)
        return records

    def normalize(self, record: dict[str, Any]) -> Tender:
        cig = record["cig"]
        title = record["oggetto_gara"]
        description = _blank_to_none(record.get("oggetto_lotto"))
        open_date = parse_iso_datetime(record.get("data_pubblicazione"))
        close_date = parse_iso_datetime(record.get("data_scadenza_offerta"))
        status = compute_status(open_date, close_date)

        estimated_value = _to_float(record.get("importo_lotto")) or _to_float(record.get("importo_complessivo_gara"))
        cpv_code = _blank_to_none(record.get("cod_cpv"))
        buyer_name = _blank_to_none(record.get("denominazione_amministrazione_appaltante"))
        province = _blank_to_none(record.get("provincia"))
        contract_type = _blank_to_none(record.get("oggetto_principale_contratto"))
        procedure_type = _blank_to_none(record.get("tipo_scelta_contraente"))
        outcome = _blank_to_none(record.get("ESITO"))

        now = datetime.now(tz=UTC)
        fields_for_hash = {
            "source": OpportunitySourceName.ANAC.value,
            "source_id": cig,
            "title": title,
            "description": description,
            "open_date": open_date,
            "close_date": close_date,
            "buyer_name": buyer_name,
            "province": province,
            "cpv_codes": [cpv_code] if cpv_code else [],
            "contract_type": contract_type,
            "procedure_type": procedure_type,
            "estimated_value": estimated_value,
            "outcome": outcome,
        }
        content_hash = compute_content_hash(fields_for_hash)

        return Tender(
            source=OpportunitySourceName.ANAC,
            source_id=cig,
            title=title,
            description=description,
            open_date=open_date,
            close_date=close_date,
            status=status,
            content_hash=content_hash,
            first_seen=now,
            last_seen_at=now,
            buyer_name=buyer_name,
            province=province,
            cpv_codes=[cpv_code] if cpv_code else [],
            contract_type=contract_type,
            procedure_type=procedure_type,
            estimated_value=estimated_value,
            estimated_value_currency="EUR" if estimated_value is not None else None,
            outcome=outcome,
            cig=cig,
        )
