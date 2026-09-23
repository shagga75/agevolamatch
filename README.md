# AgevolaMatch

Open-source matching engine between Italian public incentives ("finanza
agevolata") and company profiles - built for startups and SMEs (PMI) trying to
find which incentives they actually qualify for.

*[Leggi questo README in italiano](README.it.md)*

> **Disclaimer**: this tool is informational only. Eligibility requirements
> must always be verified against the official source (`url` field on every
> incentive) before applying. AgevolaMatch does not submit applications and is
> not affiliated with any Italian public body.

## Status

Fase 1-3 (core ingestion + matching + API/alerts) are implemented and
validated against the live dataset. The dashboard and Invitalia scraper are on
the roadmap - see [Roadmap](#roadmap) below.

- ✅ **Fase 1 - Core**: repo structure, Pydantic models + JSON Schema,
  incentivi.gov.it source, SQLite storage with new/modified detection.
- ✅ **Fase 2 - Matching + CLI**: hard eligibility filters, configurable
  weighted score, explanations (reasons for/against/unverifiable), CSV/JSON
  export, example profile.
- ✅ **Fase 3 - API + alerts**: FastAPI REST API, email (SMTP) and Telegram
  alert channels with send-once dedup, Docker + docker-compose.
- ⏳ Fase 4 - Dashboard, Invitalia scraper, optional LLM, MCP server
- ⏳ Fase 5 - Public tenders (gare d'appalto): ANAC + TED, separate module

## Why

incentivi.gov.it lists thousands of incentives with inconsistent, hard-to-
filter metadata (see [`docs/sources.md`](docs/sources.md) for exactly how
messy: 71% of ATECO fields are free text, not codes; no status field;
inconsistent money formats). AgevolaMatch ingests that data, normalizes it
into a typed model, and will match it against a company profile with
transparent, explainable scoring - no LLM required for the core pipeline.

## Install

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone <this-repo>
cd agevolamatch
uv sync
```

## Usage

```bash
# Fetch incentives from incentivi.gov.it and store new/modified ones
uv run agevolamatch ingest

# List stored incentives, with filters
uv run agevolamatch list --status open --region Lazio --limit 20

# Rank stored incentives against a company profile, with explanations
uv run agevolamatch match --profile examples/startup_profile.yaml --top 10

# Export stored incentives (or, with --profile, match results) to CSV/JSON
uv run agevolamatch export --format csv --output incentives.csv --status open
uv run agevolamatch export --format json --output ranking.json --profile examples/startup_profile.yaml
```

`ingest` is safe to re-run: it only reports records as new or modified when
their content actually changed (see [`CLAUDE.md`](CLAUDE.md) for how change
detection works), and never deletes closed incentives - they remain queryable
as history.

`match` applies hard eligibility filters first (status, region, company size,
beneficiary type, ATECO, and a few checks that the source data simply can't
make more than "unverifiable" - see [`docs/sources.md`](docs/sources.md)),
then ranks the eligible incentives with a configurable weighted score, and
prints why each one scored the way it did. `examples/sample_match_output.json`
is a real (dated) snapshot of this output against the live dataset.

## REST API

```bash
uv run agevolamatch serve            # http://127.0.0.1:8000, docs at /docs
```

| Endpoint | Description |
|---|---|
| `GET /health` | Liveness check |
| `GET /incentives?status=&region=&limit=` | List stored incentives |
| `GET /incentives/{source_id}` | One incentive, 404 if unknown |
| `POST /match?top=&min_score=` | Body: a `CompanyProfile` JSON object. Returns ranked `MatchResult`s |

`AGEVOLAMATCH_DB_PATH` (also read from `.env`) selects which SQLite file the
API reads from.

## Alerts

Copy `.env.example` to `.env` and fill in either the SMTP or Telegram section
(or both). Then define one or more subscriptions - see
[`examples/alert_subscriptions.yaml`](examples/alert_subscriptions.yaml):

```yaml
subscriptions:
  - name: "startup-lazio"
    profile: examples/startup_profile.yaml
    min_score: 60
    channels: ["telegram"]
```

```bash
uv run agevolamatch alerts run --subscriptions examples/alert_subscriptions.yaml --dry-run
uv run agevolamatch alerts run --subscriptions examples/alert_subscriptions.yaml --no-dry-run
```

An alert fires only for an incentive that (a) is eligible and scores at or
above `min_score`, and (b) hasn't already been alerted at this exact content
- re-running never resends the same alert twice, and a genuinely modified
incentive (different `content_hash`) does trigger a new one. `--dry-run`
(the default) previews without sending anything or touching the dedup log.

## Docker

```bash
cp .env.example .env   # fill in SMTP/Telegram credentials as needed
docker compose up --build
```

This starts the `api` service (port 8000) and an `ingest` service that loops
`ingest` + `alerts run` on `INGEST_INTERVAL_SECONDS` (default: once a day).
`ingest`'s alerts step is a dry-run by default (`ALERTS_DRY_RUN=true` in
`docker-compose.yml`) - flip it to `false` once `.env` has real credentials
you've tested. Mount your own subscriptions file over
`examples/alert_subscriptions.yaml` in the `ingest` service's volumes.

## Data model

`Opportunity` is the base model shared by any fundable opportunity;
`Incentive` (implemented) and `Tender` (planned, Fase 5) are its subtypes, so
matching and alerting will work across both domains without mixing their
fields. `CompanyProfile` describes the company being matched. Full field
definitions: [`schemas/`](schemas/) (JSON Schema, auto-generated - run
`uv run python scripts/export_schemas.py` after editing models) and
[`src/agevolamatch/models/`](src/agevolamatch/models/).

## Adding a new source

Implement `agevolamatch.sources.base.BaseSource`: `fetch()` (network I/O),
`parse()` (raw payload → list of source-native dicts), `normalize()` (one dict
→ `Opportunity`/`Incentive`). `run()` (inherited) calls all three and is
tolerant of individual malformed records - a single broken record is logged
and skipped, not fatal. See
[`sources/incentivi_gov_it.py`](src/agevolamatch/sources/incentivi_gov_it.py)
for a complete example, including HTTP caching and rate limiting.

## Adjusting the matching score

Weights (see [`src/agevolamatch/matching/weights.py`](src/agevolamatch/matching/weights.py)
for defaults) live in `ScoringWeights`: `ateco_match`, `eligible_costs_match`,
`support_form_match`, `amount_fit`, `urgency`, `special_flags_match`. Pass a
YAML file overriding any subset of them:

```yaml
# weights.yaml
ateco_match: 40
amount_fit: 10
```

```bash
uv run agevolamatch match --profile examples/startup_profile.yaml --weights weights.yaml
```

No LLM is used anywhere in the matching pipeline; every score component comes
with a human-readable reason, surfaced under "reasons for/against/unverifiable"
in both the CLI output and CSV/JSON export.

## Development

```bash
uv run pytest -q          # tests never touch the network - see tests/fixtures/
uv run ruff check .       # lint
uv run ruff format .      # format
```

See [`CLAUDE.md`](CLAUDE.md) for architecture decisions and conventions,
[`docs/sources.md`](docs/sources.md) for the full incentivi.gov.it field
mapping and data-quality notes, and [`docs/inspiration.md`](docs/inspiration.md)
for prior art and license checks on related projects.

## Roadmap

See the Status section above and open issues for details on Fases 2-5.

## License

MIT - see [`LICENSE`](LICENSE). Data pulled from incentivi.gov.it is licensed
separately under IODL 2.0 by its publisher; see
[`docs/sources.md`](docs/sources.md).
