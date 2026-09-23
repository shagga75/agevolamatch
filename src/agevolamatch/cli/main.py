from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table
from sqlmodel import select

from agevolamatch.export import incentive_records_to_rows, match_results_to_rows, write_rows
from agevolamatch.matching import (
    DEFAULT_WEIGHTS,
    ScoringWeights,
    load_company_profile,
    match_profile,
)
from agevolamatch.models.opportunity import Incentive
from agevolamatch.sources.incentivi_gov_it import IncentiviGovItSource
from agevolamatch.storage import (
    DEFAULT_DB_PATH,
    get_engine,
    get_session,
    init_db,
    upsert_opportunities,
)
from agevolamatch.storage.tables import OpportunityRecord

app = typer.Typer(help="AgevolaMatch: matching engine for Italian public incentives (finanza agevolata)")
console = Console()


def _load_stored_incentives(db_path: Path) -> list[Incentive]:
    engine = get_engine(db_path)
    init_db(engine)
    with get_session(engine) as session:
        records = session.exec(select(OpportunityRecord)).all()
    return [Incentive.model_validate(r.payload) for r in records]


@app.command()
def ingest(
    db_path: Annotated[Path, typer.Option(help="SQLite database path")] = DEFAULT_DB_PATH,
    verbose: Annotated[bool, typer.Option(help="Enable debug logging")] = False,
) -> None:
    """Fetch incentives from incentivi.gov.it and store new/modified records."""
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO)

    engine = get_engine(db_path)
    init_db(engine)

    source = IncentiviGovItSource()
    opportunities = source.run()

    with get_session(engine) as session:
        summary = upsert_opportunities(session, opportunities)

    console.print(
        f"[green]Ingest complete[/green]: {summary.total} total, "
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


if __name__ == "__main__":
    app()
