from __future__ import annotations

import pytest
from sqlmodel import Session, SQLModel, create_engine

from agevolamatch.alerts.base import AlertChannel
from agevolamatch.alerts.service import run_alerts
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
        "name: Test Srl\nregion: Lazio\nsize: Microimpresa\nateco_codes:\n  - code: \"62.01\"\n",
        encoding="utf-8",
    )
    return path


def make_subscription(profile_path, **overrides) -> AlertSubscription:
    defaults = {"name": "sub1", "profile": profile_path, "min_score": 0.0, "channels": ["fake"]}
    defaults.update(overrides)
    return AlertSubscription(**defaults)


def test_dry_run_does_not_send_or_record(session, profile_path, incentive_factory):
    incentive = incentive_factory(ateco_all_sectors=True)
    channel = FakeChannel()
    summary = run_alerts(session, [incentive], [make_subscription(profile_path)], {"fake": channel}, dry_run=True)
    assert summary.dry_run is True
    assert summary.total == 1
    assert summary.events[0].sent is False
    assert channel.sent == []


def test_real_run_sends_and_records(session, profile_path, incentive_factory):
    incentive = incentive_factory(ateco_all_sectors=True)
    channel = FakeChannel()
    summary = run_alerts(session, [incentive], [make_subscription(profile_path)], {"fake": channel}, dry_run=False)
    assert len(channel.sent) == 1
    assert summary.events[0].sent is True


def test_second_run_does_not_resend_same_content(session, profile_path, incentive_factory):
    incentive = incentive_factory(ateco_all_sectors=True)
    channel = FakeChannel()
    subs = [make_subscription(profile_path)]
    run_alerts(session, [incentive], subs, {"fake": channel}, dry_run=False)
    summary2 = run_alerts(session, [incentive], subs, {"fake": channel}, dry_run=False)
    assert summary2.total == 0
    assert len(channel.sent) == 1


def test_modified_incentive_triggers_a_new_alert(session, profile_path, incentive_factory):
    channel = FakeChannel()
    subs = [make_subscription(profile_path)]
    original = incentive_factory(ateco_all_sectors=True, content_hash="hash-v1")
    run_alerts(session, [original], subs, {"fake": channel}, dry_run=False)

    modified = incentive_factory(ateco_all_sectors=True, content_hash="hash-v2")
    summary2 = run_alerts(session, [modified], subs, {"fake": channel}, dry_run=False)
    assert summary2.total == 1
    assert len(channel.sent) == 2


def test_ineligible_incentive_is_never_alerted(session, profile_path, incentive_factory):
    incentive = incentive_factory(ateco_all_sectors=False, ateco_codes=["10.01"])  # no ATECO overlap -> ineligible
    channel = FakeChannel()
    summary = run_alerts(session, [incentive], [make_subscription(profile_path)], {"fake": channel}, dry_run=False)
    assert summary.total == 0


def test_below_min_score_is_not_alerted(session, profile_path, incentive_factory):
    incentive = incentive_factory(ateco_all_sectors=True)
    channel = FakeChannel()
    sub = make_subscription(profile_path, min_score=1000.0)
    summary = run_alerts(session, [incentive], [sub], {"fake": channel}, dry_run=False)
    assert summary.total == 0


def test_unknown_channel_raises(session, profile_path, incentive_factory):
    incentive = incentive_factory(ateco_all_sectors=True)
    sub = make_subscription(profile_path, channels=["nonexistent"])
    with pytest.raises(ValueError, match="Unknown alert channel"):
        run_alerts(session, [incentive], [sub], {}, dry_run=False)
