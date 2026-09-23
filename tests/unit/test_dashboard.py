"""Exercises the real Streamlit app (not a mock) via Streamlit's own
AppTest harness, against real ingested fixture data - the same pattern used
elsewhere in this suite (API via TestClient, MCP via call_tool())."""

from __future__ import annotations

from pathlib import Path

import pytest

st_testing = pytest.importorskip(
    "streamlit.testing.v1", reason="streamlit is an optional extra - run `uv sync --extra dashboard` to test it"
)
AppTest = st_testing.AppTest

from agevolamatch.sources.incentivi_gov_it import IncentiviGovItSource  # noqa: E402
from agevolamatch.storage import (  # noqa: E402
    get_engine,
    get_session,
    init_db,
    upsert_opportunities,
)

APP_PATH = str(Path(__file__).parent.parent.parent / "src" / "agevolamatch" / "dashboard" / "app.py")


@pytest.fixture(autouse=True)
def _clear_streamlit_caches():
    """`@st.cache_resource`/`@st.cache_data` are global to the process, not
    scoped per AppTest run - without clearing them, a test using a different
    AGEVOLAMATCH_DB_PATH than a previous test would still see the previous
    test's cached engine/data. This was a real failure, not a hypothetical."""
    import streamlit as st

    st.cache_resource.clear()
    st.cache_data.clear()
    yield
    st.cache_resource.clear()
    st.cache_data.clear()


@pytest.fixture
def dashboard_env(tmp_path, incentivi_gov_it_raw_docs, monkeypatch):
    db_path = tmp_path / "dashboard_test.db"
    monkeypatch.setenv("AGEVOLAMATCH_DB_PATH", str(db_path))

    engine = get_engine(db_path)
    init_db(engine)
    source = IncentiviGovItSource()
    incentives = [source.normalize(doc) for doc in incentivi_gov_it_raw_docs]
    with get_session(engine) as session:
        upsert_opportunities(session, incentives)

    return db_path


def test_app_runs_without_exceptions(dashboard_env):
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=30)
    assert not at.exception


def test_app_shows_title_and_tabs(dashboard_env):
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=30)
    assert any("AgevolaMatch" in t.value for t in at.title)
    assert len(at.tabs) == 3


def test_loading_example_profile_populates_session_state(dashboard_env):
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=30)

    profile_tab = at.tabs[1]
    load_button = profile_tab.button[0]
    load_button.click().run(timeout=30)

    assert at.session_state["profile"] is not None
    assert at.session_state["profile"].name


def test_matching_tab_shows_prompt_without_a_profile(dashboard_env):
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=30)

    match_tab = at.tabs[2]
    assert any("perfil" in info.value.lower() for info in match_tab.info)


def test_matching_tab_shows_results_after_loading_example_profile(dashboard_env):
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=30)

    at.tabs[1].button[0].click().run(timeout=30)  # load example profile
    at.run(timeout=30)

    match_tab = at.tabs[2]
    assert match_tab.caption
    assert "incentivo" in match_tab.caption[0].value.lower()


def test_empty_database_shows_warning_instead_of_crashing(tmp_path, monkeypatch):
    monkeypatch.setenv("AGEVOLAMATCH_DB_PATH", str(tmp_path / "empty.db"))
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=30)
    assert not at.exception
    assert at.warning
