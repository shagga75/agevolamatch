"""Scraper for invitalia.it's business incentives listing (no public API -
confirmed by checking for a JSON:API endpoint, which 404s; robots.txt allows
crawling this content, checked 2026-09-23).

Individual measure detail pages (/incentivi-e-strumenti/<slug>) are long-form
free-text content (Drupal Paragraphs: "A CHI SI RIVOLGE", "COSA FINANZIA", ...)
with no structured dates/region/ATECO/size fields - unlike incentivi.gov.it,
there's nothing reliable to extract there. This source only scrapes the
listing page's card summaries (title, url, short description, status label).
Every other Incentive field is left empty; the matching engine's hard filters
already treat missing fields as "unverifiable", not disqualifying, so this
degrades gracefully rather than needing special-casing downstream.

Many Invitalia measures are also on incentivi.gov.it under a different exact
title - see sources/dedup.py for how the ingest pipeline filters those out
before storing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from bs4 import BeautifulSoup

from agevolamatch.models.enums import OpportunitySourceName, OpportunityStatus
from agevolamatch.models.opportunity import Incentive
from agevolamatch.sources.base import BaseSource
from agevolamatch.sources.http_cache import CachedHttpClient
from agevolamatch.sources.http_client import RateLimitedHttpClient
from agevolamatch.sources.parsing import compute_content_hash

BASE_URL = "https://www.invitalia.it"
LISTING_PATH = "/per-le-imprese/incentivi-e-strumenti"
USER_AGENT = "AgevolaMatch/0.1 (+https://github.com/shagga75/agevolamatch; open-source incentive matcher)"

STATUS_LABELS: dict[str, OpportunityStatus] = {
    "attivo": OpportunityStatus.OPEN,
    "chiuso": OpportunityStatus.CLOSED,
    "in apertura": OpportunityStatus.UPCOMING,
}


def parse_listing_page(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    cards = []
    for article in soup.select("article.card--incentivi"):
        title_tag = article.select_one("h3 a.card-unified__title")
        if title_tag is None:
            continue
        description_tag = article.select_one("p.fw-normal")
        status_tag = article.select_one(".category-top .category")
        cards.append(
            {
                "url": (title_tag.get("href") or "").strip(),
                "title": title_tag.get_text(strip=True),
                "description": description_tag.get_text(strip=True) if description_tag else None,
                "status_label": status_tag.get_text(strip=True).lower() if status_tag else "",
            }
        )
    return cards


@dataclass
class InvitaliaSource(BaseSource):
    name: str = OpportunitySourceName.INVITALIA.value
    max_pages: int = 30
    http: RateLimitedHttpClient = field(
        default_factory=lambda: RateLimitedHttpClient(user_agent=USER_AGENT, http_cache=CachedHttpClient())
    )

    def fetch(self) -> list[str]:
        pages: list[str] = []
        for page_num in range(self.max_pages):
            url = f"{BASE_URL}{LISTING_PATH}?page={page_num}"
            html = self.http.get(url)
            if not parse_listing_page(html):
                break
            pages.append(html)
        return pages

    def parse(self, raw: list[str]) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        for html in raw:
            for card in parse_listing_page(html):
                if card["url"] and card["url"] not in seen_urls:
                    seen_urls.add(card["url"])
                    records.append(card)
        return records

    def normalize(self, record: dict[str, Any]) -> Incentive:
        url = record["url"]
        if url.startswith("/"):
            url = f"{BASE_URL}{url}"
        slug = record["url"].rstrip("/").split("/")[-1]
        status = STATUS_LABELS.get(record["status_label"], OpportunityStatus.UNKNOWN)
        now = datetime.now(tz=UTC)

        content_hash = compute_content_hash(
            {
                "source": OpportunitySourceName.INVITALIA.value,
                "source_id": slug,
                "title": record["title"],
                "description": record.get("description"),
                "url": url,
                "status": status.value,
            }
        )

        return Incentive(
            source=OpportunitySourceName.INVITALIA,
            source_id=slug,
            title=record["title"],
            description=record.get("description"),
            url=url,
            status=status,
            content_hash=content_hash,
            first_seen=now,
            last_seen_at=now,
        )
