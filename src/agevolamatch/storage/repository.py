"""Upsert logic that detects new vs. modified vs. unchanged opportunities.

Records are never deleted: a closed incentive stays in the table with
status="closed" so history is preserved, per the project's requirement to
keep track of closed bandi.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlmodel import Session, select

from agevolamatch.models.enums import OpportunitySourceName
from agevolamatch.models.opportunity import Incentive, Opportunity, Tender
from agevolamatch.storage.tables import OpportunityRecord

_INCENTIVE_SOURCES = (OpportunitySourceName.INCENTIVI_GOV_IT, OpportunitySourceName.INVITALIA)
_TENDER_SOURCES = (OpportunitySourceName.ANAC, OpportunitySourceName.TED_EUROPA)


@dataclass
class IngestSummary:
    new: list[OpportunityRecord] = field(default_factory=list)
    modified: list[OpportunityRecord] = field(default_factory=list)
    unchanged: list[OpportunityRecord] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.new) + len(self.modified) + len(self.unchanged)


def upsert_opportunities(session: Session, opportunities: list[Opportunity]) -> IngestSummary:
    summary = IngestSummary()
    now = datetime.now(tz=UTC)

    for opp in opportunities:
        existing = session.exec(
            select(OpportunityRecord).where(
                OpportunityRecord.source == opp.source,
                OpportunityRecord.source_id == opp.source_id,
            )
        ).first()

        payload = opp.model_dump(mode="json")

        if existing is None:
            record = OpportunityRecord(
                source=opp.source,
                source_id=opp.source_id,
                title=opp.title,
                status=opp.status,
                open_date=opp.open_date,
                close_date=opp.close_date,
                content_hash=opp.content_hash,
                first_seen=opp.first_seen,
                last_seen_at=now,
                source_last_updated=opp.source_last_updated,
                payload=payload,
            )
            session.add(record)
            summary.new.append(record)
        elif existing.content_hash != opp.content_hash:
            existing.title = opp.title
            existing.status = opp.status
            existing.open_date = opp.open_date
            existing.close_date = opp.close_date
            existing.content_hash = opp.content_hash
            existing.last_seen_at = now
            existing.source_last_updated = opp.source_last_updated
            existing.payload = payload
            session.add(existing)
            summary.modified.append(existing)
        else:
            existing.status = opp.status
            existing.last_seen_at = now
            session.add(existing)
            summary.unchanged.append(existing)

    session.commit()
    return summary


def load_incentives(session: Session, status: str | None = None) -> list[Incentive]:
    """Deserializes stored payloads back into Incentive models. Shared by the
    CLI and the API so both read incentives the same way.

    Filters to incentive sources: the same table also stores Tender records
    (ANAC/TED, Fase 5) since both are Opportunity subtypes sharing one table -
    without this filter, Incentive.model_validate() would raise on a Tender's
    payload (extra="forbid" rejects Tender-only fields like buyer_name)."""
    query = select(OpportunityRecord).where(OpportunityRecord.source.in_(_INCENTIVE_SOURCES))
    if status:
        query = query.where(OpportunityRecord.status == status)
    records = session.exec(query).all()
    return [Incentive.model_validate(r.payload) for r in records]


def load_tenders(session: Session, status: str | None = None) -> list[Tender]:
    """Same idea as load_incentives, filtered to tender sources (ANAC/TED)."""
    query = select(OpportunityRecord).where(OpportunityRecord.source.in_(_TENDER_SOURCES))
    if status:
        query = query.where(OpportunityRecord.status == status)
    records = session.exec(query).all()
    return [Tender.model_validate(r.payload) for r in records]
