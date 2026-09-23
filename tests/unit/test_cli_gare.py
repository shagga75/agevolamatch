from __future__ import annotations

from typer.testing import CliRunner

from agevolamatch.cli.main import app
from agevolamatch.sources.anac import ANACSource
from agevolamatch.sources.ted import TEDSource
from agevolamatch.storage import get_engine, get_session, init_db, upsert_opportunities

runner = CliRunner()


def _seed_gare_db(db_path, anac_rows, ted_notices):
    engine = get_engine(db_path)
    init_db(engine)
    anac_source = ANACSource()
    ted_source = TEDSource()
    tenders = [anac_source.normalize(r) for r in anac_rows] + [ted_source.normalize(n) for n in ted_notices]
    with get_session(engine) as session:
        upsert_opportunities(session, tenders)
    return len(tenders)


def test_gare_match_against_real_fixtures(tmp_path, anac_cig_raw_rows, ted_notices_raw):
    db_path = tmp_path / "gare_cli_test.db"
    _seed_gare_db(db_path, anac_cig_raw_rows, ted_notices_raw)

    result = runner.invoke(
        app,
        ["gare", "match", "--profile", "examples/startup_profile.yaml", "--db-path", str(db_path), "--top", "5"],
    )

    assert result.exit_code == 0, result.output
    assert "gara(s) elegible" in result.output


def test_gare_match_with_no_stored_tenders_exits_cleanly(tmp_path):
    db_path = tmp_path / "empty_gare.db"
    result = runner.invoke(
        app,
        ["gare", "match", "--profile", "examples/startup_profile.yaml", "--db-path", str(db_path)],
    )
    assert result.exit_code == 1
    assert "No hay gare almacenadas" in result.output


def test_gare_ingest_rejects_unknown_source(tmp_path):
    db_path = tmp_path / "gare.db"
    result = runner.invoke(app, ["gare", "ingest", "--source", "bogus", "--db-path", str(db_path)])
    assert result.exit_code == 1
    assert "Fuente desconocida" in result.output
