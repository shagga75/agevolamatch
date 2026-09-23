from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Session, select

from agevolamatch.storage.tables import SentAlert


def already_sent(session: Session, subscription_name: str, source: str, source_id: str, content_hash: str) -> bool:
    existing = session.exec(
        select(SentAlert).where(
            SentAlert.subscription_name == subscription_name,
            SentAlert.source == source,
            SentAlert.source_id == source_id,
            SentAlert.content_hash == content_hash,
        )
    ).first()
    return existing is not None


def record_sent(
    session: Session,
    subscription_name: str,
    source: str,
    source_id: str,
    content_hash: str,
    channels_sent: list[str],
) -> None:
    session.add(
        SentAlert(
            subscription_name=subscription_name,
            source=source,
            source_id=source_id,
            content_hash=content_hash,
            channels_sent=",".join(channels_sent),
            sent_at=datetime.now(tz=UTC),
        )
    )
    session.commit()
