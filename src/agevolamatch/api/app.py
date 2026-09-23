"""FastAPI mirror of the CLI's read/match surface. Same storage layer, same
matching engine - this is a thin HTTP wrapper, not a second implementation.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from sqlalchemy import Engine
from sqlmodel import select

from agevolamatch.matching import DEFAULT_WEIGHTS, MatchResult, match_profile
from agevolamatch.models.company_profile import CompanyProfile
from agevolamatch.models.opportunity import Incentive
from agevolamatch.storage import get_engine, get_session, init_db, load_incentives
from agevolamatch.storage.tables import OpportunityRecord


def _db_path() -> Path:
    return Path(os.environ.get("AGEVOLAMATCH_DB_PATH", "data/agevolamatch.db"))


@lru_cache
def _engine_for(path_str: str) -> Engine:
    return get_engine(Path(path_str))


def _current_engine() -> Engine:
    return _engine_for(str(_db_path()))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db(_current_engine())
    yield


app = FastAPI(
    title="AgevolaMatch API",
    description=(
        "Read-only view of ingested Italian public incentives, plus matching "
        "against a CompanyProfile. Informational only - always verify "
        "eligibility against the official source before applying."
    ),
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/incentives", response_model=list[Incentive])
def list_incentives(
    status: str | None = None,
    region: str | None = None,
    limit: int = Query(default=50, le=500),
) -> list[Incentive]:
    with get_session(_current_engine()) as session:
        incentives = load_incentives(session, status=status)
    if region:
        incentives = [i for i in incentives if region in i.regions]
    return incentives[:limit]


@app.get("/incentives/{source_id}", response_model=Incentive)
def get_incentive(source_id: str) -> Incentive:
    with get_session(_current_engine()) as session:
        record = session.exec(select(OpportunityRecord).where(OpportunityRecord.source_id == source_id)).first()
    if record is None:
        raise HTTPException(status_code=404, detail=f"No incentive with source_id={source_id!r}")
    return Incentive.model_validate(record.payload)


@app.post("/match", response_model=list[MatchResult])
def match(
    profile: CompanyProfile,
    top: int = Query(default=20, le=200),
    min_score: float = 0.0,
) -> list[MatchResult]:
    with get_session(_current_engine()) as session:
        incentives = load_incentives(session)
    results = match_profile(incentives, profile, weights=DEFAULT_WEIGHTS)
    return [r for r in results if r.score >= min_score][:top]
