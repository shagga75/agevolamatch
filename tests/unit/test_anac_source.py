from __future__ import annotations

from datetime import date

from agevolamatch.models.enums import OpportunitySourceName, OpportunityStatus
from agevolamatch.sources.anac import _DELTA_RESOURCE_NAME_PATTERN, ANACSource


def test_delta_resource_name_pattern_matches_real_naming():
    assert _DELTA_RESOURCE_NAME_PATTERN.match("20260901-cig_csv")
    assert _DELTA_RESOURCE_NAME_PATTERN.match("cig_csv_logCsv") is None


def test_normalize_all_fixture_rows_without_raising(anac_cig_raw_rows):
    source = ANACSource()
    tenders = [source.normalize(row) for row in anac_cig_raw_rows]
    assert len(tenders) == len(anac_cig_raw_rows)
    for tender in tenders:
        assert tender.source == OpportunitySourceName.ANAC
        assert tender.cig
        assert tender.source_id == tender.cig


def test_run_is_tolerant_of_one_malformed_record(anac_cig_raw_rows, monkeypatch):
    source = ANACSource()
    broken = dict(anac_cig_raw_rows[0])
    del broken["oggetto_gara"]  # required for title -> normalize() should raise for this one
    docs = [broken, *anac_cig_raw_rows[1:]]

    monkeypatch.setattr(source, "fetch", lambda: b"")
    monkeypatch.setattr(source, "parse", lambda raw: docs)
    results = source.run()

    assert len(results) == len(docs) - 1


def test_contract_type_is_preserved(anac_cig_raw_rows):
    source = ANACSource()
    row = next(r for r in anac_cig_raw_rows if r.get("oggetto_principale_contratto") == "LAVORI")
    tender = source.normalize(row)
    assert tender.contract_type == "LAVORI"


def test_missing_province_leaves_field_none(anac_cig_raw_rows):
    """Checked live: among 3,908 real still-open records (2026-09-23 delta),
    0 were missing 'provincia' - the general CSV schema allows it (seen when
    scanning the full delta including closed/awarded rows), but it doesn't
    occur in the currently-open subset this source actually stores. This
    test constructs the case directly rather than relying on the fixture to
    happen to contain something that genuinely isn't in real open data today."""
    source = ANACSource()
    row = dict(anac_cig_raw_rows[0])
    row["provincia"] = ""
    tender = source.normalize(row)
    assert tender.province is None


def test_estimated_value_falls_back_to_complessivo_when_lotto_missing(anac_cig_raw_rows):
    """Same situation as the province case above: 0/3,908 real open records
    were missing importo_lotto - constructed directly for the same reason."""
    source = ANACSource()
    row = dict(anac_cig_raw_rows[0])
    row["importo_lotto"] = ""
    row["importo_complessivo_gara"] = "999999.99"
    tender = source.normalize(row)
    assert tender.estimated_value == 999999.99


def test_status_is_open_for_future_deadline(anac_cig_raw_rows):
    """parse() already filters to future-deadline rows (see module docstring),
    so every fixture row should normalize to an open status as of today."""
    source = ANACSource()
    for row in anac_cig_raw_rows:
        tender = source.normalize(row)
        assert tender.status == OpportunityStatus.OPEN, tender.cig


def test_status_becomes_closed_once_deadline_passes(anac_cig_raw_rows):
    source = ANACSource()
    row = anac_cig_raw_rows[0]
    tender = source.normalize(row)
    future_status = tender.status
    assert future_status == OpportunityStatus.OPEN
    # Recompute as if run far in the future, past every fixture row's deadline.
    from agevolamatch.sources.parsing import compute_status

    assert compute_status(tender.open_date, tender.close_date, as_of=date(2099, 1, 1)) == OpportunityStatus.CLOSED
