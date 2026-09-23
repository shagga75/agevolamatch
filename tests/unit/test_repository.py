from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlmodel import Session, SQLModel, create_engine

from agevolamatch.models.enums import OpportunitySourceName, OpportunityStatus
from agevolamatch.models.opportunity import Incentive
from agevolamatch.sources.parsing import compute_content_hash
from agevolamatch.storage.repository import upsert_opportunities


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
