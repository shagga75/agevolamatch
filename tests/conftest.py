from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def incentivi_gov_it_raw_docs() -> list[dict]:
    payload = json.loads((FIXTURES_DIR / "incentivi_gov_it_sample.json").read_text(encoding="utf-8"))
    return payload["response"]["docs"]
