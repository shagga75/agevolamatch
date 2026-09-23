from __future__ import annotations

from typer.testing import CliRunner

from agevolamatch.cli.main import app
from agevolamatch.sources.anac import ANACSource
from agevolamatch.storage import get_engine, get_session, init_db, upsert_opportunities

runner = CliRunner()


def _seed_db(db_path, anac_rows):
    engine = get_engine(db_path)
    init_db(engine)
    source = ANACSource()
    tenders = [source.normalize(row) for row in anac_rows]
    with get_session(engine) as session:
        upsert_opportunities(session, tenders)


def _write_profile(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text(
        'name: Test Srl\nregion: Lazio\nsize: Microimpresa\ncpv_codes: ["72200000"]\n',
        encoding="utf-8",
    )
    return path


def _write_subscriptions(tmp_path, profile_path, min_score=0):
    path = tmp_path / "subs.yaml"
    path.write_text(
        f"subscriptions:\n  - name: test-sub\n    profile: {profile_path}\n    min_score: {min_score}\n    channels: [telegram]\n",
        encoding="utf-8",
    )
    return path


def test_gare_alerts_run_dry_run_reports_without_sending(tmp_path, anac_cig_raw_rows, monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    db_path = tmp_path / "cli_gare_test.db"
    _seed_db(db_path, anac_cig_raw_rows)
    profile_path = _write_profile(tmp_path)
    subs_path = _write_subscriptions(tmp_path, profile_path)

    result = runner.invoke(
        app,
        ["gare", "alerts", "run", "--subscriptions", str(subs_path), "--db-path", str(db_path), "--dry-run"],
    )

    assert result.exit_code == 0, result.output
    assert "DRY RUN" in result.output
    # Unconfigured Telegram would raise on a real send - dry-run must never call it.


def test_gare_alerts_run_with_no_subscriptions_matching_exits_cleanly(tmp_path, anac_cig_raw_rows):
    db_path = tmp_path / "cli_gare_test.db"
    _seed_db(db_path, anac_cig_raw_rows)
    profile_path = _write_profile(tmp_path)
    subs_path = _write_subscriptions(tmp_path, profile_path, min_score=1000)

    result = runner.invoke(
        app,
        ["gare", "alerts", "run", "--subscriptions", str(subs_path), "--db-path", str(db_path), "--dry-run"],
    )

    assert result.exit_code == 0, result.output
    assert "0 alerta" in result.output
