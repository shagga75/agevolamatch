# Data sources

## Priority overview

| Source | Domain | Format | Update frequency | License | Status |
|---|---|---|---|---|---|
| incentivi.gov.it Open Data | Incentives | JSON via Solr endpoint (see below) | Site doesn't publish one; observed `ds_last_update` per record | IODL 2.0 | **Implemented** (Fase 1) |
| Invitalia | Incentives | HTML (no public API) | N/A | Site terms apply | Planned, Fase 4. Many measures duplicate incentivi.gov.it - dedupe by (normalized title, granting body, dates), no shared external ID exists |
| ANAC Open Data | Tenders (gare) | CSV/ZIP | Historical dumps, updated periodically | To verify at implementation time (ANAC publishes under an open license, exact terms TBD) | Planned, Fase 5 |
| TED Europa | Tenders (gare) | Official API | Real-time | EU reuse policy (generally open) | Planned, Fase 5 |
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
