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
uv sync --all-extras             # also installs the dashboard extra (streamlit/pandas) - do this to run the full test suite, same as CI
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
uv run agevolamatch-mcp                  # MCP server (stdio) - console script, not a Typer subcommand
uv run streamlit run src/agevolamatch/dashboard/app.py   # needs --extra dashboard installed

uv run agevolamatch gare ingest --source anac|ted|all    # tenders/gare - separate domain, see below
uv run agevolamatch gare match --profile examples/startup_profile.yaml --top 10
uv run agevolamatch gare alerts run --subscriptions examples/alert_subscriptions.yaml --dry-run

docker compose up --build                # api + dashboard + ingest/alerts loop services
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
  `LegalForm.ASSOCIAZIONE` (APS/ODV/ONLUS/Terzo Settore) maps to the same
  `BeneficiaryType.COOPERATIVA_NONPROFIT` bucket as `cooperativa` - the source
  vocabulary doesn't distinguish them (verified against the live dataset).
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
- `tests/fixtures/anac_cig_sample.csv` and `ted_notices_sample.json` are
  curated real data (not synthetic) the same way the incentive fixtures are,
  picked to cover: LAVORI/SERVIZI/FORNITURE, CPV starting with 72 (IT - so
  the startup example profile actually matches something), with/without
  ESITO, open/closed status. When curating a fixture like this, verify each
  predicate actually found a real row (`add()` returning the count you
  asked for) rather than assuming - two tests were written against cases
  that turned out not to exist in the *currently-open* ANAC subset (0/3,908
  real records were missing province or importo_lotto) and had to be fixed
  to construct that case directly instead, once discovered.
- `tests/unit/test_tenders_engine.py::test_real_fixture_data_from_both_sources_produces_a_coherent_ranking`
  is the tenders equivalent of the incentive test above - same principle.
- `tests/unit/test_dashboard.py` has two AppTest env fixtures:
  `dashboard_env` (incentives only) and `dashboard_env_with_gare`
  (incentives + real ANAC tender fixture rows). Use the latter for anything
  touching the Gare tab or the Matching tab's Gare sub-tab - the former will
  make the Gare tab correctly show its "no gare" info message, not test
  the actual tender-list/tender-matching code paths.
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

- **The MCP server (`mcp/server.py`) is a third thin wrapper over
  storage/matching**, alongside the CLI and REST API - `search_incentives`,
  `get_incentive`, `match_company_profile` call the exact same
  `load_incentives`/`match_profile` functions. Uses `mcp.server.mcpserver.
  MCPServer`, not `FastMCP` - the installed SDK (mcp>=2.0) renamed `FastMCP`
  to `MCPServer` between 1.x and 2.x; this was confirmed against the actually
  installed version (`uv add mcp` resolved 2.2.0), not assumed from training
  data, after `from mcp.server.fastmcp import FastMCP` raised a
  `ModuleNotFoundError` with the SDK's own migration-guide pointer. Re-check
  the installed API before assuming an import path if this dependency is
  ever upgraded across a major version again.
- **A malformed `match_company_profile` argument must raise `ToolError`,
  not let pydantic's `ValidationError` propagate raw** - confirmed live
  (not just from documentation) that this SDK treats an unhandled exception
  from inside a tool body as an "unexpected crash" (`UnexpectedToolError`),
  while a deliberately-raised `ToolError`/`ResourceError` is what the
  stdio/JSON-RPC transport layer translates into a graceful
  `CallToolResult(isError=True)` for the actual MCP client. Note that
  `MCPServer.call_tool()` itself - the API these tests call directly -
  *raises* in both cases; only the full transport layer does the
  isError-result translation, so don't expect `result.is_error` when testing
  via `call_tool()` directly, only via a real client/transport round-trip.

- **The Streamlit dashboard (`dashboard/app.py`) is a fourth thin wrapper**
  over storage/matching, alongside the CLI, REST API, and MCP server -
  same `load_incentives`/`match_profile` calls, no separate logic. It's
  behind the optional `dashboard` extra (`uv sync --extra dashboard`) since
  streamlit/pandas are sizeable and most CLI/API/MCP usage doesn't need them;
  CI installs `--all-extras` so it's still tested on every push.
