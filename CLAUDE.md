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

uv run agevolamatch ingest                          # incentivi.gov.it (default)
uv run agevolamatch ingest --source invitalia       # scrape + dedup against stored incentivi.gov.it records
uv run agevolamatch ingest --source all
uv run agevolamatch list --status open --region Lazio
uv run agevolamatch match --profile examples/startup_profile.yaml --top 10
uv run agevolamatch export --format csv --output out.csv --profile examples/startup_profile.yaml
uv run agevolamatch alerts run --subscriptions examples/alert_subscriptions.yaml --dry-run
uv run agevolamatch serve                # REST API on :8000

docker compose up --build                # api + ingest/alerts loop services
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
- **Matching only scores incentives that already passed hard filters**
  (`matching/engine.py::match_incentive`). A low score always means "eligible
  but not a great fit", never "might be ineligible" - those are two different
  things and mixing them into one number would make the ranking misleading.
  `match_profile(..., include_ineligible=True)` exists for debugging/transparency
  but is off by default.
- **Hard filter checks default to UNVERIFIABLE, never to a silent pass or a
  disqualifying fail, whenever the data needed to verify them doesn't exist**
  - either because the source field is empty (rare - see docs/sources.md null
    rates) or because AgevolaMatch doesn't model the company-side data needed
    to check it at all (company age - the source has no such field at all;
    municipality-level eligibility - no comune→provincia mapping yet; special
    territorial status like ZES/Aree interne - not modeled in CompanyProfile).
    This is a deliberate product decision from Fase 0, not a gap to silently
    paper over.
- **`CompanyProfile` has no explicit "beneficiary type" field** matching the
  source's `Tipologia_Soggetto` vocabulary directly (Impresa, Cooperativa,
  Professionista, ...). `matching/filters.py::_expected_beneficiary_types`
  derives the set of source values a profile could satisfy from `legal_form`
  and the startup/PMI/femminile/under-35 flags, defaulting every profile to
  "Impresa" (the value ~89% of incentives use). Revisit if a profile type
  that isn't a plain company (e.g. Professionista, Ente Pubblico) is needed.
- **Score components a profile leaves unconfigured get neutral half-credit**,
  not 0 or full weight (`matching/scoring.py`, `_NEUTRAL_FRACTION`) - an
  incomplete profile shouldn't be punished or flattered on axes it didn't
  provide data for. This is different from the hard-filter UNVERIFIABLE
  status (which never affects eligibility) - here it's a genuine scoring
  choice that does affect the ranking.
- **The API is a thin HTTP wrapper over the same storage/matching code the
  CLI uses** (`api/app.py` calls `storage.load_incentives` and
  `matching.match_profile` directly) - there is no second implementation to
  keep in sync. `AGEVOLAMATCH_DB_PATH` env var (also read from `.env` via
  `python-dotenv`, loaded once in `agevolamatch/__init__.py`) selects the
  database file; the engine is cached per path with `lru_cache` so repeated
  requests don't reopen the SQLite file each time.
- **Alert dedup reuses `content_hash`, the same mechanism ingestion uses for
  change detection** (`storage/tables.py::SentAlert`, unique on
  `(subscription_name, source, source_id, content_hash)`). This is what makes
  "don't resend an alert already sent" and "do alert on a genuinely modified
  incentive" both fall out of one rule, with no separate "is this new since
  last run" bookkeeping needed - `alerts run` can be invoked at any cadence,
  independent of when `ingest` last ran.
- **Alert channels read their own config from the environment lazily, inside
  `send()`, not at construction** (`alerts/email_channel.py`,
  `alerts/telegram_channel.py`) - so `default_channels()` always succeeds
  even if only one channel is actually configured, and `--dry-run` (the
  default for `alerts run`) never touches channel config at all since it
  never calls `send()`.
- **Docker**: a single image (`Dockerfile`) serves both the `api` and
  `ingest` compose services, differentiated only by command/entrypoint. `uv
  sync` runs at build time; `ENV UV_NO_SYNC=1` stops `uv run` from re-syncing
  (and pulling the dev dependency group) on every container start - this was
  a real bug caught by actually running the built image, not just building it.
