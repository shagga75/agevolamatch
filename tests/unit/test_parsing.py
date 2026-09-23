from __future__ import annotations

from datetime import UTC, date, datetime

from agevolamatch.models.enums import OpportunityStatus
from agevolamatch.sources.parsing import (
    compute_content_hash,
    compute_status,
    parse_ateco,
    parse_iso_datetime,
    parse_italian_money,
)


class TestParseIsoDatetime:
    def test_naive_date_is_assumed_utc(self):
        assert parse_iso_datetime("2023-09-08T00:00:00") == datetime(2023, 9, 8, tzinfo=UTC)

    def test_utc_date_with_z_suffix(self):
        result = parse_iso_datetime("2024-03-28T12:05:28Z")
        assert result == datetime(2024, 3, 28, 12, 5, 28, tzinfo=UTC)

    def test_none_returns_none(self):
        assert parse_iso_datetime(None) is None

    def test_empty_string_returns_none(self):
        assert parse_iso_datetime("") is None

    def test_garbage_returns_none(self):
        assert parse_iso_datetime("not-a-date") is None


class TestParseAteco:
    def test_all_sectors_prose_no_trailing_punctuation(self):
        codes, all_sectors = parse_ateco("Tutti i settori economici ammissibili a ricevere aiuti")
        assert codes is None
        assert all_sectors is True

    def test_all_sectors_prose_with_trailing_semicolon(self):
        codes, all_sectors = parse_ateco("Tutti i settori economici ammissibili a ricevere aiuti;")
        assert codes is None
        assert all_sectors is True

    def test_all_codici_variant(self):
        codes, all_sectors = parse_ateco("Tutti i codici Ateco")
        assert all_sectors is True

    def test_semicolon_separated_codes(self):
        codes, all_sectors = parse_ateco("90.00; 90.01; 90.02; 90.03; 90.04;")
        assert all_sectors is False
        assert codes == ["90.00", "90.01", "90.02", "90.03", "90.04"]

    def test_none_input(self):
        codes, all_sectors = parse_ateco(None)
        assert codes is None
        assert all_sectors is False

    def test_empty_string(self):
        codes, all_sectors = parse_ateco("")
        assert codes is None
        assert all_sectors is False


class TestParseItalianMoney:
    def test_plain_integer(self):
        assert parse_italian_money("650000") == 650000.0

    def test_comma_decimal(self):
        assert parse_italian_money("15375383,50") == 15375383.50

    def test_compound_text_takes_first_number(self):
        result = parse_italian_money("163000000 (con dm 29/7), 161800000 (con dm 09/08)")
        assert result == 163000000.0

    def test_none_returns_none(self):
        assert parse_italian_money(None) is None

    def test_empty_returns_none(self):
        assert parse_italian_money("") is None

    def test_no_number_returns_none(self):
        assert parse_italian_money("Non applicabile") is None


class TestComputeStatus:
    def test_open_when_between_dates(self):
        status = compute_status(
            datetime(2024, 1, 1), datetime(2099, 1, 1), as_of=date(2024, 6, 1)
        )
        assert status == OpportunityStatus.OPEN

    def test_upcoming_when_before_open_date(self):
        status = compute_status(
            datetime(2099, 1, 1), datetime(2099, 6, 1), as_of=date(2024, 6, 1)
        )
        assert status == OpportunityStatus.UPCOMING

    def test_closed_when_after_close_date(self):
        status = compute_status(
            datetime(2023, 1, 1), datetime(2023, 12, 23), as_of=date(2024, 6, 1)
        )
        assert status == OpportunityStatus.CLOSED

    def test_unknown_when_no_dates(self):
        assert compute_status(None, None) == OpportunityStatus.UNKNOWN

    def test_open_when_only_open_date_in_past(self):
        status = compute_status(datetime(2020, 1, 1), None, as_of=date(2024, 6, 1))
        assert status == OpportunityStatus.OPEN


class TestComputeContentHash:
    def test_deterministic(self):
        fields = {"title": "x", "regions": ["Lazio"]}
        assert compute_content_hash(fields) == compute_content_hash(fields)

    def test_changes_when_content_changes(self):
        h1 = compute_content_hash({"title": "x"})
        h2 = compute_content_hash({"title": "y"})
        assert h1 != h2

    def test_ignores_volatile_bookkeeping_fields(self):
        base = {"title": "x"}
        with_volatile = {**base, "first_seen": "2024-01-01", "last_seen_at": "2024-06-01", "status": "open"}
        assert compute_content_hash(base) == compute_content_hash(with_volatile)
