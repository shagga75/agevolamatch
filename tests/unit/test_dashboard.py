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

from agevolamatch.sources.anac import ANACSource  # noqa: E402
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


@pytest.fixture
def dashboard_env_with_gare(tmp_path, incentivi_gov_it_raw_docs, anac_cig_raw_rows, monkeypatch):
    db_path = tmp_path / "dashboard_gare_test.db"
    monkeypatch.setenv("AGEVOLAMATCH_DB_PATH", str(db_path))

    engine = get_engine(db_path)
    init_db(engine)
    incentive_source = IncentiviGovItSource()
    tender_source = ANACSource()
    opportunities = [incentive_source.normalize(doc) for doc in incentivi_gov_it_raw_docs] + [
        tender_source.normalize(row) for row in anac_cig_raw_rows
    ]
    with get_session(engine) as session:
        upsert_opportunities(session, opportunities)

    return db_path


def test_app_runs_without_exceptions(dashboard_env):
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=30)
    assert not at.exception


def test_app_shows_title_and_tabs(dashboard_env):
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=30)
    assert any("AgevolaMatch" in t.value for t in at.title)
    assert len(at.tabs) == 4  # Incentivos, Gare, Perfil de empresa, Matching


def test_loading_example_profile_populates_session_state(dashboard_env):
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=30)

    profile_tab = at.tabs[2]
    load_button = profile_tab.button[0]
    load_button.click().run(timeout=30)

    assert at.session_state["profile"] is not None
    assert at.session_state["profile"].name


def test_matching_tab_shows_prompt_without_a_profile(dashboard_env):
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=30)

    match_tab = at.tabs[3]
    assert any("perfil" in info.value.lower() for info in match_tab.info)


def test_matching_tab_shows_results_after_loading_example_profile(dashboard_env):
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=30)

    at.tabs[2].button[0].click().run(timeout=30)  # load example profile
    at.run(timeout=30)

    match_tab = at.tabs[3]
    assert match_tab.caption
    assert any("perfil actual" in c.value.lower() for c in match_tab.caption)


def test_empty_database_shows_warning_instead_of_crashing(tmp_path, monkeypatch):
    monkeypatch.setenv("AGEVOLAMATCH_DB_PATH", str(tmp_path / "empty.db"))
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=30)
    assert not at.exception
    assert at.warning


def test_gare_tab_lists_real_tenders(dashboard_env_with_gare):
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=30)

    gare_tab = at.tabs[1]
    assert not at.exception
    assert any("gara" in c.value.lower() for c in gare_tab.caption)


def test_incentives_only_db_shows_info_instead_of_crashing_in_gare_tab(dashboard_env):
    """dashboard_env seeds only incentives, no tenders - the Gare tab must
    degrade to an informational message, not crash, when load_tenders()
    returns an empty list."""
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=30)

    gare_tab = at.tabs[1]
    assert not at.exception
    assert any("gare ingest" in info.value for info in gare_tab.info)


def test_tender_matching_subtab_requires_cpv_codes(dashboard_env_with_gare):
    """Loading the example profile (which has cpv_codes) should let the gare
    sub-tab produce results, not the "no CPV configured" info message."""
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=30)

    at.tabs[2].button[0].click().run(timeout=30)  # load example profile (has cpv_codes)
    at.run(timeout=30)

    match_tab = at.tabs[3]
    # The nested "Gare" sub-tab's own caption ("N gara(s) elegible(s)") proves
    # render_tender_matching_tab actually ran match_tender_profile, not just
    # the outer "Perfil actual" caption from render_matching_tab.
    assert any("gara(s) elegible" in c.value.lower() for c in match_tab.caption)


def test_tender_matching_subtab_prompts_when_profile_has_no_cpv_codes(dashboard_env_with_gare):
    from agevolamatch.models.company_profile import CompanyProfile
    from agevolamatch.models.enums import CompanySize, Region

    at = AppTest.from_file(APP_PATH)
    at.run(timeout=30)

    at.session_state["profile"] = CompanyProfile(name="Empresa sin CPV", region=Region.LAZIO, size=CompanySize.MICRO)
    at.run(timeout=30)

    match_tab = at.tabs[3]
    assert not at.exception
    assert any("no tiene códigos cpv" in info.value.lower() for info in match_tab.info)
