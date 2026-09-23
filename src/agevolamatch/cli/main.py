from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table
from sqlmodel import select

from agevolamatch.alerts import default_channels, load_subscriptions, run_alerts
from agevolamatch.export import incentive_records_to_rows, match_results_to_rows, write_rows
from agevolamatch.matching import (
    DEFAULT_WEIGHTS,
    ScoringWeights,
    load_company_profile,
    match_profile,
)
from agevolamatch.matching.llm import enrich_with_llm_requirements, get_llm_provider
from agevolamatch.models.enums import OpportunitySourceName
from agevolamatch.sources.anac import ANACSource
from agevolamatch.sources.dedup import find_duplicate
from agevolamatch.sources.incentivi_gov_it import IncentiviGovItSource
from agevolamatch.sources.invitalia import InvitaliaSource
from agevolamatch.sources.ted import TEDSource
from agevolamatch.storage import (
    DEFAULT_DB_PATH,
    get_engine,
    get_session,
    init_db,
    load_incentives,
    load_tenders,
    upsert_opportunities,
)
from agevolamatch.storage.tables import OpportunityRecord
from agevolamatch.tenders import DEFAULT_TENDER_WEIGHTS, match_tender_profile

app = typer.Typer(help="AgevolaMatch: matching engine for Italian public incentives (finanza agevolata)")
alerts_app = typer.Typer(help="Manage and run alert subscriptions")
app.add_typer(alerts_app, name="alerts")
gare_app = typer.Typer(help="Gare d'appalto (public tenders) - ANAC + TED, a separate domain from incentives")
app.add_typer(gare_app, name="gare")
console = Console()


def _load_stored_incentives(db_path: Path):
    engine = get_engine(db_path)
    init_db(engine)
    with get_session(engine) as session:
        return load_incentives(session)


_INGEST_SOURCES = {"incentivi_gov_it", "invitalia", "all"}


@app.command()
def ingest(
    source: Annotated[str, typer.Option(help="incentivi_gov_it, invitalia, or all")] = "incentivi_gov_it",
    db_path: Annotated[Path, typer.Option(help="SQLite database path")] = DEFAULT_DB_PATH,
    verbose: Annotated[bool, typer.Option(help="Enable debug logging")] = False,
) -> None:
    """Fetch incentives and store new/modified records."""
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO)

    if source not in _INGEST_SOURCES:
        console.print(f"[red]Fuente desconocida: {source!r} (opciones: {', '.join(sorted(_INGEST_SOURCES))})[/red]")
        raise typer.Exit(code=1)

    engine = get_engine(db_path)
    init_db(engine)

    sources_to_run = []
    if source in ("incentivi_gov_it", "all"):
        sources_to_run.append(IncentiviGovItSource())
    if source in ("invitalia", "all"):
        sources_to_run.append(InvitaliaSource())

    for src in sources_to_run:
        try:
            opportunities = src.run()
        except Exception as exc:
            console.print(f"[red]{src.name}: fetch failed, skipping this source ({exc})[/red]")
            continue

        if src.name == OpportunitySourceName.INVITALIA.value:
            with get_session(engine) as session:
                reference_incentives = [
                    i for i in load_incentives(session) if i.source == OpportunitySourceName.INCENTIVI_GOV_IT
                ]
            deduped, skipped = [], 0
            for opp in opportunities:
                if find_duplicate(opp.title, reference_incentives) is not None:
                    skipped += 1
                else:
                    deduped.append(opp)
            opportunities = deduped
            if skipped:
                console.print(f"[dim]Invitalia: {skipped} medida(s) descartadas por duplicar incentivi.gov.it[/dim]")

        with get_session(engine) as session:
            summary = upsert_opportunities(session, opportunities)

        console.print(
            f"[green]{src.name}[/green]: {summary.total} total, "
            f"[bold]{len(summary.new)}[/bold] new, "
            f"[bold]{len(summary.modified)}[/bold] modified, "
            f"{len(summary.unchanged)} unchanged"
        )


@app.command(name="list")
def list_opportunities(
    db_path: Annotated[Path, typer.Option(help="SQLite database path")] = DEFAULT_DB_PATH,
    status: Annotated[str | None, typer.Option(help="Filter by status: open, upcoming, closed")] = None,
    region: Annotated[str | None, typer.Option(help="Filter by region name, e.g. Lazio")] = None,
    limit: Annotated[int, typer.Option(help="Max rows to display")] = 50,
) -> None:
    """List stored opportunities with optional filters."""
    engine = get_engine(db_path)
    init_db(engine)

    with get_session(engine) as session:
        query = select(OpportunityRecord)
        if status:
            query = query.where(OpportunityRecord.status == status)
        query = query.order_by(OpportunityRecord.close_date).limit(limit)
        records = session.exec(query).all()

    if region:
        records = [r for r in records if region in (r.payload.get("regions") or [])]

    table = Table(title="Incentives")
    table.add_column("ID")
    table.add_column("Title", max_width=60)
    table.add_column("Status")
    table.add_column("Close date")
    table.add_column("Regions")

    for record in records:
        regions = ", ".join(record.payload.get("regions") or [])
        table.add_row(
            record.source_id,
            record.title,
            record.status,
            record.close_date.date().isoformat() if record.close_date else "-",
            regions,
        )

    console.print(table)
    console.print(f"[dim]{len(records)} record(s) shown[/dim]")


