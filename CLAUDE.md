# CLAUDE.md

Project conventions and architecture decisions for AgevolaMatch. Read this
before making non-trivial changes.

## What this is

An open-source matching engine between Italian public incentives (finanza
agevolata) and company profiles. See `docs/sources.md` for data sources and
`docs/inspiration.md` for prior art. `README.md` / `README.it.md` cover
end-user usage.

## Commands

```bash
uv sync                          # install deps (dev group included by default)
uv run pytest -q                 # run tests (no network access required - all fixtures)
uv run ruff check .              # lint
uv run ruff check --fix .        # lint + autofix
uv run ruff format .             # format
uv run python scripts/export_schemas.py   # regenerate schemas/*.json after model changes

uv run agevolamatch ingest       # fetch + store incentives from incentivi.gov.it
uv run agevolamatch list --status open --region Lazio
```

## Architecture decisions

- **Opportunity/Incentive/Tender split**: `Opportunity` (in
  `models/opportunity.py`) is the base shared by anything a company can apply
  to. `Incentive` is the only subtype implemented so far (Fase 1-3); `Tender`
  (gare d'appalto, Fase 5) will be added the same way, so matching/alerts code
  written against `Opportunity` doesn't need to change.
- **No status field from the source**: incentivi.gov.it doesn't expose one.
  `status` (open/upcoming/closed/unknown) is *computed* at ingest time from
  `open_date`/`close_date` (`sources/parsing.py::compute_status`), and
  re-computed (and persisted) on every ingest run even when nothing else about
  a record changed - see `storage/repository.py`'s "unchanged" branch.
- **Change detection via content hash, not the source's own timestamp**:
  `Data_ultimo_aggiornamento` (`source_last_updated`) is stored for reference,
  but "new vs. modified vs. unchanged" is decided by comparing
  `content_hash` (sha256 over the normalized payload, excluding volatile
  bookkeeping fields - see `compute_content_hash`). Records are never
  deleted, so closed incentives remain queryable as history.
- **Storage is one JSON-payload table, not one column per field**
  (`storage/tables.py::OpportunityRecord`). Only the columns actual queries
  filter/sort on are indexed (source, source_id, status, close_date). This
  keeps the schema stable as `Incentive` gains fields or `Tender` is added,
  at the cost of not being able to do arbitrary SQL WHERE clauses on payload
  fields (matching/filtering logic loads the payload into a Pydantic model
  and filters in Python instead).
- **BaseSource.run() never lets one bad record kill an ingest**: `normalize()`
  is allowed to raise; `run()` catches, logs, and continues. This is a hard
  requirement (see `docs/sources.md` for the messy fields that make this
  necessary - e.g. `Stanziamento_incentivo`'s inconsistent formatting).
- **Free-text ATECO handling**: 71% of `Codici_ATECO` values are the prose
  "all sectors eligible" pattern rather than real codes. `ateco_all_sectors:
  bool` exists specifically so downstream matching doesn't need to
  string-match that prose itself.
- **`startup_or_pmi_innovativa_ambiguous`**: the source conflates "startup
  innovativa" and "PMI innovativa" into one value. This flag marks that
  conflation explicitly on `Incentive` rather than silently guessing which
  one it means - matching logic (Fase 2) is the layer that decides how to
  treat the ambiguity, not the ingestion layer.
- **HTTP caching is a flat file cache** (`sources/http_cache.py`), keyed by
  full URL with a TTL, deliberately minimal (no extra dependency). If a
  second source needs different caching semantics, revisit before adding
  a library.
- **No LLM by default anywhere.** Matching (Fase 2) is 100% deterministic
  (hard filters + configurable weighted score + explanation). Any LLM
  integration point must be optional and behind an explicit opt-in.

## Testing

- Tests never touch the network. `tests/fixtures/incentivi_gov_it_sample.json`
  is a curated 37-record sample of the *real* dataset (not synthetic),
  deliberately covering edge cases: Estero region, ATECO with real codes vs.
  the "all sectors" prose pattern, missing Comuni, ZES/Aree interne/Zone
  sismiche special territories, SU/PMI innovativa ambiguity, duplicate
  titles, messy `Stanziamento_incentivo` formats, missing optional fields.
  See `docs/sources.md` for how/why each case was picked.
- `tests/unit/test_ingest_pipeline.py` runs the full fetch-skipped pipeline
  (normalize → upsert against a real in-memory SQLite engine) rather than
  unit-testing each layer in isolation - this is what caught a real bug
  (naive vs. timezone-aware datetimes) that neither layer's isolated tests
  exercised. Prefer adding to this file over trusting layer-level tests alone
  when touching normalize() or the storage layer.
- Ruff must be clean (`uv run ruff check .`) before considering a phase done.

## Non-goals / explicit decisions from Fase 0

- ATECO 2007↔2025 official correspondence table: not yet integrated (TODO,
  Fase 2). Until then, ATECO prefix matching treats both versions the same.
- Comune→provincia lookup: not yet integrated (TODO, Fase 2) - needed to
  match a company's province against a `municipalities`-restricted incentive.
- Invitalia dedup (Fase 4) will match on (normalized title, granting body,
  dates) since there's no shared external ID with incentivi.gov.it.
