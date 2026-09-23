from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from agevolamatch.models.enums import OpportunitySourceName, OpportunityStatus
from agevolamatch.models.opportunity import Incentive, Tender

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def incentivi_gov_it_raw_docs() -> list[dict]:
    payload = json.loads((FIXTURES_DIR / "incentivi_gov_it_sample.json").read_text(encoding="utf-8"))
    return payload["response"]["docs"]


@pytest.fixture
def invitalia_listing_page0_html() -> str:
    return (FIXTURES_DIR / "invitalia_listing_page0.html").read_text(encoding="utf-8")


@pytest.fixture
def invitalia_listing_page_chiuso_html() -> str:
    return (FIXTURES_DIR / "invitalia_listing_page_chiuso.html").read_text(encoding="utf-8")


def make_incentive(source_id: str = "1", **overrides: Any) -> Incentive:
    """Builds a minimal valid Incentive for tests, with sane defaults that
    match the "generic open incentive for any Impresa" case, overridable per
    test so each test only sets the fields it actually cares about."""
    now = datetime.now(tz=UTC)
    defaults: dict[str, Any] = {
        "source": OpportunitySourceName.INCENTIVI_GOV_IT,
        "source_id": source_id,
        "title": f"Incentivo di test {source_id}",
        "status": OpportunityStatus.OPEN,
        "open_date": datetime(2024, 1, 1, tzinfo=UTC),
        "close_date": datetime(2099, 1, 1, tzinfo=UTC),
        "content_hash": f"hash-{source_id}",
        "first_seen": now,
        "last_seen_at": now,
        "beneficiary_types": ["Impresa"],
        "company_sizes": ["Microimpresa", "Piccola Impresa", "Media Impresa"],
        "regions": ["Lazio"],
        "eligible_costs": ["Costo del personale", "Servizi, brevetti e licenze"],
        "support_forms": ["Contributo/Fondo perduto"],
        "scope": [],
        "ateco_all_sectors": True,
    }
    defaults.update(overrides)
    return Incentive(**defaults)


@pytest.fixture
def incentive_factory():
    return make_incentive


@pytest.fixture
def startup_profile():
    from agevolamatch.matching.profile_loader import load_company_profile

    path = Path(__file__).parent.parent / "examples" / "startup_profile.yaml"
    return load_company_profile(path)


@pytest.fixture
def anac_cig_raw_rows() -> list[dict]:
    with (FIXTURES_DIR / "anac_cig_sample.csv").open(encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter=";", quotechar='"'))


@pytest.fixture
def ted_notices_raw() -> list[dict]:
    payload = json.loads((FIXTURES_DIR / "ted_notices_sample.json").read_text(encoding="utf-8"))
    return payload["notices"]


def make_tender(source_id: str = "T1", **overrides: Any) -> Tender:
    now = datetime.now(tz=UTC)
    defaults: dict[str, Any] = {
        "source": OpportunitySourceName.ANAC,
        "source_id": source_id,
        "title": f"Gara di test {source_id}",
        "status": OpportunityStatus.OPEN,
        "open_date": datetime(2024, 1, 1, tzinfo=UTC),
        "close_date": datetime(2099, 1, 1, tzinfo=UTC),
        "content_hash": f"hash-{source_id}",
        "first_seen": now,
        "last_seen_at": now,
        "cpv_codes": ["72200000"],
    }
    defaults.update(overrides)
    return Tender(**defaults)


@pytest.fixture
def tender_factory():
    return make_tender