@app.command()
def match(
    profile: Annotated[Path, typer.Option(help="Path to a CompanyProfile YAML file")],
    db_path: Annotated[Path, typer.Option(help="SQLite database path")] = DEFAULT_DB_PATH,
    weights: Annotated[Path | None, typer.Option(help="Optional YAML file overriding scoring weights")] = None,
    top: Annotated[int, typer.Option(help="Max results to display")] = 20,
    min_score: Annotated[float, typer.Option(help="Hide results scoring below this threshold")] = 0.0,
    llm: Annotated[
        bool,
        typer.Option(
            "--llm/--no-llm",
            help="Optionally extract extra eligibility requirements from descriptions via an LLM (off by default; needs AGEVOLAMATCH_LLM_PROVIDER)",
        ),
    ] = False,
) -> None:
    """Rank stored incentives against a company profile, with explanations."""
    company_profile = load_company_profile(profile)
    scoring_weights = ScoringWeights.from_yaml(weights) if weights else DEFAULT_WEIGHTS
    incentives = _load_stored_incentives(db_path)

    if not incentives:
        console.print("[yellow]No hay incentivos almacenados. Corré `agevolamatch ingest` primero.[/yellow]")
        raise typer.Exit(code=1)

    results = match_profile(incentives, company_profile, weights=scoring_weights)
    results = [r for r in results if r.score >= min_score][:top]

    if llm:
        provider = get_llm_provider()
        if provider is None:
            console.print(
                "[yellow]--llm pedido pero AGEVOLAMATCH_LLM_PROVIDER no está configurado en .env; "
                "continuando sin enriquecimiento LLM.[/yellow]\n"
            )
        else:
            results = enrich_with_llm_requirements(results, provider)

    console.print(f"[bold]{company_profile.name}[/bold] - {len(results)} incentivo(s) elegible(s) mostrados\n")

    for rank, result in enumerate(results, start=1):
        incentive = result.incentive
        console.print(f"[bold cyan]{rank}. {incentive.title}[/bold cyan]  [green]score={result.score}[/green]")
        console.print(f"   [dim]{incentive.url or 'sin URL'}[/dim]")
        for reason in result.explanation.reasons_for:
            console.print(f"   [green]+[/green] {reason}")
        for reason in result.explanation.reasons_against:
            console.print(f"   [red]-[/red] {reason}")
        for reason in result.explanation.unverifiable:
            console.print(f"   [yellow]?[/yellow] {reason}")
        console.print()

    if not results:
        console.print("[yellow]Ningún incentivo elegible superó el umbral de score configurado.[/yellow]")


@app.command()
def export(
    output: Annotated[Path, typer.Option(help="Output file path")],
    format: Annotated[str, typer.Option(help="csv or json")] = "json",
    db_path: Annotated[Path, typer.Option(help="SQLite database path")] = DEFAULT_DB_PATH,
    profile: Annotated[Path | None, typer.Option(help="If given, exports match results for this profile instead of raw incentives")] = None,
    weights: Annotated[Path | None, typer.Option(help="Optional YAML file overriding scoring weights")] = None,
    status: Annotated[str | None, typer.Option(help="Filter by status (only applies without --profile)")] = None,
) -> None:
    """Export stored incentives, or match results for a profile, to CSV/JSON."""
    if format not in {"csv", "json"}:
        console.print(f"[red]Formato no soportado: {format} (usar csv o json)[/red]")
        raise typer.Exit(code=1)

    if profile:
        company_profile = load_company_profile(profile)
        scoring_weights = ScoringWeights.from_yaml(weights) if weights else DEFAULT_WEIGHTS
        incentives = _load_stored_incentives(db_path)
        results = match_profile(incentives, company_profile, weights=scoring_weights)
        rows = match_results_to_rows(results)
    else:
        engine = get_engine(db_path)
        init_db(engine)
        with get_session(engine) as session:
            query = select(OpportunityRecord)
            if status:
                query = query.where(OpportunityRecord.status == status)
            records = session.exec(query).all()
        rows = incentive_records_to_rows(records)

    write_rows(rows, output, format)
    console.print(f"[green]Exportados {len(rows)} registro(s) a {output}[/green]")


