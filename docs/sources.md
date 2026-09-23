# Data sources

## Priority overview

| Source | Domain | Format | Update frequency | License | Status |
|---|---|---|---|---|---|
| incentivi.gov.it Open Data | Incentives | JSON via Solr endpoint (see below) | Site doesn't publish one; observed `ds_last_update` per record | IODL 2.0 | **Implemented** (Fase 1) |
| Invitalia | Incentives | HTML (no public API, no JSON:API) | Site doesn't publish one | Site terms apply (no explicit open-data license found) | **Implemented** (Fase 4) |
| ANAC Open Data | Tenders (gare) | CSV/ZIP (CKAN portal) | Monthly delta dumps | CC-BY-SA 4.0 | **Implemented** (Fase 5) |
| TED Europa | Tenders (gare) | Official REST API (JSON) | Real-time, queried on a rolling window | EU reuse policy (no auth required for published notices) | **Implemented** (Fase 5) |
| OpenCoesione | Historical/analytics | Official API | Periodic | Open data license (to verify) | Planned, Fase 3+ |
| OpenCUP | Historical/analytics | Web/exports | Periodic | To verify | Planned, Fase 3+ |

## incentivi.gov.it Open Data - implementation notes

The public page (https://www.incentivi.gov.it/it/open-data) states the license
is **IODL 2.0** and that data is offered "in formato CSV compresso (leggibile
da Excel) e in formato JSON", but the "Scarica JSON/CSV" buttons are not plain
links - they're client-side calls to an embedded Solr search backend. This was
reverse-engineered on 2026-09-23 by downloading the site's own
`main.min.js` bundle and reading the `queryFile`/`aliases_file` functions it
uses to build its own export feature - i.e. we call exactly the same endpoint
the site's own UI calls, just directly instead of through a browser click.

- **Endpoint:** `GET https://www.incentivi.gov.it/solr/coredrupal/select`
- **Required query params:** `q=index_id:incentivi`, `wt=json`, `q.op=OR`,
  `fl=<alias:internal_field,...>` (see mapping table below), `rows`, `start`
  for pagination.
- **Volume at inspection time:** 5,896 records total.
- No API key or authentication required. No documented rate limit; this
  project self-limits to 1 request/second and paginates in pages of 2,000.

### Field mapping (origin → our model)

Column names below are the aliases used both by the site's own "Scarica
JSON" feature and by `agevolamatch.sources.incentivi_gov_it.FIELD_ALIASES`.
Null rates were measured over the full 5,896-record dump on 2026-09-23.

