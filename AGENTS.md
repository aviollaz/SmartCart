# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.
It is a condensed map — `CLAUDE.md` at the repo root has the full stage-by-stage rationale (why
each module exists, what broke before it did) and is the source of truth if the two ever
disagree.

## Project overview

SmartCart is a shopping-cart price optimizer for Argentine supermarkets (Coto, Día and
Carrefour). It scrapes each store's internal API, unifies their catalogs by EAN barcode, lets a
user build a cart via semantic search, and runs a constraint solver (Google OR-Tools) to find the
cheapest way to split that cart across stores — accounting for promotions, bank/membership
discounts, delivery costs, and each store's minimum-purchase threshold.

Full technical spec: `docs/smartcart_spec.md`. Pending work and known risks: `docs/TODO.md`.
Publishing the public demo (Cloud Run + Vercel): `ops/demo-publica.md`. Where the nightly sweep
runs today and why: `ops/README.md`.

The repo has two halves that run as separate processes and talk over HTTP:
- **`src/`** — Python/FastAPI backend + Postgres/pgvector.
- **`frontend/`** — React/Vite/Tailwind SPA (rebuilt from an earlier Streamlit prototype; the old
  `frontend/app.py`/`utils.py` no longer exist).

## Commands

### Backend

```bash
docker-compose up -d              # Postgres + pgvector on localhost:5432 (db/user/pass: smartcart/smartuser/smartpassword)
pip install -r requirements.txt
cp .env.example .env              # ANALYTICS_* — without it /optimize emits no analytics event
uvicorn src.api:app --reload      # API on http://localhost:8000 (interactive docs at /docs)
python -m src.scripts.run_scrapers   # populate the DB: all three scrapers + embeddings
python -m src.scripts.orchestrator   # same, but the unattended path (logs + telemetry)
python -m src.scrapers.get_bank_promos  # regenerate src/scrapers/bank_promos.json
pytest                            # whole suite
pytest tests/test_optimizer_correctness.py   # pure Python, no DB/model needed, runs anywhere
```

`docker-compose.yml` only defines the Postgres container — it does not run the API or frontend.
`src/scripts/run_scrapers.py` is the interactive entry point for populating the DB (`--store
coto|dia|carrefour|all`, `--skip-embeddings`); `src/scripts/orchestrator.py` is the unattended
one used in production, sharing `STORE_RUNNERS`/`build_arg_parser()` with it.

Tests are **not** isolated: `tests/test_api.py`, `test_search.py` and `test_search_ranking.py`
spin up the real FastAPI app (downloads the `all-MiniLM-L6-v2` model on first run) and query the
real Postgres instance — that DB must be up and populated for those to pass. Most of the rest of
the suite is pure Python and runs with nothing else up. `pytest.ini` sets `pythonpath = .`, so
backend code is always imported as `src.module_name`, never with relative imports.

### Frontend

```bash
cd frontend
npm install
npm run dev       # Vite dev server, default :5173
npm run build     # production build to frontend/dist
npm run lint      # oxlint
```

Talks to the backend via `VITE_API_URL` in `frontend/.env` (defaults to
`http://localhost:8000`; CORS is a real allow-list on the API side, not `*`).

## Backend architecture (`src/`)

Data flows in one direction through distinct stages:

1. **Scraping** (`src/scrapers/scraper_{coto,dia,carrefour}.py`) — hit each retailer's internal
   API directly (Coto: BFF REST; Día/Carrefour: VTEX GraphQL `productSearchV3`), paginating per
   category. Which categories get scraped lives in one place, `src/shelves.py` (see stage 1b) —
   not hardcoded per scraper. Día and Carrefour share `src/scrapers/vtex.py`
   (`extract_search_payload()`, `read_availability()`). Coto's price fields can be `null` with
   the key present — always read them through `_as_price()`. Coto's product URL must go through
   `build_coto_url()`/`_slugify()`, never string-concatenated from the API's `url` field.
2. **Which shelves get scraped** (`src/shelves.py`) — one table, `SHELVES`, mapping canonical
   shelf slugs to each store's category keys, so a shelf is scraped identically across all three
   chains (required for EAN-based unification to produce comparisons, not just catalog). Also
   holds `STORE_IDS`. `SECTIONS` groups shelves for the mega-menu (presentation only).
3. **Normalization + persistence** (`src/database.py`, `SmartCartDB`) — `save_store_products()`
   upserts into `unified_products` (one row per EAN) and `store_products` (one row per store
   offer). Promo payloads are normalized via `src/promotion_parser.py`'s `PromoTransformer` into
   one of four types consumed by the flattener. `src/schema.py` owns all DDL (idempotent,
   `CREATE ... IF NOT EXISTS`, no `DROP`). `unit_type` only ever holds `'g'`/`'ml'`/`'un'` — every
   size-comparing consumer depends on that vocabulary. EANs go through `src/ean.py`'s
   `normalize_ean()`. Obsolete rows are pruned per store, scoped to categories whose sweep
   completed cleanly (`prune_missing_store_products`).