@alerts_app.command("run")
def alerts_run(
    subscriptions: Annotated[Path, typer.Option(help="Path to an alert subscriptions YAML file")],
    db_path: Annotated[Path, typer.Option(help="SQLite database path")] = DEFAULT_DB_PATH,
    dry_run: Annotated[bool, typer.Option(help="Preview without actually sending or recording alerts")] = True,
) -> None:
    """Send alerts for new/modified incentives matching saved subscriptions.

    Never resends an alert for the same incentive content twice (see CLAUDE.md).
    Defaults to --dry-run; pass --no-dry-run to actually deliver alerts.
    """
    subs = load_subscriptions(subscriptions)
    if not subs:
        console.print(f"[yellow]No hay suscripciones en {subscriptions}[/yellow]")
        raise typer.Exit(code=1)

    engine = get_engine(db_path)
    init_db(engine)
    with get_session(engine) as session:
        incentives = load_incentives(session)
        summary = run_alerts(session, incentives, subs, default_channels(), dry_run=dry_run)

    mode = "[yellow]DRY RUN[/yellow]" if dry_run else "[green]ENVIADO[/green]"
    console.print(f"{mode} - {summary.total} alerta(s) {'simuladas' if dry_run else 'procesadas'}\n")
    for event in summary.events:
        console.print(f"  [{event.subscription_name}] {event.title} (score {event.score}) -> {', '.join(event.channels)}")

    if not summary.events:
        console.print("[dim]Ningún incentivo nuevo/modificado supera el umbral configurado.[/dim]")


@app.command()
def serve(
    host: Annotated[str, typer.Option(help="Bind host")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Bind port")] = 8000,
    reload: Annotated[bool, typer.Option(help="Auto-reload on code changes (development only)")] = False,
) -> None:
    """Run the REST API (equivalent to `uvicorn agevolamatch.api.app:app`)."""
    import uvicorn

    uvicorn.run("agevolamatch.api.app:app", host=host, port=port, reload=reload)


_GARE_INGEST_SOURCES = {"anac", "ted", "all"}


@gare_app.command("ingest")
def gare_ingest(
    source: Annotated[str, typer.Option(help="anac, ted, or all")] = "all",
    db_path: Annotated[Path, typer.Option(help="SQLite database path")] = DEFAULT_DB_PATH,
    verbose: Annotated[bool, typer.Option(help="Enable debug logging")] = False,
) -> None:
    """Fetch public tenders (ANAC and/or TED) and store new/modified records."""
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO)

    if source not in _GARE_INGEST_SOURCES:
        console.print(f"[red]Fuente desconocida: {source!r} (opciones: {', '.join(sorted(_GARE_INGEST_SOURCES))})[/red]")
        raise typer.Exit(code=1)

    engine = get_engine(db_path)
    init_db(engine)

    sources_to_run = []
    if source in ("anac", "all"):
        sources_to_run.append(ANACSource())
    if source in ("ted", "all"):
        sources_to_run.append(TEDSource())

    for src in sources_to_run:
        try:
            tenders = src.run()
        except Exception as exc:
            console.print(f"[red]{src.name}: fetch failed, skipping this source ({exc})[/red]")
            continue
        with get_session(engine) as session:
            summary = upsert_opportunities(session, tenders)
        console.print(
            f"[green]{src.name}[/green]: {summary.total} total, "
            f"[bold]{len(summary.new)}[/bold] new, "
            f"[bold]{len(summary.modified)}[/bold] modified, "
            f"{len(summary.unchanged)} unchanged"
        )


@gare_app.command("match")
def gare_match(
    profile: Annotated[Path, typer.Option(help="Path to a CompanyProfile YAML file (needs cpv_codes set)")],
    db_path: Annotated[Path, typer.Option(help="SQLite database path")] = DEFAULT_DB_PATH,
    top: Annotated[int, typer.Option(help="Max results to display")] = 20,
    min_score: Annotated[float, typer.Option(help="Hide results scoring below this threshold")] = 0.0,
) -> None:
    """Rank stored tenders against a company profile, with explanations."""
    company_profile = load_company_profile(profile)
    engine = get_engine(db_path)
    init_db(engine)
    with get_session(engine) as session:
        tenders = load_tenders(session)

    if not tenders:
        console.print("[yellow]No hay gare almacenadas. Corré `agevolamatch gare ingest` primero.[/yellow]")
        raise typer.Exit(code=1)

    results = match_tender_profile(tenders, company_profile, weights=DEFAULT_TENDER_WEIGHTS)
    results = [r for r in results if r.score >= min_score][:top]

    console.print(f"[bold]{company_profile.name}[/bold] - {len(results)} gara(s) elegible(s) mostrada(s)\n")

    for rank, result in enumerate(results, start=1):
        tender = result.tender
        console.print(f"[bold cyan]{rank}. {tender.title}[/bold cyan]  [green]score={result.score}[/green]")
        console.print(f"   [dim]{tender.url or 'sin URL'} | fuente: {tender.source}[/dim]")
        for reason in result.explanation.reasons_for:
            console.print(f"   [green]+[/green] {reason}")
        for reason in result.explanation.reasons_against:
            console.print(f"   [red]-[/red] {reason}")
        for reason in result.explanation.unverifiable:
            console.print(f"   [yellow]?[/yellow] {reason}")
        console.print()

    if not results:
        console.print("[yellow]Ninguna gara elegible superó el umbral de score configurado.[/yellow]")


if __name__ == "__main__":
    app()
