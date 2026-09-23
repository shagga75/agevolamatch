"""Parsing helpers shared across sources, extracted from patterns observed in
the real incentivi.gov.it dump (see docs/sources.md for the underlying analysis)."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, date, datetime

from agevolamatch.models.enums import OpportunityStatus

_ATECO_ALL_SECTORS_PATTERN = re.compile(r"^tutti\s+i\s+(settori|codici)", re.IGNORECASE)
_ATECO_CODE_PATTERN = re.compile(r"\d{2}(?:\.\d{1,2}){0,2}")
_NUMBER_PATTERN = re.compile(r"-?\d[\d.]*(?:,\d+)?")


def parse_iso_datetime(value: str | None) -> datetime | None:
    """Handles both '2023-09-08T00:00:00' (naive, always midnight in the source)
    and '2024-03-28T12:05:28Z' (UTC). Naive values are assumed UTC so every
    returned datetime is timezone-aware - storage (SQLModel) rejects naive ones,
    and mixing naive/aware breaks comparisons."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


_TED_DATE_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:[+-]\d{2}:\d{2})?$")


def parse_ted_date(value: str | None) -> datetime | None:
    """TED API dates look like '2026-09-01+02:00' - a date with a UTC offset
    but no time component. `datetime.fromisoformat` silently misparses this
    (confirmed: it reads the offset's digits as an 02:00 time-of-day and
    drops the timezone entirely, giving a wrong-but-plausible-looking
    result) - so this extracts just the date part and treats it as UTC
    midnight, consistent with how other date-only sources are handled."""
    if not value:
        return None
    match = _TED_DATE_PATTERN.match(value.strip())
    if not match:
        return None
    return datetime.fromisoformat(match.group(1)).replace(tzinfo=UTC)


def parse_ateco(raw: str | None) -> tuple[list[str] | None, bool]:
    """Returns (codes, all_sectors). ~71% of records use free-text 'all sectors
    eligible' instead of real codes; only ~29% carry semicolon-separated codes."""
    if not raw:
        return None, False
    if _ATECO_ALL_SECTORS_PATTERN.match(raw.strip()):
        return None, True
    codes = _ATECO_CODE_PATTERN.findall(raw)
    return (codes or None), False


def parse_italian_money(raw: str | None) -> float | None:
    """Best-effort parse of a messy money field (Stanziamento_incentivo): plain
    integers, comma-decimal Italian format, or free text with multiple amounts
    (e.g. '163000000 (con dm 29/7), 161800000 (con dm 09/08)'). Takes the first
    number found; never raises. Never used for hard-filter eligibility."""
    if not raw:
        return None
    match = _NUMBER_PATTERN.search(raw)
    if not match:
        return None
    number = match.group(0).replace(".", "").replace(",", ".") if "," in match.group(0) else match.group(0)
    try:
        return float(number)
    except ValueError:
        return None


def compute_status(
    open_date: datetime | None, close_date: datetime | None, as_of: date | None = None
) -> OpportunityStatus:
    today = as_of or datetime.now(tz=UTC).date()

    def as_date(dt: datetime | None) -> date | None:
        return dt.date() if dt else None

    open_d, close_d = as_date(open_date), as_date(close_date)
    if open_d is None and close_d is None:
        return OpportunityStatus.UNKNOWN
    if open_d and today < open_d:
        return OpportunityStatus.UPCOMING
    if close_d and today > close_d:
        return OpportunityStatus.CLOSED
    return OpportunityStatus.OPEN


def compute_content_hash(fields: dict) -> str:
    """Stable hash over the fields that matter for change detection. Excludes
    volatile bookkeeping fields (first_seen, last_seen_at, status, content_hash
    itself) so the hash only changes when the underlying data actually changes."""
    stable = {k: v for k, v in fields.items() if k not in {"first_seen", "last_seen_at", "status", "content_hash"}}
    serialized = json.dumps(stable, sort_keys=True, default=str, ensure_ascii=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
