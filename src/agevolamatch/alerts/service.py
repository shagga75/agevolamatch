"""Orchestrates alerts/run: for each subscription, match its profile against
stored incentives and send an alert for every result that (a) clears the
subscription's min_score and (b) hasn't already been alerted at this exact
content_hash (see alerts/repository.py - this is what makes "new or modified"
detection work across separate `alerts run` invocations, independent of when
`ingest` last ran).
"""

from __future__ import annotations

import logging

from pydantic import BaseModel
from sqlmodel import Session

from agevolamatch.alerts.base import AlertChannel
from agevolamatch.alerts.formatting import format_alert_message
from agevolamatch.alerts.repository import already_sent, record_sent
from agevolamatch.alerts.subscriptions import AlertSubscription
from agevolamatch.matching.engine import match_profile
from agevolamatch.matching.profile_loader import load_company_profile
from agevolamatch.matching.weights import DEFAULT_WEIGHTS, ScoringWeights
from agevolamatch.models.opportunity import Incentive

logger = logging.getLogger(__name__)


class AlertEvent(BaseModel):
    subscription_name: str
    source_id: str
    title: str
    score: float
    channels: list[str]
    sent: bool


class AlertRunSummary(BaseModel):
    dry_run: bool
    events: list[AlertEvent] = []

    @property
    def total(self) -> int:
        return len(self.events)


def run_alerts(
    session: Session,
    incentives: list[Incentive],
    subscriptions: list[AlertSubscription],
    channels: dict[str, AlertChannel],
    dry_run: bool = True,
) -> AlertRunSummary:
    summary = AlertRunSummary(dry_run=dry_run)

    for subscription in subscriptions:
        profile = load_company_profile(subscription.profile)
        weights = ScoringWeights.from_yaml(subscription.weights) if subscription.weights else DEFAULT_WEIGHTS
        results = match_profile(incentives, profile, weights=weights)

        for result in results:
            if result.score < subscription.min_score:
                continue
            incentive = result.incentive
            if already_sent(session, subscription.name, incentive.source, incentive.source_id, incentive.content_hash):
                continue

            if not dry_run:
                subject, body = format_alert_message(subscription.name, result)
                for channel_name in subscription.channels:
                    channel = channels.get(channel_name)
                    if channel is None:
                        raise ValueError(f"Unknown alert channel {channel_name!r} in subscription {subscription.name!r}")
                    channel.send(subject, body)
                record_sent(
                    session,
                    subscription.name,
                    incentive.source,
                    incentive.source_id,
                    incentive.content_hash,
                    subscription.channels,
                )

            summary.events.append(
                AlertEvent(
                    subscription_name=subscription.name,
                    source_id=incentive.source_id,
                    title=incentive.title,
                    score=result.score,
                    channels=subscription.channels,
                    sent=not dry_run,
                )
            )

    return summary
