from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlmodel import Session, SQLModel, create_engine

from agevolamatch.models.enums import OpportunitySourceName, OpportunityStatus
from agevolamatch.models.opportunity import Incentive, Tender
from agevolamatch.sources.parsing import compute_content_hash
from agevolamatch.storage.repository import (
    get_incentive_record,
    get_tender_record,
    load_incentives,
    load_tenders,
    upsert_opportunities,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def make_incentive(source_id: str, title: str) -> Incentive:
    now = datetime.now(tz=UTC)
    content_hash = compute_content_hash({"source_id": source_id, "title": title})
    return Incentive(
        source=OpportunitySourceName.INCENTIVI_GOV_IT,
        source_id=source_id,
        title=title,
        status=OpportunityStatus.OPEN,
        content_hash=content_hash,
        first_seen=now,
        last_seen_at=now,
    )


def test_first_ingest_marks_everything_as_new(session):
    summary = upsert_opportunities(session, [make_incentive("1", "Bando A"), make_incentive("2", "Bando B")])
    assert len(summary.new) == 2
    assert len(summary.modified) == 0
    assert len(summary.unchanged) == 0


def test_second_ingest_with_same_data_is_unchanged(session):
    upsert_opportunities(session, [make_incentive("1", "Bando A")])
    summary = upsert_opportunities(session, [make_incentive("1", "Bando A")])
    assert len(summary.new) == 0
    assert len(summary.unchanged) == 1
    assert len(summary.modified) == 0


def test_changed_title_is_detected_as_modified(session):
    upsert_opportunities(session, [make_incentive("1", "Bando A")])
    summary = upsert_opportunities(session, [make_incentive("1", "Bando A - aggiornato")])
    assert len(summary.modified) == 1
    assert summary.modified[0].title == "Bando A - aggiornato"


def test_first_seen_is_preserved_across_updates(session):
    first = upsert_opportunities(session, [make_incentive("1", "Bando A")])
    original_first_seen = first.new[0].first_seen

    second = upsert_opportunities(session, [make_incentive("1", "Bando A - aggiornato")])
    assert second.modified[0].first_seen == original_first_seen


def test_closed_opportunity_is_kept_not_deleted(session):
    upsert_opportunities(session, [make_incentive("1", "Bando A")])
    closed = make_incentive("1", "Bando A")
    closed.status = OpportunityStatus.CLOSED
    summary = upsert_opportunities(session, [closed])
    assert summary.unchanged[0].status == OpportunityStatus.CLOSED


def make_tender(source_id: str, title: str) -> Tender:
    now = datetime.now(tz=UTC)
    content_hash = compute_content_hash({"source_id": source_id, "title": title})
    return Tender(
        source=OpportunitySourceName.ANAC,
        source_id=source_id,
        title=title,
        status=OpportunityStatus.OPEN,
        content_hash=content_hash,
        first_seen=now,
        last_seen_at=now,
    )


def test_load_incentives_ignores_tenders_sharing_the_same_table(session):
    """Regression test: Incentive.model_validate() has extra='forbid', so it
    raises on a Tender's payload (buyer_name, cpv_codes, ... aren't declared
    on Incentive) unless load_incentives filters by source first."""
    upsert_opportunities(session, [make_incentive("1", "Bando A"), make_tender("T1", "Gara A")])
    incentives = load_incentives(session)
    assert [i.source_id for i in incentives] == ["1"]


def test_load_tenders_ignores_incentives_sharing_the_same_table(session):
    upsert_opportunities(session, [make_incentive("1", "Bando A"), make_tender("T1", "Gara A")])
    tenders = load_tenders(session)
    assert [t.source_id for t in tenders] == ["T1"]


def test_get_incentive_record_ignores_a_tender_with_the_same_source_id(session):
    """Regression test: source_id is only unique per (source, source_id), not
    globally - an ANAC CIG and an incentivi.gov.it nid could coincidentally
    share the same string. A lookup scoped to incentive sources must not
    return the tender row just because the id string matches."""
    upsert_opportunities(session, [make_incentive("SAME_ID", "Bando A"), make_tender("SAME_ID", "Gara A")])
    record = get_incentive_record(session, "SAME_ID")
    assert record is not None
    assert record.source == OpportunitySourceName.INCENTIVI_GOV_IT


def test_get_tender_record_ignores_an_incentive_with_the_same_source_id(session):
    upsert_opportunities(session, [make_incentive("SAME_ID", "Bando A"), make_tender("SAME_ID", "Gara A")])
    record = get_tender_record(session, "SAME_ID")
    assert record is not None
    assert record.source == OpportunitySourceName.ANAC


def test_get_incentive_record_returns_none_for_unknown_id(session):
    assert get_incentive_record(session, "does-not-exist") is None


def test_get_tender_record_returns_none_for_unknown_id(session):
    assert get_tender_record(session, "does-not-exist") is None
