"""Regenerates schemas/*.json from the Pydantic models. Run after changing any model."""

from __future__ import annotations

import json
from pathlib import Path

from agevolamatch.matching.models import MatchResult
from agevolamatch.models.company_profile import CompanyProfile
from agevolamatch.models.opportunity import Incentive, Opportunity, Tender
from agevolamatch.tenders.models import TenderMatchResult

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"

MODELS = {
    "opportunity.schema.json": Opportunity,
    "incentive.schema.json": Incentive,
    "tender.schema.json": Tender,
    "company_profile.schema.json": CompanyProfile,
    "match_result.schema.json": MatchResult,
    "tender_match_result.schema.json": TenderMatchResult,
}


def main() -> None:
    SCHEMAS_DIR.mkdir(exist_ok=True)
    for filename, model in MODELS.items():
        schema = model.model_json_schema()
        path = SCHEMAS_DIR / filename
        path.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
