# AgevolaMatch

Motore open-source di matching tra incentivi pubblici italiani (finanza
agevolata) e profili aziendali - pensato per startup e PMI che vogliono capire
a quali incentivi possono davvero accedere.

*[Read this README in English](README.md)*

> **Disclaimer**: questo strumento ha finalità puramente informativa. I
> requisiti di ammissibilità vanno sempre verificati sulla fonte ufficiale
> (campo `url` di ogni incentivo) prima di presentare domanda. AgevolaMatch
> non presenta domande per conto dell'utente e non è affiliato a nessun ente
> pubblico italiano.

## Stato del progetto

La Fase 1 (ingestione core) è implementata e validata contro il dataset live.
Matching, API REST, alert e dashboard sono nella roadmap - vedi
[Roadmap](#roadmap).

- ✅ **Fase 1 - Core**: struttura del repo, modelli Pydantic + JSON Schema,
  fonte incentivi.gov.it, storage SQLite con rilevamento nuovi/modificati.
- ⏳ Fase 2 - Matching + export CLI
- ⏳ Fase 3 - API REST + alert (email/Telegram) + Docker
- ⏳ Fase 4 - Dashboard, scraper Invitalia, LLM opzionale, server MCP
- ⏳ Fase 5 - Gare d'appalto: ANAC + TED, modulo separato

## Perché

incentivi.gov.it elenca migliaia di incentivi con metadati incoerenti e
difficili da filtrare (vedi [`docs/sources.md`](docs/sources.md) per il
dettaglio: il 71% dei campi ATECO è testo libero, non codici; non esiste un
campo di stato; i formati degli importi sono incoerenti). AgevolaMatch ingerisce
questi dati, li normalizza in un modello tipizzato e li confronterà con un
profilo aziendale con uno scoring trasparente e spiegabile - senza bisogno di
un LLM per la pipeline principale.

## Installazione

Richiede Python 3.12+ e [uv](https://docs.astral.sh/uv/).

```bash
git clone <questo-repo>
cd agevolamatch
uv sync
```

## Utilizzo

```bash
# Scarica gli incentivi da incentivi.gov.it e salva i record nuovi/modificati
uv run agevolamatch ingest

# Elenca gli incentivi salvati, con filtri
uv run agevolamatch list --status open --region Lazio --limit 20
```

`ingest` può essere rieseguito in sicurezza: segnala un record come nuovo o
modificato solo se il suo contenuto è effettivamente cambiato (vedi
[`CLAUDE.md`](CLAUDE.md) per i dettagli), e non cancella mai gli incentivi
chiusi - restano consultabili come storico.

## Modello dati

`Opportunity` è il modello base condiviso da ogni opportunità finanziabile;
`Incentive` (implementato) e `Tender` (pianificato, Fase 5) sono i suoi
sottotipi, così matching e alert funzioneranno su entrambi i domini senza
mischiarne i campi. `CompanyProfile` descrive l'azienda da confrontare.
Definizioni complete dei campi: [`schemas/`](schemas/) (JSON Schema,
generato automaticamente - eseguire `uv run python scripts/export_schemas.py`
dopo aver modificato i modelli) e
[`src/agevolamatch/models/`](src/agevolamatch/models/).

## Aggiungere una nuova fonte

Implementa `agevolamatch.sources.base.BaseSource`: `fetch()` (I/O di rete),
`parse()` (payload grezzo → lista di dict nativi della fonte), `normalize()`
(un dict → `Opportunity`/`Incentive`). `run()` (ereditato) chiama tutti e tre
ed è tollerante ai singoli record malformati - un record rotto viene loggato
e saltato, non blocca l'ingestione. Vedi
[`sources/incentivi_gov_it.py`](src/agevolamatch/sources/incentivi_gov_it.py)
per un esempio completo, incluso caching HTTP e rate limiting.

## Regolare i pesi dello scoring

Non ancora implementato (Fase 2). Una volta disponibile, i pesi vivranno in un
file YAML (documentato qui e nell'help del comando `match`).

## Sviluppo

```bash
uv run pytest -q          # i test non usano mai la rete - vedi tests/fixtures/
uv run ruff check .       # lint
uv run ruff format .      # formattazione
```

Vedi [`CLAUDE.md`](CLAUDE.md) per le decisioni architetturali,
[`docs/sources.md`](docs/sources.md) per il mapping completo dei campi di
incentivi.gov.it e le note sulla qualità dei dati, e
[`docs/inspiration.md`](docs/inspiration.md) per i progetti di riferimento e
le verifiche di licenza.

## Roadmap

Vedi la sezione Stato sopra e le issue aperte per i dettagli sulle Fasi 2-5.

## Licenza

MIT - vedi [`LICENSE`](LICENSE). I dati provenienti da incentivi.gov.it sono
concessi con licenza separata IODL 2.0 dal loro editore; vedi
[`docs/sources.md`](docs/sources.md).