| Site alias | Solr internal field | Null % | Maps to `Incentive` field | Notes |
|---|---|---|---|---|
| ID_Incentivo | zs_nid | 0.0% | `source_id` | Drupal node id, unique |
| Titolo | zs_title | 0.0% | `title` | |
| Descrizione | zs_body | 0.0% | `description` | Free text, sometimes structured with "Cos'è / A chi si rivolge / Cosa prevede" headers |
| Obiettivo_Finalita | zm_field_scopes_value | 0.0% | `scope` | Closed vocabulary, 13 values -> `IncentiveScope` |
| Data_apertura | zs_field_open_date | 0.3% | `open_date` | ISO, naive (no TZ in source; treated as UTC) |
| Data_chiusura | zs_field_close_date | 3.5% | `close_date` | Same format |
| Note_di_apertura_chiusura | zs_field_close_date_descriptor | 71.3% | `close_date_note` | Free text, sometimes clarifies real status ("Iscrizioni chiuse") beyond what dates say |
| Dimensioni | zm_field_dimensions_value | 0.0% | `company_sizes` | Closed vocabulary, 5 values -> `CompanySize` |
| Tipologia_Soggetto | zm_field_subject_type_value | 0.0% | `beneficiary_types` | Closed vocabulary, 16 values -> `BeneficiaryType`. See ambiguity note below |
| Forma_agevolazione | zm_field_support_form_value | 0.0% | `support_forms` | Closed vocabulary, 6 values -> `SupportForm` |
| Costi_Ammessi | zm_field_granted_costs_value | 0.0% | `eligible_costs` | Closed vocabulary, 7 values -> `EligibleCost` |
| Spesa_Ammessa_min/max | zs_field_cost_min/max | 15.3% | `cost_min`/`cost_max` | Clean plain numbers when present |
| Agevolazione_Concedibile_min/max | zs_field_support_grant_type_min/max | 15.3% | `grant_min`/`grant_max` | Clean plain numbers when present |
| Settore_Attivita | zm_field_activity_sector_value | 4.8% | `activity_sectors` | Closed vocabulary, 21 values -> `ActivitySector`. Informative only - not used for hard filters, `ateco_codes` is authoritative |
| Codici_ATECO | zs_field_ateco | 0.1% | `ateco_codes` / `ateco_all_sectors` / `ateco_raw` | **71% of non-null values are free-text "Tutti i settori economici ammissibili a ricevere aiuti" rather than codes.** Only ~29% carry real semicolon-separated ATECO codes (e.g. `"90.00; 90.01;"`). Parsed by `sources.parsing.parse_ateco` |
| Regioni | zm_field_regions_value | 0.1% | `regions` | 21 values: the 20 Italian regions + `"Estero"` (foreign/EU-wide measures) |
| Comuni | zs_field_comuni | 58.8% | `municipalities` | Free-text, semicolon-separated municipality **names**, no ISTAT codes. Cross-referencing with a company's province requires a comune→provincia lookup table (not in the source) |
| Ambito_territoriale | zm_field_special_territory_value | 87.9% | `special_territory` | Closed vocabulary, 6 values (ZES, Aree interne, Zone sismiche, Zone franche, Emergenza climatica, Non applicabile) |
| Soggetto_Concedente | zs_field_subject_grant | 0.02% | `granting_body` | Free text |
| Base_normativa_primaria | zs_field_primary_ruleset | 0.0% | `primary_legal_basis` | Free text |
| Base_normativa_secondaria | zs_field_secondary_ruleset | 92.7% | `secondary_legal_basis` | Free text |
| Provvedimento_attuativo | zs_field_implementation_ruleset | 0.3% | `implementation_ruling` | Free text |
| Gazzetta_ufficiale | zs_field_official_references | 87.0% | `official_gazette_ref` | Free text |
| Stanziamento_incentivo | zs_field_budget_allocation | 0.1% | `budget_allocation_raw` + `budget_allocation_amount` | **Messy format**: plain integers, Italian comma-decimals (`"15375383,50"`), and compound text (`"163000000 (con dm 29/7), 161800000 (con dm 09/08)"`). Best-effort parsed by `parse_italian_money`; the raw string is always kept, the parsed amount is informational and never used in hard filters |
| Link_istituzionale | zs_field_link | 0.0% | `url` | |
| Altre_caratteristiche | zs_field_other_characteristic | 88.1% | `other_characteristics` | Free text |
| Data_ultimo_aggiornamento | ds_last_update | 1.0% | `source_last_updated` | ISO with `Z` (UTC) - the origin's own last-modified timestamp |

There is **no status field** in the source. `status` (`open`/`upcoming`/
`closed`/`unknown`) is computed by `sources.parsing.compute_status` by
comparing `open_date`/`close_date` against the current date at ingest time.

### Known data-quality caveats

1. **ATECO is mostly prose, not codes** (see table above). Hard-filtering on
   ATECO must treat the "all sectors" pattern as "no exclusion", not as a
   missing/unverifiable field.
2. **"SU/PMI innovativa" is a single combined value** in `Tipologia_Soggetto`
   - the source cannot distinguish "startup innovativa" from "PMI innovativa".
   `Incentive.startup_or_pmi_innovativa_ambiguous` is set to `True` whenever
   this value is present; the matching logic (Fase 2) treats a company profile
   flagging *either* `is_startup_innovativa` or `is_pmi_innovativa` as
   satisfying this requirement, per the decision agreed in Fase 0.
3. **No ISTAT codes for municipalities or regions.** `municipalities` is a
   list of free-text names. A comune→provincia static lookup will be needed
   in Fase 2 to match a company's `province` against a municipality-level
   incentive.
4. **16 duplicate titles** across distinct `source_id`s were observed - these
   look like recurring yearly programs (same name, different edition), not
   ingestion bugs, and are not deduplicated.
5. Encoding is clean UTF-8 throughout; no mojibake observed in accented
   Italian text.

### Real-data validation

On 2026-09-23, running `agevolamatch ingest` against the live endpoint
normalized **5,896/5,896** records with zero failures, confirming the parsing
logic (built from a 37-record curated sample in
`tests/fixtures/incentivi_gov_it_sample.json`) generalizes to the full
dataset. Re-running ingest immediately after reports 0 new / 0 modified /
5,896 unchanged, confirming the content-hash-based change detection is stable.

## Invitalia - implementation notes