4. **Embeddings** (`src/embeddings.py`) — offline pipeline, encodes `"{brand} {name}"` with
   `all-MiniLM-L6-v2` into `unified_products.name_embedding` (pgvector, HNSW, cosine). Run after
   scraping; an unembedded product is invisible to `GET /search`.
5. **Coto delivery logistics** (`src/coto_logistics.py`) — per-request lookup of Coto coverage
   and shipping cost via the public ATG actor `getCobertura`. Fail-open: only an affirmative
   "no coverage" excludes the store; anything else (timeout, malformed payload) falls back to the
   published flat tariff.
6. **Search & optimization API** (`src/api.py`) — FastAPI app, loads the embedding model and
   builds shelf data once at startup (`lifespan`). Key endpoints: `GET /search` (pgvector
   retrieve-then-rerank, availability-aware), `GET /categories`/`GET /category/{slug}` (backed
   by `shelves.py`, 404 on an unknown slug), `POST /products/by-ids` (batch lookup for purchase
   history; absence of an id means the product was pruned, not that it's out of stock),
   `GET /demo-cart` (cold-start sample cart), `GET /logistics/coto/coverage`, and `POST
   /optimize` — the core flow: `src/flattener.py`'s `flatten_cart_prices()` prices each line per
   store, then `src/optimizer.py`'s `optimize_cart()` runs a CP-SAT model minimizing subtotal +
   delivery − capped bank discount, with each store's minimum spend as a hard constraint.
   Registering a new store is a two-file change: `DEFAULT_MIN_SPEND_LIMITS` in `optimizer.py`
   and the frontend's per-zone `delivery_costs` table must both list it.
7. **Store-closure heuristic** (`src/strategic_swaps.py`) — post-solve: for each active store,
   finds products only it carries ("anchors"), looks for same-shelf substitutes, and re-runs the
   solver with that store excluded to see if closing it saves money. Result is `strategic_swaps`
   on the `/optimize` response.
8. **Bank discounts** (`src/promotions/`, `src/bank_promos.py`) — offline scrape of card/wallet
   discounts (unrelated to catalog scraping). `DiscountScraper` is a template method; Coto uses
   `httpx` against a public ATG actor, Día/Carrefour render client-side so they use Playwright
   (imported lazily so a machine without Chromium still works). `load_bank_promos(today)` filters
   by weekday before the table reaches the solver.
9. **Analytics emitter** (`src/analytics.py`) — fires one `cart_optimized` event per optimization
   at a separate analyzer service. Runs in a `BackgroundTask`, fail-open, never blocks or breaks
   `/optimize`. Config comes from `.env`, not the shell (`uvicorn --reload` never reloads the
   environment).
10. **Unattended orchestration** (`src/scripts/orchestrator.py`, `src/logging_setup.py`,
    `src/scraper_telemetry.py`, `ops/`) — the production sweep path around stage 1. Telemetry
    rows open before the work (`RUNNING`) and close after, so a killed process leaves a stranded
    row instead of silence. Runs nightly on GitHub Actions against Neon Postgres today (an
    Oracle-VM path is designed but blocked on capacity — `ops/README.md` has the current status).
    The public demo runs the API on Cloud Run and the frontend on Vercel, DB still on Neon.

## Frontend architecture (`frontend/src`)

Plain React state (Context + `useReducer`/`useState`, no Redux/Zustand/React Query) and native
`fetch` (no axios). Tailwind v4, configured CSS-first (`src/index.css`'s `@theme`, no
`tailwind.config.js`).

- `api/` — thin `fetch` wrappers per resource over `api/client.js`'s `apiFetch`/`ApiError`.
- `context/` — `CartContext` (`{unified_id: {name, quantity}}`, persisted to `localStorage`),
  `ProfileContext` (cards, memberships, geocoded `location` — delivery zone is derived from the
  address, never asked directly) and `HistoryContext` (client-side purchase history, session
  window of 30 min per entry, `smartcart_history_v1` key must never be version-bumped).
- **Address onboarding** — `components/onboarding/LocationModal.jsx`, used in two modes (blocking
  first-run vs. dismissable change-address) via one `onClose` prop, not two components.
- `hooks/useProductFilters.js` — all listing facets computed client-side over an already-fetched
  result array. Price sorting goes through `utils/formatters.js`'s `resolveDisplayPrice()`, not
  raw `min_price` (which ignores promos).
- **Cart line prices / estimated subtotal** — `hooks/useCartProducts.js` +
  `context/CartProductsContext.jsx` resolve cart items via `POST /products/by-ids` and show a
  labeled **estimate** (cheapest per-line price, ignores delivery/bank discounts/quantity promos)
  — this is deliberately not the same number as `/optimize`'s real total.
- `components/megamenu/` — two levels (section → shelf) from `GET /categories`; every click
  routes to `/categoria/:shelf`.
- `components/optimize/` — renders `POST /optimize`'s response (`SavingsPanel`,
  `LogisticsNotice`, per-store breakdown, strategic-swap suggestions).
- Routes (`App.jsx`): `/` (home), `/buscar` (search), `/categoria/:bucket` (category),
  `/carrito` (cart + profile + optimize flow).
