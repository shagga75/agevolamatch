"""Streamlit dashboard: filterable incentive list, incentive detail, a
company profile editor, and matching results with explanations. Same
storage/matching code as the CLI, API, and MCP server - no separate logic.

Run with: uv run streamlit run src/agevolamatch/dashboard/app.py
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st

from agevolamatch.matching import DEFAULT_WEIGHTS, match_profile
from agevolamatch.matching.profile_loader import load_company_profile
from agevolamatch.models.company_profile import AtecoCode, CompanyProfile
from agevolamatch.models.enums import CompanySize, EligibleCost, LegalForm, Region, SupportForm
from agevolamatch.models.opportunity import Incentive, Tender
from agevolamatch.storage import get_engine, get_session, init_db, load_incentives, load_tenders
from agevolamatch.tenders import DEFAULT_TENDER_WEIGHTS, match_tender_profile

EXAMPLE_PROFILE_PATH = Path("examples/startup_profile.yaml")


def _db_path() -> Path:
    return Path(os.environ.get("AGEVOLAMATCH_DB_PATH", "data/agevolamatch.db"))


@st.cache_resource
def _engine():
    engine = get_engine(_db_path())
    init_db(engine)
    return engine


@st.cache_data(ttl=60)
def _load_all_incentives() -> list[Incentive]:
    with get_session(_engine()) as session:
        return load_incentives(session)


@st.cache_data(ttl=60)
def _load_all_tenders() -> list[Tender]:
    with get_session(_engine()) as session:
        return load_tenders(session)


def _incentives_dataframe(incentives: list[Incentive]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ID": i.source_id,
                "Fuente": i.source,
                "Título": i.title,
                "Estado": i.status,
                "Cierre": i.close_date.date().isoformat() if i.close_date else "-",
                "Regiones": ", ".join(i.regions),
            }
            for i in incentives
        ]
    )


def render_incentive_list_tab(incentives: list[Incentive]) -> None:
    col1, col2, col3 = st.columns(3)
    status_filter = col1.selectbox("Estado", ["(todos)", "open", "upcoming", "closed"])
    all_regions = sorted({r for i in incentives for r in i.regions})
    region_filter = col2.selectbox("Región", ["(todas)", *all_regions])
    search = col3.text_input("Buscar en el título")

    filtered = incentives
    if status_filter != "(todos)":
        filtered = [i for i in filtered if i.status == status_filter]
    if region_filter != "(todas)":
        filtered = [i for i in filtered if region_filter in i.regions]
    if search:
        filtered = [i for i in filtered if search.lower() in i.title.lower()]

    st.caption(f"{len(filtered)} incentivo(s)")
    if not filtered:
        return

    selection = st.dataframe(
        _incentives_dataframe(filtered),
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
    )

    selected_rows = selection.selection.rows if selection is not None else []
    if selected_rows:
        incentive = filtered[selected_rows[0]]
        st.subheader(incentive.title)
        st.write(f"**Fuente:** {incentive.source} | **Estado:** {incentive.status}")
        if incentive.url:
            st.write(f"**URL oficial:** {incentive.url}")
        st.write(incentive.description or "_Sin descripción_")
        with st.expander("Ver todos los campos"):
            st.json(incentive.model_dump(mode="json"))


def _tenders_dataframe(tenders: list[Tender]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ID": t.source_id,
                "Fuente": t.source,
                "Título": t.title,
                "Estado": t.status,
                "Cierre": t.close_date.date().isoformat() if t.close_date else "-",
                "Importe": f"{t.estimated_value:.0f}" if t.estimated_value is not None else "-",
                "CPV": ", ".join(t.cpv_codes),
                "Provincia": t.province or "-",
            }
            for t in tenders
        ]
    )


def render_tender_list_tab(tenders: list[Tender]) -> None:
    col1, col2, col3 = st.columns(3)
    status_filter = col1.selectbox("Estado", ["(todos)", "open", "upcoming", "closed"], key="gare_status_filter")
    all_provinces = sorted({t.province for t in tenders if t.province})
    province_filter = col2.selectbox("Provincia", ["(todas)", *all_provinces], key="gare_province_filter")
    search = col3.text_input("Buscar en el título", key="gare_search")

    filtered = tenders
    if status_filter != "(todos)":
        filtered = [t for t in filtered if t.status == status_filter]
    if province_filter != "(todas)":
        filtered = [t for t in filtered if t.province == province_filter]
    if search:
        filtered = [t for t in filtered if search.lower() in t.title.lower()]

    st.caption(f"{len(filtered)} gara(s)")
    if not filtered:
        return

    selection = st.dataframe(
        _tenders_dataframe(filtered),
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="gare_table",
    )

    selected_rows = selection.selection.rows if selection is not None else []
    if selected_rows:
        tender = filtered[selected_rows[0]]
        st.subheader(tender.title)
        st.write(f"**Fuente:** {tender.source} | **Estado:** {tender.status}")
        if tender.buyer_name:
            st.write(f"**Ente convocante:** {tender.buyer_name}")
        if tender.url:
            st.write(f"**URL oficial:** {tender.url}")
        st.write(tender.description or "_Sin descripción_")
        with st.expander("Ver todos los campos"):
            st.json(tender.model_dump(mode="json"))


def render_profile_editor_tab() -> None:
    if "profile" not in st.session_state:
        st.session_state.profile = None

    if st.button("Cargar perfil de ejemplo (startup)") and EXAMPLE_PROFILE_PATH.exists():
        st.session_state.profile = load_company_profile(EXAMPLE_PROFILE_PATH)

    current = st.session_state.profile

    with st.form("profile_form"):
        name = st.text_input("Nombre de la empresa", value=current.name if current else "")
        region = st.selectbox(
            "Región",
            [r.value for r in Region],
            index=[r.value for r in Region].index(current.region.value) if current else 0,
        )
        size = st.selectbox(
            "Tamaño",
            [s.value for s in CompanySize],
            index=[s.value for s in CompanySize].index(current.size.value) if current else 0,
        )
        province = st.text_input("Provincia (sigla)", value=current.province if current and current.province else "")
        founded_on = st.date_input("Fecha de constitución", value=current.founded_on if current else None)
        legal_form_options = ["(sin especificar)", *[f.value for f in LegalForm]]
        legal_form = st.selectbox(
            "Forma jurídica",
            legal_form_options,
            index=legal_form_options.index(current.legal_form.value) if current and current.legal_form else 0,
        )
        ateco_raw = st.text_input(
            "Códigos ATECO (separados por coma) - para incentivos",
            value=", ".join(c.code for c in current.ateco_codes) if current else "",
        )
        cpv_raw = st.text_input(
            "Códigos CPV (separados por coma) - para gare/tenders, clasificación distinta de ATECO",
            value=", ".join(current.cpv_codes) if current else "",
        )

        col1, col2, col3, col4 = st.columns(4)
        is_startup_innovativa = col1.checkbox("Startup innovativa", value=current.is_startup_innovativa if current else False)
        is_pmi_innovativa = col2.checkbox("PMI innovativa", value=current.is_pmi_innovativa if current else False)
        is_impresa_femminile = col3.checkbox("Impresa femminile", value=current.is_impresa_femminile if current else False)
        is_under_35 = col4.checkbox("Under 35", value=current.is_under_35 if current else False)

        planned_expense_types = st.multiselect(
            "Gastos previstos",
            [c.value for c in EligibleCost],
            default=current.planned_expense_types if current else [],
        )
        planned_investment_amount = st.number_input(
            "Inversión prevista (€)", min_value=0.0, value=float(current.planned_investment_amount or 0) if current else 0.0
        )
        preferred_support_forms = st.multiselect(
            "Formas de agevolación preferidas",
            [f.value for f in SupportForm],
            default=current.preferred_support_forms if current else [],
        )

        submitted = st.form_submit_button("Guardar perfil")

    if submitted:
        if not name or not (ateco_raw.strip() or cpv_raw.strip()):
            st.error("Nombre y al menos un código ATECO (incentivos) o CPV (gare) son obligatorios.")
        else:
            st.session_state.profile = CompanyProfile(
                name=name,
                region=Region(region),
                size=CompanySize(size),
                province=province or None,
                founded_on=founded_on,
                legal_form=LegalForm(legal_form) if legal_form != "(sin especificar)" else None,
                ateco_codes=[AtecoCode(code=c.strip()) for c in ateco_raw.split(",") if c.strip()],
                cpv_codes=[c.strip() for c in cpv_raw.split(",") if c.strip()],
                is_startup_innovativa=is_startup_innovativa,
                is_pmi_innovativa=is_pmi_innovativa,
                is_impresa_femminile=is_impresa_femminile,
                is_under_35=is_under_35,
                planned_expense_types=planned_expense_types,
                planned_investment_amount=planned_investment_amount or None,
                preferred_support_forms=preferred_support_forms,
            )
            st.success("Perfil guardado para esta sesión.")

    if st.session_state.profile:
        with st.expander("Ver perfil actual (JSON)"):
            st.json(st.session_state.profile.model_dump(mode="json"))


def render_incentive_matching_tab(incentives: list[Incentive], profile: CompanyProfile) -> None:
    col1, col2 = st.columns(2)
    top = col1.slider("Máximo de resultados", 1, 50, 10, key="incentive_match_top")
    min_score = col2.slider("Score mínimo", 0, 100, 0, key="incentive_match_min_score")

    results = match_profile(incentives, profile, weights=DEFAULT_WEIGHTS)
    results = [r for r in results if r.score >= min_score][:top]

    st.caption(f"{len(results)} incentivo(s) elegible(s)")
    for result in results:
        with st.expander(f"{result.incentive.title} — score {result.score}"):
            if result.incentive.url:
                st.write(result.incentive.url)
            for reason in result.explanation.reasons_for:
                st.write(f"✅ {reason}")
            for reason in result.explanation.reasons_against:
                st.write(f"❌ {reason}")
            for reason in result.explanation.unverifiable:
                st.write(f"❓ {reason}")


def render_tender_matching_tab(tenders: list[Tender], profile: CompanyProfile) -> None:
    if not profile.cpv_codes:
        st.info("Este perfil no tiene códigos CPV configurados - agregalos en 'Perfil de empresa' para matchear gare.")
        return

    col1, col2 = st.columns(2)
    top = col1.slider("Máximo de resultados", 1, 50, 10, key="tender_match_top")
    min_score = col2.slider("Score mínimo", 0, 100, 0, key="tender_match_min_score")

    results = match_tender_profile(tenders, profile, weights=DEFAULT_TENDER_WEIGHTS)
    results = [r for r in results if r.score >= min_score][:top]

    st.caption(f"{len(results)} gara(s) elegible(s)")
    for result in results:
        with st.expander(f"{result.tender.title} — score {result.score}"):
            st.write(f"Fuente: {result.tender.source}")
            if result.tender.url:
                st.write(result.tender.url)
            for reason in result.explanation.reasons_for:
                st.write(f"✅ {reason}")
            for reason in result.explanation.reasons_against:
                st.write(f"❌ {reason}")
            for reason in result.explanation.unverifiable:
                st.write(f"❓ {reason}")


def render_matching_tab(incentives: list[Incentive], tenders: list[Tender]) -> None:
    profile: CompanyProfile | None = st.session_state.get("profile")
    if profile is None:
        st.info("Primero cargá o creá un perfil en la pestaña 'Perfil de empresa'.")
        return

    st.caption(f"Perfil actual: **{profile.name}**")
    sub_incentives, sub_gare = st.tabs(["Incentivos", "Gare"])
    with sub_incentives:
        render_incentive_matching_tab(incentives, profile)
    with sub_gare:
        render_tender_matching_tab(tenders, profile)


def main() -> None:
    st.set_page_config(page_title="AgevolaMatch", layout="wide")
    st.title("AgevolaMatch")
    st.caption(
        "Herramienta informativa: verificá siempre los requisitos de elegibilidad "
        "en la fuente oficial de cada incentivo antes de presentar una solicitud."
    )

    incentives = _load_all_incentives()
    tenders = _load_all_tenders()
    if not incentives and not tenders:
        st.warning(
            "No hay datos almacenados. Corré `agevolamatch ingest` (incentivos) "
            "y/o `agevolamatch gare ingest` (gare) primero."
        )
        return

    tab_incentives, tab_gare, tab_profile, tab_match = st.tabs(
        ["📋 Incentivos", "📄 Gare", "🏢 Perfil de empresa", "🎯 Matching"]
    )
    with tab_incentives:
        if incentives:
            render_incentive_list_tab(incentives)
        else:
            st.info("No hay incentivos almacenados. Corré `agevolamatch ingest` primero.")
    with tab_gare:
        if tenders:
            render_tender_list_tab(tenders)
        else:
            st.info("No hay gare almacenadas. Corré `agevolamatch gare ingest` primero.")
    with tab_profile:
        render_profile_editor_tab()
    with tab_match:
        render_matching_tab(incentives, tenders)


main()