`www.invitalia.it` runs Drupal too, but exposes neither a Solr-backed export
(like incentivi.gov.it) nor a JSON:API (`/jsonapi/node/incentivi` 404s -
checked 2026-09-23). `robots.txt` doesn't disallow the content pages used
here. `agevolamatch.sources.invitalia.InvitaliaSource` scrapes the paginated
HTML listing at `/per-le-imprese/incentivi-e-strumenti?page=N` (only the "for
existing businesses" listing - the separate "for aspiring entrepreneurs"
listing at `/per-chi-vuole-fare-impresa/...` is not scraped, since
`CompanyProfile` models an existing company).

**What's extracted, from the listing page cards only:**

| Field | Source | Notes |
|---|---|---|
| `title` | Card `<h3><a class="card-unified__title">` | |
| `url` | Same `<a href>` | Made absolute |
| `source_id` | Last path segment of the URL (slug) | |
| `description` | Card `<p class="fw-normal">` | Short one-line subtitle |
| `status` | Card's `.category-top .category` label | `Attivo`→open, `Chiuso`→closed, `In apertura`→upcoming |

**Individual measure detail pages are not scraped for structured fields.**
Inspecting a real one (`/incentivi-e-strumenti/smartstart-italia`) showed it's
long-form free text organized as Drupal Paragraphs ("A CHI SI RIVOLGE", "COSA
FINANZIA", ...) with no structured dates/region/ATECO/size data comparable to
incentivi.gov.it - there's nothing reliable to extract there generically
across ~106 different measure pages. Every `Incentive` field this source
can't populate (regions, company_sizes, ateco_codes, cost/grant ranges, ...)
is left empty. This is not a special case for matching: the hard filters
already treat an empty field as "unverifiable, don't disqualify" (see
CLAUDE.md), so an Invitalia record without region data is neither wrongly
excluded nor wrongly matched - it just carries less scoring signal than a
fully-described incentivi.gov.it record.

**Status is set directly, not computed from dates** (unlike incentivi.gov.it):
Invitalia publishes a status label instead of open/close dates.
`matching/filters.py::_check_status` was updated to fall back to the stored
`status` field when an incentive has neither `open_date` nor `close_date`,
rather than always recomputing from dates and treating "no dates" as
automatically unverifiable - this was a real gap caught while designing this
source, not something the original Fase 1 code needed to handle.

### Deduplication against incentivi.gov.it

Most Invitalia measures are already on incentivi.gov.it, usually under a
longer or differently-worded title (e.g. Invitalia's "Smart&Start Italia" vs.
incentivi.gov.it's "Smart&Start Italia - Sostegno alle startup innovative").
There's no shared external ID, so `agevolamatch.sources.dedup.find_duplicate`
compares normalized titles (accent/case/punctuation-stripped) via substring
containment or word-set Jaccard similarity (default threshold 0.6), against
every *currently stored* incentivi.gov.it record. `agevolamatch ingest
--source invitalia` applies this before storing: a match is dropped and
counted, not persisted.

### Real-data validation

On 2026-09-23, `agevolamatch ingest --source invitalia` against the live site
scraped and normalized **106/106** listing cards with zero failures (9
paginated pages), of which **45 were identified as duplicates** of already-
ingested incentivi.gov.it records and dropped, leaving 61 new Invitalia-only
incentives stored. Spot-checked several kept titles for plausibility and
confirmed known-duplicate titles (e.g. "Smart&Start Italia", "Legge 181")
were correctly excluded. `agevolamatch match` against this mixed-source data
runs without errors, and Invitalia records do appear in wider result sets,
ranked appropriately lower than richer incentivi.gov.it records when a
profile's criteria depend on fields Invitalia doesn't provide.

## Fase 5: gare/tenders (domain B) - a separate domain, not incentives

Per the original spec, tenders (gare d'appalto) are a genuinely different
domain from incentives - no beneficiary type, no eligible costs, no support
form; eligibility instead turns on CPV codes (procurement classification) and
a submission deadline. `models.Tender` is a second `Opportunity` subtype
(alongside `Incentive`), and `agevolamatch.tenders` is a dedicated matching
module (hard filters + scoring) separate from `agevolamatch.matching`, per
the "módulo separado" requirement - see CLAUDE.md for why. Storage/CLI/API
plumbing (`Opportunity`, `BaseSource`, `upsert_opportunities`) is shared
infrastructure, reused as-is.

### ANAC (Autorità Nazionale Anticorruzione) - implementation notes

`dati.anticorruzione.it/opendata` is a CKAN portal, CC-BY-SA 4.0 licensed.
The "cig" dataset ("CIG aggiornamenti delta") publishes one CSV+JSON zip per
month via the standard CKAN `package_show` API - `agevolamatch.sources.anac`
discovers the latest one dynamically (by date-prefixed resource name) rather
than hardcoding a URL, so it keeps working next month without a code change.

**The portal's WAF blocks non-browser-looking requests outright**, confirmed
live by elimination: a conventional self-identifying bot UA
("Mozilla/5.0 (compatible; AgevolaMatch/0.1; +url)", the pattern well-behaved
bots like Googlebot use) was still rejected via httpx; only a UA with genuine
browser tokens (Chrome/AppleWebKit/Safari) got through, with no other header
changes needed. This is public, unrestricted-license open data - the WAF is
generic bot mitigation, not a deliberate access control this project's
single-request-per-run, rate-limited use is evading - but it does mean
`sources/anac.py::USER_AGENT` has to look like a browser to work reliably.

**The delta file is a monthly changelog, not a "currently open" snapshot.**
A real sample (2026-09 delta, 168,977 rows scanned) showed:
- 168,970/168,977 rows have `stato=ATTIVO` - this field tracks whether the
  CIG record itself is active/valid in ANAC's system, **not** whether the
  tender is still open for bids. It cannot be used to determine openness.
- 140,864/168,977 (83%) already have an `ESITO` (award outcome) - i.e. this
  delta is dominated by award-notice updates to old CIGs, not new open calls.
- Only 3,908/168,977 (2.3%) have `data_scadenza_offerta` (bid deadline) in
  the future.

Given that scale and noise ratio, `ANACSource.parse()` filters to
deadline-in-the-future rows **before** normalizing - unlike every other
source in this project, closed/awarded ANAC tenders are not kept for
history. This is a deliberate, documented departure from the project's
default "keep everything" policy, justified by scale (100k+ rows/month vs.
incentivi.gov.it's ~5,900 total) and by this specific feed's own noisy
change-log design (not a property of gare/tenders data in general - TED,
below, does keep closed records).

**Field mapping** (only the columns this source uses; the real CSV has ~55
columns total, most institutional/procedural detail not modeled here):

| CSV column | Maps to `Tender` field | Notes |
|---|---|---|
| `cig` | `source_id`, `cig` | Unique per lot/contract, not per overall gara - confirmed: two different CIGs can share the same `numero_gara` (multi-lot tenders) |
| `oggetto_gara` | `title` | |
| `oggetto_lotto` | `description` | Lot-level description |
| `importo_lotto` (fallback `importo_complessivo_gara`) | `estimated_value` | Clean plain-decimal numbers (unlike incentivi.gov.it's messy money fields) |
| `oggetto_principale_contratto` | `contract_type` | `LAVORI`/`SERVIZI`/`FORNITURE` (works/services/supplies) |
| `denominazione_amministrazione_appaltante` | `buyer_name` | |
| `provincia` | `province` | Italian province name, e.g. `ROMA` - no ISTAT code, same "no comune/provincia→regione mapping yet" limitation as incentivi.gov.it's `municipalities` |
| `data_pubblicazione` / `data_scadenza_offerta` | `open_date` / `close_date` | Plain `YYYY-MM-DD`, no timezone ambiguity |
| `tipo_scelta_contraente` | `procedure_type` | e.g. "PROCEDURA APERTA", "AFFIDAMENTO DIRETTO" |
| `cod_cpv` | `cpv_codes` | Single code per row (unlike TED's list); wrapped in a 1-item list |
| `ESITO` | `outcome` | Informational only, present on most rows even within the open-filtered subset when the tender has multiple lots at different stages |

No per-record web URL exists in this dataset - `Tender.url` is left `None`
for ANAC records (a user can look up a CIG manually on the portal).

**Known data-quality notes:**
- ~7/168,977 rows (checked in the full delta) show column-shifted values
  (e.g. a `settore` value appearing in the `stato` column) - a small number
  of source rows have fewer fields than the header, likely from an unescaped
  delimiter upstream. `csv.DictReader` doesn't raise on this, so such a row
  parses "successfully" with wrong data in the wrong field; at this
  incidence rate (0.004%), this is accepted as inherent source noise rather
  than engineered around.
- CSV blank fields arrive as empty strings, not `None` - confirmed live to
  matter: an early version of `normalize()` stored `province=""` instead of
  `None` for a blank field. Every optional string field is now run through
  `_blank_to_none()`, not a bare `record.get(...)`.
- Within the *currently-open* subset specifically (post-filter), `provincia`
  and `importo_lotto` were 100% populated (0/3,908 missing) in the observed
  snapshot - the general schema allows nulls there (seen in the full delta
  including closed rows), it just doesn't occur in what actually reaches
  this source's output today.
- The same CIG can appear more than once within a single monthly delta (a
  tender updated twice in the same month produces two delta rows) -
  `upsert_opportunities`'s existing dedup-by-`(source, source_id)` logic
  handles this correctly even within a single ingest batch (confirmed live:
  a fresh-database ingest reported some rows as "modified"/"unchanged"
  against records inserted earlier in the very same run, not just against
  previous runs).

### TED (Tenders Electronic Daily) - implementation notes

The EU's official procurement portal, with a genuinely public REST API:
`POST https://api.ted.europa.eu/v3/notices/search`, confirmed live to
require no authentication for published notices. Field names, response
shape, and quirks below were all confirmed against the live API - TED
publishes a Swagger reference but not a plain field-by-field guide, and the
exact response shape isn't documented at the level needed to write a parser
without checking directly.

**Query scope**: `buyer-country=ITA AND notice-type=cn-standard AND
publication-date>=<rolling 60-day window>`. `cn-standard` (standard contract
notice) specifically excludes prior-information notices (`pin-only`, which
carry no submission deadline) and award notices - i.e. it's scoped to actual
open calls, not every notice type TED carries. `buyer-country=ITA` keeps
this source's scope aligned with the rest of the project (EU tenders are
technically open to bidders from any member state, but an Italian buyer
keeps this squarely "Italian public procurement", same framing as ANAC).
The 60-day rolling window avoids re-fetching the full archive (128,705 total
`cn-standard` notices for Italy alone, confirmed live) on every run.

**Real quirks confirmed live, not assumed:**
- **Dates are `'YYYY-MM-DD+HH:MM'`** - a date with a UTC offset but no time
  component. `datetime.fromisoformat()` silently misparses this (it reads
  the offset's digits as a time-of-day and drops the timezone), which would
  have produced wrong-but-plausible-looking timestamps if shipped -
  `sources/parsing.py::parse_ted_date` handles this format explicitly.
- **`notice-title` and `buyer-name` are multi-language dicts**, keyed by
  whichever 3-letter language codes that specific notice was published in
  (not a fixed set) - `sources/ted.py::_pick_language_value` prefers Italian,
  falls back to English, then to whatever's available.
- **The public API does enforce a rate limit** and returns HTTP 429 -
  confirmed by hitting it during manual testing. `TEDSource` rate-limits
  itself (1 req/s default) and retries a 429 using the server's own
  `Retry-After` header when present, falling back to exponential backoff.
- Pagination is plain `page`/`limit` query fields in the JSON body (verified
  empirically - `page=2` returns different results than `page=1`); the
  `iterationNextToken` field the API also returns was null in every
  response observed and isn't used here.

**Field mapping:**

| API field | Maps to `Tender` field | Notes |
|---|---|---|
| `publication-number` | `source_id` | e.g. `"599734-2026"` |
| `notice-title` (multi-lang) | `title` | |
| `buyer-name` (multi-lang) | `buyer_name` | |
| `buyer-country` | `buyer_country` | ISO 3166-1 alpha-3, e.g. `"ITA"` |
| `publication-date` | `open_date` | |
| `deadline-receipt-tender-date-lot` (list, one per lot) | `close_date` | Earliest deadline across lots |
| `classification-cpv` | `cpv_codes` | List, deduplicated (raw values sometimes repeat the same code) |
| `estimated-value-lot` / `estimated-value-cur-lot` | `estimated_value` / `estimated_value_currency` | Populated in 148/150 notices in a live sample |
| `notice-type` | `notice_type` | Always `"cn-standard"` given the query scope |
| `links.htmlDirect.ITA` (fallback `.ENG`) | `url` | |

`status` is computed from `open_date`/`close_date` the same way as
incentivi.gov.it (not stored directly) - confirmed on a live 60-day sample:
19 open / 131 closed out of 150 notices, a realistic mix since this source,
unlike ANAC, does keep closed records (TED's volume for a single-country
60-day window is manageable; ANAC's monthly delta is not - see above).

### Real-data validation (both sources)

On 2026-09-23: `agevolamatch gare ingest --source anac` downloaded the live
32MB monthly delta, filtered 168,977 rows to 3,908 candidates, and
normalized **3,908/3,908 with zero failures**. `agevolamatch gare ingest
--source ted` paginated the live API for a 60-day Italy window and
normalized **2,566/2,566 with zero failures**. `agevolamatch gare match
--profile examples/startup_profile.yaml` against the resulting 6,388-tender
mixed-source database produced a coherent ranking blending both sources
(e.g. an ANAC IT-services tender and a TED cloud-migration tender both
scoring ~79/100 for a software startup profile, with sensible CPV-prefix and
amount-fit reasoning in each explanation).
