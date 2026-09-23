"""SQL persistence model.

Rather than mirroring every Incentive/Tender field as a SQL column, we index
the columns matching queries actually need (source, status, dates, hash) and
keep the full normalized record as a JSON payload. This keeps the table
schema stable across Opportunity subtypes (Incentive today, Tender in Fase 5)
without a migration per new field.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel


class OpportunityRecord(SQLModel, table=True):
    __tablename__ = "opportunities"
    __table_args__ = (UniqueConstraint("source", "source_id", name="uq_source_source_id"),)

    id: int | None = Field(default=None, primary_key=True)
    source: str = Field(index=True)
    source_id: str = Field(index=True)
    title: str
    status: str = Field(index=True)
    open_date: datetime | None = None
    close_date: datetime | None = Field(default=None, index=True)
    content_hash: str
    first_seen: datetime
    last_seen_at: datetime
    source_last_updated: datetime | None = None
    payload: dict = Field(sa_column=Column(JSON))
