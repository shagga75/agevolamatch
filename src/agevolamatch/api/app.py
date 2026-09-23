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

from agevolamatch.matching import DEFAULT_WEIGHTS, MatchResult, match_profile
from agevolamatch.models.company_profile import CompanyProfile
from agevolamatch.models.opportunity import Incentive, Tender
from agevolamatch.storage import (
    get_engine,
    get_incentive_record,
    get_session,
    get_tender_record,
    init_db,
    load_incentives,
    load_tenders,
)
from agevolamatch.tenders import DEFAULT_TENDER_WEIGHTS, TenderMatchResult, match_tender_profile


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
        "Read-only view of ingested Italian public incentives and tenders "
        "(gare d'appalto), plus matching against a CompanyProfile. "
        "Informational only - always verify eligibility against the "
        "official source before applying."
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
        record = get_incentive_record(session, source_id)
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


@app.get("/tenders", response_model=list[Tender])
def list_tenders(
    status: str | None = None,
    province: str | None = None,
    limit: int = Query(default=50, le=500),
) -> list[Tender]:
    """Gare d'appalto (public tenders) - ANAC + TED, a separate domain from
    incentives (see CLAUDE.md). Same thin-wrapper pattern as /incentives."""
    with get_session(_current_engine()) as session:
        tenders = load_tenders(session, status=status)
    if province:
        tenders = [t for t in tenders if t.province == province]
    return tenders[:limit]


@app.get("/tenders/{source_id}", response_model=Tender)
def get_tender(source_id: str) -> Tender:
    with get_session(_current_engine()) as session:
        record = get_tender_record(session, source_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No tender with source_id={source_id!r}")
    return Tender.model_validate(record.payload)


@app.post("/tenders/match", response_model=list[TenderMatchResult])
def match_tenders(
    profile: CompanyProfile,
    top: int = Query(default=20, le=200),
    min_score: float = 0.0,
) -> list[TenderMatchResult]:
    """profile.cpv_codes drives tender matching (separate from ateco_codes,
    which drives /match for incentives)."""
    with get_session(_current_engine()) as session:
        tenders = load_tenders(session)
    results = match_tender_profile(tenders, profile, weights=DEFAULT_TENDER_WEIGHTS)
    return [r for r in results if r.score >= min_score][:top]
