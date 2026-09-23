# AgevolaMatch

Motore open-source di matching tra incentivi pubblici italiani (finanza
agevolata) e profili aziendali - pensato per startup e PMI che vogliono capire
a quali incentivi possono davvero accedere.

Repo: [github.com/shagga75/agevolamatch](https://github.com/shagga75/agevolamatch)

*[Read this README in English](README.md)*

> **Disclaimer**: questo strumento ha finalità puramente informativa. I
> requisiti di ammissibilità vanno sempre verificati sulla fonte ufficiale
> (campo `url` di ogni incentivo) prima di presentare domanda. AgevolaMatch
> non presenta domande per conto dell'utente e non è affiliato a nessun ente
> pubblico italiano.

## Stato del progetto

Tutte e 5 le fasi previste sono implementate e validate contro dati live.

- ✅ **Fase 1 - Core**: struttura del repo, modelli Pydantic + JSON Schema,
  fonte incentivi.gov.it, storage SQLite con rilevamento nuovi/modificati.
- ✅ **Fase 2 - Matching + CLI**: filtri duri di ammissibilità, scoring pesato
  configurabile, spiegazioni (motivi a favore/contro/da verificare), export
  CSV/JSON, profilo di esempio.
- ✅ **Fase 3 - API + alert**: API REST FastAPI, canali email (SMTP) e
  Telegram con deduplica anti-reinvio, Docker + docker-compose.
- ✅ **Fase 4 - Extra**: scraper Invitalia (deduplicato), LLM opzionale, server MCP, dashboard Streamlit.
- ✅ **Fase 5 - Gare d'appalto**: ANAC + TED, un dominio e modulo di matching separati (vedi sotto).

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
uv run agevolamatch ingest --source invitalia   # scraping, deduplicato contro incentivi.gov.it
uv run agevolamatch ingest --source all

# Elenca gli incentivi salvati, con filtri
uv run agevolamatch list --status open --region Lazio --limit 20

# Confronta gli incentivi salvati con un profilo aziendale, con spiegazioni
uv run agevolamatch match --profile examples/startup_profile.yaml --top 10

# Esporta gli incentivi salvati (o, con --profile, i risultati del matching) in CSV/JSON
uv run agevolamatch export --format csv --output incentives.csv --status open
uv run agevolamatch export --format json --output ranking.json --profile examples/startup_profile.yaml
```

`ingest` può essere rieseguito in sicurezza: segnala un record come nuovo o
modificato solo se il suo contenuto è effettivamente cambiato (vedi
[`CLAUDE.md`](CLAUDE.md) per i dettagli), e non cancella mai gli incentivi
chiusi - restano consultabili come storico.

`match` applica prima i filtri di ammissibilità duri (stato, regione,
dimensione aziendale, tipo di beneficiario, ATECO, e alcuni controlli che i
dati di origine non permettono di verificare del tutto - vedi
[`docs/sources.md`](docs/sources.md)), poi ordina gli incentivi ammissibili
con uno scoring pesato configurabile, spiegando il motivo di ogni punteggio.
`examples/sample_match_output.json` è uno snapshot reale (datato) di questo
output contro il dataset live.

## API REST

```bash
uv run agevolamatch serve            # http://127.0.0.1:8000, docs su /docs
```

| Endpoint | Descrizione |
|---|---|
| `GET /health` | Controllo di stato |
| `GET /incentives?status=&region=&limit=` | Elenca gli incentivi salvati |
| `GET /incentives/{source_id}` | Un incentivo, 404 se sconosciuto |
| `POST /match?top=&min_score=` | Body: un oggetto JSON `CompanyProfile`. Ritorna i `MatchResult` ordinati |
| `GET /tenders?status=&province=&limit=` | Elenca le gare salvate |
| `GET /tenders/{source_id}` | Una gara, 404 se sconosciuta |
| `POST /tenders/match?top=&min_score=` | Body: un `CompanyProfile` (serve `cpv_codes`). Ritorna i `TenderMatchResult` ordinati |

`AGEVOLAMATCH_DB_PATH` (letto anche da `.env`) sceglie quale file SQLite legge l'API.

## Alert

Copia `.env.example` in `.env` e compila la sezione SMTP o Telegram (o
entrambe). Poi definisci una o più subscription - vedi
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

Un alert scatta solo per un incentivo che (a) è ammissibile e ha uno score
maggiore o uguale a `min_score`, e (b) non è già stato notificato con questo
identico contenuto - rieseguire il comando non rinvia mai lo stesso alert, e
un incentivo effettivamente modificato (content_hash diverso) ne genera uno
nuovo. `--dry-run` (default) mostra un'anteprima senza inviare né toccare il
registro di deduplica. Lo stesso file di subscription funziona anche per le
gare - vedi `gare alerts run` nella sezione [Gare d'appalto](#gare-dappalto---un-dominio-separato) sotto.

## LLM opzionale

Completamente opzionale e disattivato di default - matching, filtri e
scoring non usano mai un LLM. Se abilitato, `match --llm` estrae requisiti di
ammissibilità aggiuntivi menzionati nel testo libero della descrizione (es.
"azienda costituita da meno di 5 anni") che i campi strutturati non
catturano, e li aggiunge alla lista "da verificare" del risultato, prefissati
`[LLM]`. Non cambia mai l'ammissibilità né lo score, e qualsiasi errore del
provider (configurazione mancante, errore di rete, timeout) viene loggato -
il comando si completa comunque normalmente.

```bash
# Locale, gratuito, privato (serve un server Ollama attivo: https://ollama.com)
AGEVOLAMATCH_LLM_PROVIDER=ollama uv run agevolamatch match --profile examples/startup_profile.yaml --llm

# API a pagamento (OpenAI o qualsiasi endpoint OpenAI-compatibile)
AGEVOLAMATCH_LLM_PROVIDER=openai uv run agevolamatch match --profile examples/startup_profile.yaml --llm
```

Vedi `.env.example` per tutte le variabili `OLLAMA_*` / `LLM_*` (modello,
host, API key, base URL, timeout). Se `--llm` viene passato senza
`AGEVOLAMATCH_LLM_PROVIDER` impostato, il comando stampa un avviso e procede
senza arricchimento invece di fallire.

## Gare d'appalto - un dominio separato

La Fase 5 aggiunge un secondo dominio, deliberatamente separato: le gare
d'appalto pubbliche da **ANAC** (dati nazionali italiani, CC-BY-SA 4.0) e
**TED** (API ufficiale UE, senza autenticazione richiesta). Le gare non hanno
tipo di beneficiario, costi ammissibili o forma di agevolazione - il matching
si basa invece sui **codici CPV** (classificazione degli appalti, l'analogo
ATECO per questo dominio) e su una scadenza di presentazione, tramite un
modulo di matching dedicato (`agevolamatch.tenders`) con propri filtri duri e
scoring, separato dal matching degli incentivi.

```bash
uv run agevolamatch gare ingest --source anac    # delta mensile da dati.anticorruzione.it, solo aperte
uv run agevolamatch gare ingest --source ted     # finestra mobile di 60 giorni, Italia, bandi standard
uv run agevolamatch gare ingest --source all

uv run agevolamatch gare match --profile examples/startup_profile.yaml --top 10

# Alert per le gare - stesso file di subscription e stesso meccanismo di deduplica degli incentivi (vedi Alert sopra)
uv run agevolamatch gare alerts run --subscriptions examples/alert_subscriptions.yaml --dry-run
```

`CompanyProfile.cpv_codes` (separato da `ateco_codes` - non esiste una
tabella di raccordo ATECO↔CPV ufficiale) guida il matching delle gare;
`examples/startup_profile.yaml` imposta già entrambi, quindi funziona sia con
`match`/`gare match`, `alerts run`/`gare alerts run`, gli endpoint
`/tenders*` dell'API REST, che i tool `*_tenders`/`get_tender` del server
MCP. La scheda **📄 Gare** della dashboard elenca le gare salvate, e la sua
scheda **🎯 Matching** ha una sotto-scheda "Gare" accanto a "Incentivos" -
entrambe leggono gli stessi dati salvati e lo stesso profilo in sessione.

## Server MCP

Espone ricerca e matching a qualsiasi client MCP (es. Claude Desktop) tramite
`agevolamatch-mcp`, via stdio. Sei tool, tutti wrapper sottili sullo stesso
codice storage/matching usato da CLI e API REST:

| Tool | Descrizione |
|---|---|
| `search_incentives(status, region, limit)` | Elenca gli incentivi salvati |
| `get_incentive(source_id)` | Dettagli completi di un incentivo, o null |
| `match_company_profile(profile, top, min_score)` | Match di incentivi ordinati - forma di `profile`: `schemas/company_profile.schema.json` |
| `search_tenders(status, province, limit)` | Elenca le gare salvate |
| `get_tender(source_id)` | Dettagli completi di una gara, o null |
| `match_tenders(profile, top, min_score)` | Match di gare ordinati - usa `profile.cpv_codes` |

Aggiungi alla configurazione del tuo client MCP (es. `claude_desktop_config.json` di Claude Desktop):

```json
{
  "mcpServers": {
    "agevolamatch": {
      "command": "uv",
      "args": ["run", "--directory", "/percorso/assoluto/a/agevolamatch", "agevolamatch-mcp"],
      "env": { "AGEVOLAMATCH_DB_PATH": "/percorso/assoluto/a/agevolamatch/data/agevolamatch.db" }
    }
  }
}
```

## Dashboard

```bash
uv sync --extra dashboard   # installa streamlit (opzionale - non è una dipendenza core)
uv run streamlit run src/agevolamatch/dashboard/app.py
```

Quattro schede, stesso codice storage/matching di CLI/API/server MCP: un
elenco incentivi filtrabile con vista di dettaglio, un elenco **gare**
filtrabile con vista di dettaglio, un editor del profilo aziendale (carica
il profilo di esempio o costruiscine uno con un form - inclusi i codici CPV
per il matching delle gare), e una scheda di matching con una sotto-scheda
"Incentivos" e una "Gare", ciascuna con le stesse spiegazioni a favore/
contro/da verificare che stampa la CLI.

## Docker

```bash
cp .env.example .env   # compila le credenziali SMTP/Telegram se servono
docker compose up --build
```

Avvia il servizio `api` (porta 8000), il servizio `dashboard` (porta 8501) e
un servizio `ingest` che ripete `ingest` + `alerts run` ogni
`INGEST_INTERVAL_SECONDS` (default: una volta al giorno). Il passo alert di
`ingest` è in dry-run di default (`ALERTS_DRY_RUN=true` in
`docker-compose.yml`) - passalo a `false` solo dopo aver testato le
credenziali reali in `.env`. Monta il tuo file di subscription al posto di
`examples/alert_subscriptions.yaml` nei volumi del servizio `ingest`.

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

I pesi (vedi [`src/agevolamatch/matching/weights.py`](src/agevolamatch/matching/weights.py)
per i default) vivono in `ScoringWeights`: `ateco_match`, `eligible_costs_match`,
`support_form_match`, `amount_fit`, `urgency`, `special_flags_match`. Passa un
file YAML per sovrascriverne un sottoinsieme qualsiasi:

```yaml
# weights.yaml
ateco_match: 40
amount_fit: 10
```

```bash
uv run agevolamatch match --profile examples/startup_profile.yaml --weights weights.yaml
```

Nessun LLM viene usato nella pipeline di matching: ogni componente del
punteggio arriva con una motivazione leggibile, mostrata sotto "motivi a
favore/contro/da verificare" sia nell'output CLI che nell'export CSV/JSON.

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

Tutte e 5 le fasi previste sono complete - vedi Stato sopra. Le issue aperte
tracciano eventuali estensioni (es. un mapping comune/provincia→regione, una
tabella di raccordo ATECO 2007↔2025 - entrambi documentati come limiti noti
in `CLAUDE.md`).

## Licenza

MIT - vedi [`LICENSE`](LICENSE). I dati provenienti da incentivi.gov.it sono
concessi con licenza separata IODL 2.0 dal loro editore; vedi
[`docs/sources.md`](docs/sources.md).
