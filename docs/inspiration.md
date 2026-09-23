# Inspiration and prior art

This project was scoped after reviewing four existing repos/projects working
in adjacent spaces. Licenses were checked via the GitHub API (`license` field)
before writing any code, per the project's rule of never reusing code without
a compatible license.

## License findings

| Project | License found | Reuse allowed |
|---|---|---|
| [Alessandro624/BandAI](https://github.com/Alessandro624/BandAI) | None declared (GitHub API returns `license: null` → all rights reserved by default) | Design ideas only, no code |
| [roberto-nai/ANAC-OD-DOWNLOADER](https://github.com/roberto-nai/ANAC-OD-DOWNLOADER) | None declared | Design ideas only, no code |
| [roberto-nai/ANAC-OD-ANALYSER](https://github.com/roberto-nai/ANAC-OD-ANALYSER) | None declared | Design ideas only, no code |
| [BandiRadar (mayai-it, MCP server)](https://glama.ai/mcp/servers/mayai-it/bandiradar) | MIT © MayAI | Architecture pattern only (see below) - this is the project AgevolaMatch was explicitly asked *not* to be named after or clone, so no code was inspected or copied, MIT or not |

No code from any of the four projects appears in this repository. Nothing here
requires a `NOTICE` file, since nothing was copied.

## What was actually taken from each

**BandAI** - the idea of a strict multi-stage pipeline (their Scout → Compliance
→ Proposal) reinforced the decision to keep `sources/` (ingest), `matching/`
(filter + score), and `alerts/` as clearly separated stages with typed
boundaries between them, rather than one monolithic ingestion+matching script.

**ANAC-OD-DOWNLOADER / ANAC-OD-ANALYSER** - both are relevant to the Fase 5
"gare d'appalto" module (ANAC Open Data), not to the Fase 1-3 incentive MVP.
Their pattern of separating "download raw data" from "build a queryable
database from it" as two distinct steps matches this project's `fetch()` /
`normalize()` / storage split. When Fase 5 is implemented, ANAC's CIG-based
CSV format (documented in their READMEs) will be revisited.

**BandiRadar (MCP)** - the closest project in scope and the reason this
project needed a different name. Its documented pipeline - ingest → normalize
to a canonical model → store in SQLite → two-stage matching (deterministic
prefilter, then optional LLM scoring) → delivery via CLI/MCP - is essentially
the architecture this project's own spec (Opportunity/Incentive model, hard
filters + configurable score + optional LLM re-ranking) already called for
independently. Recognizing this confirms the design pattern is sound; it does
not mean any of BandiRadar's code or schema fields were consulted or copied.
One concrete difference worth naming: BandiRadar's data model is documented as
covering both incentives and tenders/gare from the start across 19 sources;
AgevolaMatch scopes Fase 1-3 to incentivi.gov.it only and defers tenders to
Fase 5, on the reasoning that a smaller, deeply-inspected single source
produces a more reliable MVP than broad coverage with unverified per-source
quality.
