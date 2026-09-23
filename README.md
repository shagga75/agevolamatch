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

Fase 1-2 (core ingestion + matching) are implemented and validated against
the live dataset. The REST API, alerts, and the dashboard are on the roadmap
- see [Roadmap](#roadmap) below.

- ✅ **Fase 1 - Core**: repo structure, Pydantic models + JSON Schema,
  incentivi.gov.it source, SQLite storage with new/modified detection.
- ✅ **Fase 2 - Matching + CLI**: hard eligibility filters, configurable
  weighted score, explanations (reasons for/against/unverifiable), CSV/JSON
  export, example profile.
- ⏳ Fase 3 - REST API + alerts (email/Telegram) + Docker
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
