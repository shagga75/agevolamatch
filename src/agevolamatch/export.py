"""CSV/JSON export helpers, shared by the `export` CLI command for both raw
stored incentives and match-ranking results."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from agevolamatch.matching.models import MatchResult
from agevolamatch.storage.tables import OpportunityRecord


def match_results_to_rows(results: list[MatchResult]) -> list[dict[str, Any]]:
    rows = []
    for r in results:
        incentive = r.incentive
        rows.append(
            {
                "source_id": incentive.source_id,
                "title": incentive.title,
                "score": r.score,
                "status": incentive.status,
                "close_date": incentive.close_date.date().isoformat() if incentive.close_date else None,
                "regions": ";".join(incentive.regions),
                "granting_body": incentive.granting_body,
                "url": incentive.url,
                "reasons_for": " | ".join(r.explanation.reasons_for),
                "reasons_against": " | ".join(r.explanation.reasons_against),
                "unverifiable": " | ".join(r.explanation.unverifiable),
            }
        )
    return rows


def incentive_records_to_rows(records: list[OpportunityRecord]) -> list[dict[str, Any]]:
    rows = []
    for record in records:
        payload = record.payload
        rows.append(
            {
                "source_id": record.source_id,
                "title": record.title,
                "status": record.status,
                "close_date": record.close_date.date().isoformat() if record.close_date else None,
                "regions": ";".join(payload.get("regions") or []),
                "granting_body": payload.get("granting_body"),
                "url": payload.get("url"),
            }
        )
    return rows


def write_rows(rows: list[dict[str, Any]], path: Path, fmt: str) -> None:
    if fmt == "json":
        path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
        return
    if fmt == "csv":
        if not rows:
            path.write_text("", encoding="utf-8")
            return
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        return
    raise ValueError(f"Unsupported export format: {fmt!r} (expected 'csv' or 'json')")
