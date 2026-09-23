"""Source for TED (Tenders Electronic Daily) - the EU's official public
procurement portal. Uses the public Search API (POST /v3/notices/search),
confirmed live to require no authentication for published notices.

Field names, response shape, and the unusual date format ('2026-09-01+02:00',
a date with a UTC offset but no time - see sources/parsing.py::parse_ted_date)
were all confirmed against the live API on 2026-09-23, not assumed from
documentation, which does not publish an exact field/schema reference.
notice-title and buyer-name are multi-language dicts (one key per ISO 639-2
language actually used in that notice) - _pick_language_value below prefers
Italian, then English, then whatever is available.

Scoped to notice-type=cn-standard (standard contract notices - i.e. actual
open calls, not prior-information or award notices) and buyer-country=ITA
(Italian contracting authorities - EU tenders are open to bidders from any
member state, but this keeps the source's scope aligned with the rest of the
project's Italy focus). Queries a rolling recent-publication window rather
than the full archive (128k+ total notices for Italy alone) - see
docs/sources.md.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from agevolamatch.models.enums import OpportunitySourceName
from agevolamatch.models.opportunity import Tender
from agevolamatch.sources.base import BaseSource
from agevolamatch.sources.parsing import compute_content_hash, compute_status, parse_ted_date

SEARCH_URL = "https://api.ted.europa.eu/v3/notices/search"
USER_AGENT = "AgevolaMatch/0.1 (+https://github.com/shagga75/agevolamatch; open-source tender matcher)"

FIELDS = [
    "publication-number",
    "notice-title",
    "buyer-name",
    "buyer-country",
    "publication-date",
    "classification-cpv",
    "deadline-receipt-tender-date-lot",
    "estimated-value-lot",
    "estimated-value-cur-lot",
    "notice-type",
]


def _pick_language_value(data: dict[str, Any] | None, preferred: tuple[str, ...] = ("ita", "eng")) -> str | None:
    """notice-title/buyer-name are keyed by 3-letter language code, value is
    either a plain string (notice-title) or a list of strings (buyer-name)."""
    if not data:
        return None
    for lang in preferred:
        if lang in data:
            value = data[lang]
            return value[0] if isinstance(value, list) else value
    for value in data.values():
        return value[0] if isinstance(value, list) else value
    return None


def _pick_url(links: dict[str, Any] | None) -> str | None:
    if not links:
        return None
    html_direct = links.get("htmlDirect") or {}
    for lang in ("ITA", "ENG"):
        if lang in html_direct:
            return html_direct[lang]
    return next(iter(html_direct.values()), None)


def _to_float(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _earliest_date(values: list[str] | None) -> datetime | None:
    parsed = [d for v in (values or []) if (d := parse_ted_date(v)) is not None]
    return min(parsed) if parsed else None


@dataclass
class TEDSource(BaseSource):
    """parse() is the identity function - the search API already returns one
    dict per notice, there's no separate raw-payload shape to flatten."""

    name: str = OpportunitySourceName.TED_EUROPA.value
    lookback_days: int = 60
    page_size: int = 50
    max_pages: int = 100
    timeout_seconds: float = 30.0
    min_request_interval_seconds: float = 1.0
    max_retries_on_rate_limit: int = 3
    _last_request_at: float = field(default=0.0, init=False, repr=False)

    def _rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        wait = self.min_request_interval_seconds - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_request_at = time.monotonic()

    def _post(self, query: str, page: int) -> dict[str, Any]:
        """Confirmed live: the public (unauthenticated) API does enforce a
        rate limit and returns 429 - retried here with the server's own
        Retry-After when given, else exponential backoff, rather than
        failing the whole ingest run over a transient limit."""
        for attempt in range(self.max_retries_on_rate_limit + 1):
            self._rate_limit()
            response = httpx.post(
                SEARCH_URL,
                headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
                json={"query": query, "fields": FIELDS, "page": page, "limit": self.page_size},
                timeout=self.timeout_seconds,
            )
            if response.status_code == 429 and attempt < self.max_retries_on_rate_limit:
                retry_after = float(response.headers.get("Retry-After", 2**attempt))
                time.sleep(retry_after)
                continue
            response.raise_for_status()
            return response.json()
        raise RuntimeError("unreachable")  # loop always returns or raises above

    def fetch(self) -> list[dict[str, Any]]:
        since = (datetime.now(tz=UTC).date() - timedelta(days=self.lookback_days)).strftime("%Y%m%d")
        query = f"buyer-country=ITA AND notice-type=cn-standard AND publication-date>={since}"

        notices: list[dict[str, Any]] = []
        for page in range(1, self.max_pages + 1):
            payload = self._post(query, page)
            batch = payload.get("notices", [])
            notices.extend(batch)
            if len(batch) < self.page_size:
                break
        return notices

    def parse(self, raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return raw

    def normalize(self, record: dict[str, Any]) -> Tender:
        publication_number = record["publication-number"]
        title = _pick_language_value(record.get("notice-title")) or publication_number
        buyer_name = _pick_language_value(record.get("buyer-name"))
        buyer_country = next(iter(record.get("buyer-country") or []), None)
        publication_date = parse_ted_date(record.get("publication-date"))
        close_date = _earliest_date(record.get("deadline-receipt-tender-date-lot"))
        status = compute_status(publication_date, close_date)

        cpv_codes = sorted(set(record.get("classification-cpv") or []))
        estimated_values = record.get("estimated-value-lot") or []
        estimated_value = _to_float(estimated_values[0]) if estimated_values else None
        currencies = record.get("estimated-value-cur-lot") or []
        currency = currencies[0] if currencies else None
        notice_type = record.get("notice-type")
        url = _pick_url(record.get("links"))

        now = datetime.now(tz=UTC)
        fields_for_hash = {
            "source": OpportunitySourceName.TED_EUROPA.value,
            "source_id": publication_number,
            "title": title,
            "url": url,
            "open_date": publication_date,
            "close_date": close_date,
            "buyer_name": buyer_name,
            "buyer_country": buyer_country,
            "cpv_codes": cpv_codes,
            "notice_type": notice_type,
            "estimated_value": estimated_value,
            "estimated_value_currency": currency,
        }
        content_hash = compute_content_hash(fields_for_hash)

        return Tender(
            source=OpportunitySourceName.TED_EUROPA,
            source_id=publication_number,
            title=title,
            url=url,
            open_date=publication_date,
            close_date=close_date,
            status=status,
            content_hash=content_hash,
            first_seen=now,
            last_seen_at=now,
            buyer_name=buyer_name,
            buyer_country=buyer_country,
            cpv_codes=cpv_codes,
            notice_type=notice_type,
            estimated_value=estimated_value,
            estimated_value_currency=currency,
        )
