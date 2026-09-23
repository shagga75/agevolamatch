from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from agevolamatch.models.enums import OpportunitySourceName, OpportunityStatus
from agevolamatch.models.opportunity import Incentive

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def incentivi_gov_it_raw_docs() -> list[dict]:
    payload = json.loads((FIXTURES_DIR / "incentivi_gov_it_sample.json").read_text(encoding="utf-8"))
    return payload["response"]["docs"]


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