- **Telegram messages are sent as plain text, no `parse_mode`**
  (`alerts/telegram_channel.py`). This was `parse_mode=Markdown` originally;
  confirmed against the real Telegram API with a live bot that it 400s
  ("can't find end of the entity") on real incentive titles/URLs containing
  unmatched `*`/`_`/`[` characters, which we don't control and can't
  reliably escape for legacy Markdown. Mocked tests alone never caught this
  since a mock returns whatever status you tell it to. Don't reintroduce a
  parse_mode without also escaping the incentive title/URL/description for
  that mode's specific special-character rules.

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
- `tests/unit/test_matching_engine.py::test_startup_profile_fixture_produces_a_coherent_ranking`
  runs `examples/startup_profile.yaml` (the real example profile, not a test
  double) against the real curated fixture - this is the same path
  `agevolamatch match --profile examples/startup_profile.yaml` exercises, so
  it should keep passing whenever that command does.
- Ruff must be clean (`uv run ruff check .`) before considering a phase done.

- **HTTP fetching is shared, not duplicated, across sources**:
  `sources/http_client.py::RateLimitedHttpClient` (cache + 1 req/s rate limit
  + User-Agent) is composed by both `IncentiviGovItSource` and
  `InvitaliaSource`. Add any third HTTP-based source the same way rather than
  re-implementing rate limiting/caching per source.
- **Invitalia is scraped at listing-card granularity only** - no per-measure
  detail-page parsing. Detail pages are free-form Drupal Paragraphs content
  with nothing structured to reliably extract across ~100 different measures
  (confirmed by inspecting a real one). Fields the listing can't provide
  (region, size, ATECO, cost/grant ranges, ...) are left empty rather than
  guessed - the matching engine's existing UNVERIFIABLE handling absorbs this
  correctly, so this isn't a special case anywhere else in the codebase.
- **`sources/dedup.py::find_duplicate` is the only thing standing between
  Invitalia ingestion and duplicate rows**: it's applied by the `ingest`
  CLI command (not inside `InvitaliaSource` itself, which stays a plain,
  source-agnostic `BaseSource`) by comparing against currently-stored
  incentivi.gov.it records before upserting. A dropped duplicate is counted
  and logged, never silently discarded.

- **The optional LLM feature is informational-only and fails safe.**
  `matching/llm/` is a pluggable `LLMProvider` interface (`OllamaProvider`,
  `OpenAICompatibleProvider`), disabled unless `AGEVOLAMATCH_LLM_PROVIDER` is
  set, and only invoked at all when `match --llm` is explicitly passed.
  `enrich_with_llm_requirements()` only ever *appends* to
  `MatchExplanation.unverifiable` (prefixed `[LLM]`) on already-eligible,
  already-scored results - it never touches eligibility or the score. Any
  provider failure (bad config, network error, timeout) is caught and logged
  per-result, never raised - confirmed live: a real local Ollama run where
  every call timed out (see below) still completed the match command
  normally with exit code 0, just without LLM enrichment.
- **Provider config fields use `field(default_factory=...)`, not a plain
  `= os.environ.get(...)` default** (`ollama_provider.py`,
  `openai_compatible_provider.py`). A plain default is evaluated once at
  module-import time and then frozen for the process; `default_factory` is
  evaluated per instantiation. This is the same principle as the alert
  channels reading config lazily inside `send()` - don't regress it back to
  a plain default when touching these files.
- **`OllamaProvider`'s default timeout is 120s, not something shorter.**
  Confirmed live on this machine: a 3B model on CPU-only hardware took over
  60s per call (cold load + generation), consistently timing out at a 60s
  default. `OLLAMA_TIMEOUT_SECONDS` is configurable via env for slower/faster
  hardware.

## Non-goals / explicit decisions from Fase 0

- ATECO 2007↔2025 official correspondence table: still not integrated. Until
  it is, `matching/ateco.py` compares codes from either version as plain
  digit strings (exact/prefix), which under-matches across a renumbered
  2007/2025 boundary but never over-matches into a wrong sector.
- Comune→provincia lookup: still not integrated - `matching/filters.py`
  marks any incentive restricted to specific `municipalities` as
  UNVERIFIABLE rather than guessing. Needed to actually check a company's
  province against a municipality-restricted incentive.
- Invitalia dedup (Fase 4) will match on (normalized title, granting body,
  dates) since there's no shared external ID with incentivi.gov.it.
