# SmartCart

**Live demo: [smart-cart-rouge.vercel.app](https://smart-cart-rouge.vercel.app)**

SmartCart finds the cheapest way to buy a grocery list in Argentina. It scrapes the
catalogs of **Coto, Día and Carrefour** every night, unifies them by barcode (EAN),
and uses a constraint solver (Google OR-Tools CP-SAT) to decide **how to split the
cart across the three chains to spend as little as possible**, accounting for
promotions, bank discounts, delivery costs and each store's minimum purchase.

A fourth chain, Vea, is also scraped but ships disabled by default: in October 2026
its product descriptions carried a payment-card skimmer, which I reported. SmartCart
strips that HTML before storing anything, and users have to opt in to Vea explicitly.

<!-- Add a screenshot or GIF of the app here: ![SmartCart](docs/screenshot.png) -->

| | |
|---|---|
| Chains scraped | 3 (Coto, Día, Carrefour), the same 75 shelves in each |
| Refresh | Every night at 03:00 ART, via GitHub Actions |
| Tests | 540+ (pytest) |
| Infra | API on Google Cloud Run, Postgres + pgvector on Neon, frontend on Vercel, all on free tiers |

## How it works

1. **Scraping.** Each chain exposes an internal API (Coto a REST BFF, Día and
   Carrefour VTEX GraphQL). The scrapers sweep **the same 75 shelves in all three
   chains**, which is what makes the catalogs comparable: comparing prices only
   makes sense if every chain covered the same aisle. Requests are deliberately
   paced so the scrapers don't behave like a bot.
2. **Unification.** The EAN is the product's identity (`prod_<ean>`). A product sold
   by all three chains is a single row with three offers.
3. **Semantic search.** Every product is embedded with `all-MiniLM-L6-v2` and
   queried through pgvector, so "gaseosa cola" finds Coca-Cola without a literal
   match.
4. **Optimization.** A CP-SAT model decides what to buy where, with each store's
   minimum purchase as a hard constraint and total spend (subtotal + delivery −
   bank discount) as the objective.

## Tech stack

- **Backend:** Python, FastAPI, PostgreSQL + pgvector, OR-Tools, sentence-transformers
- **Frontend:** React, Vite, Tailwind CSS, Leaflet
- **Infra:** GitHub Actions (nightly scrape matrix, one job per chain), Google Cloud Run, Neon, Vercel

## Running it locally

### 1. Database

```bash
docker-compose up -d
```

Starts Postgres with `pgvector` on `localhost:5432` (user/password/db:
`smartuser`/`smartpassword`/`smartcart`). The schema creates itself: `src/schema.py`
is idempotent DDL applied on first use, so there are no migrations to run.

### 2. Configuration

```bash
cp .env.example .env      # Copy-Item .env.example .env  in PowerShell
```

The defaults work for local development. `.env.example` documents every variable;
the only one you need to point the project at another database is `DATABASE_URL`.

### 3. Populate the catalog

```bash
pip install -r requirements.txt
python -m src.scripts.run_scrapers
```

**This step is required and takes hours** (about 1.5 h per chain): 75 shelves per
chain, and the time goes into the deliberate pauses between requests, not the
network. The nightly run scrapes the three chains in parallel; locally they run one
after the other.

To see the project working without the wait, one chain is enough:

```bash
python -m src.scripts.run_scrapers --store dia     # ~25 min
```

> **A product without an embedding is invisible to `GET /search`.** The script
> generates embeddings at the end; if you stop it early, the database is populated
> but search returns nothing. That's the most common reason a first run looks
> broken. Running the script again regenerates them.

### 4. Backend

```bash
uvicorn src.api:app --reload
```

API at `http://localhost:8000`, interactive docs at `/docs`. `GET /` reports the
service status (model loaded, connection pool, analytics).

### 5. Frontend

```bash
cd frontend
npm install
npm run dev
```

App at `http://localhost:5173`. It calls the API through `VITE_API_URL`
(`frontend/.env`, default `http://localhost:8000`), which **is read at build time**:
changing it requires a rebuild. `npm run build` outputs `frontend/dist` and
`npm run lint` runs oxlint.

## The database is derived

There's no sample dump in the repo, on purpose: a full sweep rebuilds the catalog
and embeddings from scratch, and it runs every night anyway. The production
database is private; if you want to try the project without waiting for a sweep,
ask for read-only access (the API works with a role that has no write permissions).

## Tests

```bash
pytest                                       # full suite
pytest tests/test_optimizer_correctness.py   # no database or model needed
```

`tests/test_api.py`, `test_search.py` and `test_search_ranking.py` start the real app
and query Postgres, so they need the database **running and populated** (and they
download the embedding model the first time). Most of the rest is pure Python and
runs with nothing else up.

## Documentation (in Spanish)

* [`docs/arquitectura.md`](docs/arquitectura.md): how it's built, every pipeline
  stage, the API, the frontend, and the reasoning behind each decision.
* [`docs/operacion.md`](docs/operacion.md): where it runs, how it's deployed and
  which limits to watch.
* [Issues](https://github.com/aviollaz/SmartCart/issues): open work and known risks,
  with the reasoning for each.