- **`@st.cache_resource`/`@st.cache_data` are global to the process, not
  scoped per test/session** - confirmed by a real test failure: a test using
  a fresh empty `AGEVOLAMATCH_DB_PATH` still saw a previous test's cached
  non-empty incentive list, because nothing had cleared the cache between
  them. `tests/unit/test_dashboard.py` has an autouse fixture that calls
  `st.cache_resource.clear()` / `st.cache_data.clear()` before and after
  every test - keep it if you add more dashboard tests. This is a testing
  concern; in a real deployment the dashboard runs against one fixed
  `AGEVOLAMATCH_DB_PATH` per process, so the caching itself is fine there.
- Dashboard tests use `streamlit.testing.v1.AppTest` to actually execute the
  app's Python and assert on the resulting element tree - not a mock, not an
  import-only smoke test. `tests/unit/test_dashboard.py` guards its streamlit
  import with `pytest.importorskip` so a plain `uv sync` (no `--extra
  dashboard`) still runs the rest of the suite cleanly.

- **Gare/tenders (Fase 5) is a deliberately separate matching module**
  (`agevolamatch/tenders/`), not folded into `agevolamatch/matching/`. The
  spec calls this out explicitly ("módulo separado") because the domains
  genuinely don't share business rules: tenders have no beneficiary type, no
  eligible costs, no support form - eligibility turns on CPV codes (the
  procurement-domain analog of ATECO) and a submission deadline, nothing
  else. `TenderMatchResult`/`TenderHardFilterResult`/etc. in
  `tenders/models.py` are separate types from `matching/models.py`'s
  Incentive-typed equivalents, on purpose - forcing Tender through
  `MatchResult` (typed to `incentive: Incentive`) would mean either bloating
  that type with tender-only fields or misusing incentive-shaped fields for
  a different domain. What *is* shared: `Opportunity`, `BaseSource`,
  `storage.upsert_opportunities` - genuinely domain-agnostic infrastructure,
  not business logic.
- **`storage.load_incentives`/`load_tenders` filter by source** - both
  domains' records live in the same `opportunities` table (they're both
  `Opportunity` subtypes), so `load_incentives` must exclude ANAC/TED rows
  and `load_tenders` must exclude incentivi.gov.it/Invitalia rows. This was
  a real bug caught by actually mixing both domains in one database, not by
  reasoning about the schema: `Incentive.model_validate()` has
  `extra="forbid"`, so validating a Tender's payload (which has fields like
  `buyer_name`/`cpv_codes` that `Incentive` doesn't declare) as an Incentive
  raises. If you add a third Opportunity subtype, extend the source
  allow-lists in `storage/repository.py`, don't assume the existing filters
  generalize automatically.
- **CPV matching (`tenders/cpv.py::match_cpv`) mirrors ATECO matching's
  exact/prefix/no-match/unverifiable shape** on purpose - same underlying
  problem (a hierarchical hardcoded classification, need prefix fallback
  when there's no exact match). The prefix search tries decreasing lengths
  (6 down to 2), not one fixed length - a fixed-length-6 check would miss a
  real match at a shorter shared prefix (e.g. "72201000" vs "72470000" only
  agree on the first 2 digits). This is the exact bug class already fixed
  once in `matching/ateco.py` (see git history) - it very nearly got
  reintroduced here by copying the pattern without copying the fix; caught
  by mirroring the same test structure, not by inspection.
- **ANAC's WAF requires a genuine browser User-Agent, not just a
  "Mozilla/5.0"-prefixed self-identifying one** - confirmed live, by
  elimination (see docs/sources.md). Don't "clean up" `sources/anac.py`'s
  `USER_AGENT` to the project's usual self-identifying bot UA style without
  re-testing against the live portal first.
- **ANAC's monthly delta is filtered to open-only at `parse()` time** - the
  only source in this project that doesn't keep closed/awarded records for
  history. This is a scale-driven, source-specific exception (100k+ rows/
  month of which ~97% is award-notice noise, not new tenders), not a
  reversal of the project's general "keep everything" policy - TED (also
  Fase 5) does keep closed records, since its per-country volume is
  manageable. See docs/sources.md for the numbers behind this call.
- **CSV blank fields are empty strings, not None** - `sources/anac.py`'s
  `_blank_to_none()` exists because a real (constructed-but-realistic) test
  case caught `record.get("provincia")` storing `province=""` instead of
  `None` for a blank CSV field. Every optional string field read from a CSV
  source must go through this or an equivalent, not a bare `.get(...)`
  - `record.get(...) or None` inline is an acceptable equivalent (see
  `oggetto_lotto` → `description`) but a bare `.get(...)` is not.
