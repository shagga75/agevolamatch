"""End-to-end check: real fixture docs -> normalize -> persist. This is the
path a bare unit test on either layer alone won't exercise (e.g. it caught a
naive-vs-aware datetime mismatch that only surfaces once real records with
open/close dates reach the database)."""

from __future__ import annotations

from sqlmodel import Session, SQLModel, create_engine

from agevolamatch.sources.incentivi_gov_it import IncentiviGovItSource
from agevolamatch.storage.repository import upsert_opportunities


def test_full_fixture_ingests_without_error(incentivi_gov_it_raw_docs):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    source = IncentiviGovItSource()
    incentives = [source.normalize(doc) for doc in incentivi_gov_it_raw_docs]

    with Session(engine) as session:
        summary = upsert_opportunities(session, incentives)

    assert summary.total == len(incentivi_gov_it_raw_docs)
    assert len(summary.new) == len(incentivi_gov_it_raw_docs)


def test_reingesting_same_fixture_is_idempotent(incentivi_gov_it_raw_docs):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    source = IncentiviGovItSource()
    incentives = [source.normalize(doc) for doc in incentivi_gov_it_raw_docs]

    with Session(engine) as session:
        upsert_opportunities(session, incentives)
        second = upsert_opportunities(session, incentives)

    assert len(second.new) == 0
    assert len(second.modified) == 0
    assert len(second.unchanged) == len(incentivi_gov_it_raw_docs)
