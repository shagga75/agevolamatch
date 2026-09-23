from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table
from sqlmodel import select

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


if __name__ == "__main__":
    app()