- **TED enforces a rate limit on its public API** - confirmed live (a real
  429 during manual testing, not documented in advance). `TEDSource`
  rate-limits itself and retries a 429 with the server's `Retry-After` when
  given, backing off exponentially otherwise. If you see 429s again, check
  `min_request_interval_seconds` / `max_retries_on_rate_limit` before adding
  another workaround.
- **`ingest` and `gare ingest` both tolerate one source failing outright**
  (not just one bad record within a source, which `BaseSource.run()` already
  handled) - a `try/except` around each source's `.run()` in the CLI logs
  and continues to the next source. Added after real experience: TED's rate
  limit produced an unhandled `HTTPStatusError` that would otherwise have
  aborted an `ingest --source all` run before it got to ANAC.
- **Gare/tenders is wired into the dashboard and alerts, reusing the exact
  same generic types** where they were already domain-agnostic, and adding
  a parallel path only where a type was genuinely Incentive-typed:
  - `alerts/service.py::run_tender_alerts` is a near-duplicate of
    `run_alerts` (different matching call and message formatter), not a
    generalization of it - `AlertEvent`/`AlertRunSummary`/`SentAlert`/
    `already_sent`/`record_sent` needed no changes at all, since none of
    them reference `Incentive` directly (confirmed before writing the
    duplicate, not assumed). `AlertSubscription` (profile/min_score/
    channels/weights) is shared as-is between `alerts run` and `gare alerts
    run` - one subscriptions file drives both domains for the same profile.
  - `dashboard/app.py` gained a fourth tab (📄 Gare) and a "Gare" sub-tab
    inside Matching, both thin wrappers calling `load_tenders`/
    `match_tender_profile` the same way the incentive tabs call
    `load_incentives`/`match_profile`. The profile editor form gained a
    `cpv_codes` text input alongside `ateco_codes`; the "at least one
    classification" validation now accepts either, not just ATECO, since a
    profile might only care about gare.
  - `TenderScoringWeights` was missing a `from_yaml()` classmethod that
    `ScoringWeights` already had - added for parity, needed for
    `run_tender_alerts`'s `subscription.weights` support. If you add a
    third weights class anywhere, check for this same gap before assuming
    parity with the incentive path.
  - REST API: `GET /tenders`, `GET /tenders/{source_id}`,
    `POST /tenders/match` - same thin-wrapper pattern as `/incentives`/
    `/match`, using `load_tenders`/`match_tender_profile`.
  - MCP server: `search_tenders`, `get_tender`, `match_tenders` - same
    pattern as the incentive tools.
  - Fixed a real bug while adding the single-record lookups: `get_incentive`
    (both the API and the MCP tool) looked up by `source_id` alone, with no
    source filter - since `source_id` is only unique per `(source,
    source_id)`, not globally, an ANAC CIG or TED publication-number that
    happened to collide with an incentive's id could have been returned
    there and then failed `Incentive.model_validate()` the same way the
    already-fixed `load_incentives` bug did. Added
    `storage.get_incentive_record`/`get_tender_record` (both source-scoped)
    and switched every single-record lookup (API `get_incentive`/
    `get_tender`, MCP `get_incentive`/`get_tender`) to use them instead of
    querying `OpportunityRecord` directly. If you add a fourth surface with
    its own single-record lookup, use these helpers, don't re-query
    `OpportunityRecord.source_id` unscoped.

## Non-goals / explicit decisions from Fase 0

- ATECO 2007↔2025 official correspondence table: still not integrated. Until
  it is, `matching/ateco.py` compares codes from either version as plain
  digit strings (exact/prefix), which under-matches across a renumbered
  2007/2025 boundary but never over-matches into a wrong sector.
- Comune/provincia→regione lookup: still not integrated - `matching/filters.py`
  marks any incentive restricted to specific `municipalities` as
  UNVERIFIABLE rather than guessing, and `tenders/filters.py` does the same
  for a tender restricted to a `province` (ANAC). Same TODO, two call sites.
- ATECO↔CPV crosswalk: doesn't exist officially, so `CompanyProfile.cpv_codes`
  (tenders) is set independently from `ateco_codes` (incentives), never
  derived from it. A profile that only fills in `ateco_codes` will get
  UNVERIFIABLE on every tender's CPV check, not a guessed match.
- Invitalia dedup (Fase 4) will match on (normalized title, granting body,
  dates) since there's no shared external ID with incentivi.gov.it.
