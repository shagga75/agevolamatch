"""MCP server exposing search and matching, so an MCP client (e.g. Claude
Desktop) can query and match incentives directly. Same pattern as the REST
API: a thin wrapper over storage/matching, no separate implementation.

Uses `mcp.server.mcpserver.MCPServer` (the mcp>=2.0 API - the SDK renamed
`FastMCP` to `MCPServer` between 1.x and 2.x; confirmed against the actually
installed version rather than assumed from training data).
"""

from __future__ import annotations

import os
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import ValidationError
from sqlmodel import Session, select

from agevolamatch.matching import DEFAULT_WEIGHTS, match_profile
from agevolamatch.models.company_profile import CompanyProfile
from agevolamatch.storage import get_engine, get_session, init_db, load_incentives
from agevolamatch.storage.tables import OpportunityRecord

mcp = MCPServer(
    name="agevolamatch",
    instructions=(
        "Search and match Italian public incentives (finanza agevolata) for startups and SMEs. "
        "Informational only - always verify eligibility against each incentive's official url before applying."
    ),
)


def _db_path() -> Path:
    return Path(os.environ.get("AGEVOLAMATCH_DB_PATH", "data/agevolamatch.db"))


def _open_session() -> Session:
    engine = get_engine(_db_path())
    init_db(engine)
    return get_session(engine)


@mcp.tool()
def search_incentives(status: str | None = None, region: str | None = None, limit: int = 20) -> list[dict]:
    """Search stored Italian public incentives. status: 'open', 'upcoming', or 'closed'. region: e.g. 'Lazio'."""
    with _open_session() as session:
        incentives = load_incentives(session, status=status)
    if region:
        incentives = [i for i in incentives if region in i.regions]
    return [i.model_dump(mode="json") for i in incentives[:limit]]


@mcp.tool()
def get_incentive(source_id: str) -> dict | None:
    """Get full stored details for one incentive by its source_id. Returns null if unknown."""
    with _open_session() as session:
        record = session.exec(select(OpportunityRecord).where(OpportunityRecord.source_id == source_id)).first()
    return record.payload if record else None


@mcp.tool()
def match_company_profile(profile: dict, top: int = 10, min_score: float = 0.0) -> list[dict]:
    """Rank stored incentives against a company profile, with explanations.

    profile must match schemas/company_profile.schema.json: at minimum
    {"name": str, "region": str, "size": str}, optionally ateco_codes,
    province, founded_on, legal_form, the is_* flags, planned_expense_types,
    planned_investment_amount, preferred_support_forms.
    """
    try:
        company_profile = CompanyProfile.model_validate(profile)
    except ValidationError as exc:
        # A malformed profile is the caller's mistake, not a server crash -
        # raising ToolError (rather than letting ValidationError propagate)
        # is what makes the SDK return a graceful CallToolResult(is_error=True)
        # instead of an UnexpectedToolError.
        raise ToolError(f"Invalid company profile: {exc}") from exc
    with _open_session() as session:
        incentives = load_incentives(session)
    results = match_profile(incentives, company_profile, weights=DEFAULT_WEIGHTS)
    results = [r for r in results if r.score >= min_score][:top]
    return [r.model_dump(mode="json") for r in results]


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
