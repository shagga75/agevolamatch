"""Mirrors test_alerts_service.py for run_tender_alerts - same dedup
mechanism, same AlertEvent/AlertRunSummary types, different matching call
and message formatting (see alerts/service.py's docstring for why)."""

from __future__ import annotations

import pytest
from sqlmodel import Session, SQLModel, create_engine

from agevolamatch.alerts.base import AlertChannel
from agevolamatch.alerts.service import run_tender_alerts
from agevolamatch.alerts.subscriptions import AlertSubscription


class FakeChannel(AlertChannel):
    name = "fake"

    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    def send(self, subject: str, body: str) -> None:
        self.sent.append((subject, body))


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture
def profile_path(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text(
        'name: Test Srl\nregion: Lazio\nsize: Microimpresa\ncpv_codes: ["72200000"]\n',
        encoding="utf-8",
    )
    return path


def make_subscription(profile_path, **overrides) -> AlertSubscription:
    defaults = {"name": "sub1", "profile": profile_path, "min_score": 0.0, "channels": ["fake"]}
    defaults.update(overrides)
    return AlertSubscription(**defaults)


def test_dry_run_does_not_send_or_record(session, profile_path, tender_factory):
    tender = tender_factory(cpv_codes=["72200000"])
    channel = FakeChannel()
    summary = run_tender_alerts(session, [tender], [make_subscription(profile_path)], {"fake": channel}, dry_run=True)
    assert summary.dry_run is True
    assert summary.total == 1
    assert summary.events[0].sent is False
    assert channel.sent == []


def test_real_run_sends_and_records(session, profile_path, tender_factory):
    tender = tender_factory(cpv_codes=["72200000"])
    channel = FakeChannel()
    summary = run_tender_alerts(session, [tender], [make_subscription(profile_path)], {"fake": channel}, dry_run=False)
    assert len(channel.sent) == 1
    assert summary.events[0].sent is True
    assert "72200000" in channel.sent[0][1] or "score" in channel.sent[0][0]


def test_second_run_does_not_resend_same_content(session, profile_path, tender_factory):
    tender = tender_factory(cpv_codes=["72200000"])
    channel = FakeChannel()
    subs = [make_subscription(profile_path)]
    run_tender_alerts(session, [tender], subs, {"fake": channel}, dry_run=False)
    summary2 = run_tender_alerts(session, [tender], subs, {"fake": channel}, dry_run=False)
    assert summary2.total == 0
    assert len(channel.sent) == 1


def test_modified_tender_triggers_a_new_alert(session, profile_path, tender_factory):
    channel = FakeChannel()
    subs = [make_subscription(profile_path)]
    original = tender_factory(cpv_codes=["72200000"], content_hash="hash-v1")
    run_tender_alerts(session, [original], subs, {"fake": channel}, dry_run=False)

    modified = tender_factory(cpv_codes=["72200000"], content_hash="hash-v2")
    summary2 = run_tender_alerts(session, [modified], subs, {"fake": channel}, dry_run=False)
    assert summary2.total == 1
    assert len(channel.sent) == 2


def test_ineligible_tender_is_never_alerted(session, profile_path, tender_factory):
    tender = tender_factory(cpv_codes=["45232410"])  # no CPV overlap -> ineligible
    channel = FakeChannel()
    summary = run_tender_alerts(session, [tender], [make_subscription(profile_path)], {"fake": channel}, dry_run=False)
    assert summary.total == 0


def test_below_min_score_is_not_alerted(session, profile_path, tender_factory):
    tender = tender_factory(cpv_codes=["72200000"])
    channel = FakeChannel()
    sub = make_subscription(profile_path, min_score=1000.0)
    summary = run_tender_alerts(session, [tender], [sub], {"fake": channel}, dry_run=False)
    assert summary.total == 0


def test_unknown_channel_raises(session, profile_path, tender_factory):
    tender = tender_factory(cpv_codes=["72200000"])
    sub = make_subscription(profile_path, channels=["nonexistent"])
    with pytest.raises(ValueError, match="Unknown alert channel"):
        run_tender_alerts(session, [tender], [sub], {}, dry_run=False)


def test_incentive_and_tender_alerts_share_the_dedup_log_but_dont_collide(session, profile_path, tender_factory):
    """SentAlert is keyed on (subscription_name, source, source_id,
    content_hash) - a tender and an incentive from different sources with
    the same source_id must not be treated as duplicates of each other."""
    from agevolamatch.alerts.repository import already_sent, record_sent
    from agevolamatch.models.enums import OpportunitySourceName

    record_sent(session, "sub1", OpportunitySourceName.INCENTIVI_GOV_IT, "SAME_ID", "hash-x", ["fake"])
    assert already_sent(session, "sub1", OpportunitySourceName.ANAC, "SAME_ID", "hash-x") is False
