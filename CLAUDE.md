# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

SmartCart is a shopping-cart price optimizer for Argentine supermarkets (Coto and Día). It scrapes both stores' internal APIs, unifies their catalogs by EAN barcode, lets a user build a cart via semantic search, and runs a constraint solver (Google OR-Tools) to find the cheapest way to split that cart across stores — accounting for promotions, bank/membership discounts, delivery costs, and each store's minimum-purchase threshold.

Full technical spec (data model, architecture rationale): `docs/smartcart_spec.md`.

The repo has two halves that run as separate processes and talk over HTTP:
- **`src/`** — Python/FastAPI backend + Postgres/pgvector.
- **`frontend/`** — React/Vite/Tailwind SPA (rebuilt from an earlier Streamlit prototype; the old `frontend/app.py`/`utils.py` no longer exist).

## Commands

### Backend

```bash
docker-compose up -d              # Postgres + pgvector on localhost:5432 (db/user/pass: smartcart/smartuser/smartpassword)
pip install -r requirements.txt
uvicorn src.api:app --reload      # API on http://localhost:8000 (interactive docs at /docs)
pytest                            # whole suite
pytest tests/test_optimizer.py    # single file
pytest tests/test_api.py::test_fastapi_endpoints   # single test
```

`docker-compose.yml` only defines the Postgres container — it does not run the API or frontend.

Tests are **not** isolated unit tests: `tests/test_api.py` and `tests/test_search.py` spin up the real FastAPI app (loading the `all-MiniLM-L6-v2` sentence-transformers model, which downloads on first run) and query the actual Postgres instance, so Postgres must be up and populated for those to pass. `tests/test_optimizer.py`, `tests/test_promos.py`, and `tests/test_category_tree.py` are pure-Python and don't need the DB.

`pytest.ini` sets `pythonpath = .`, so backend code is always imported as `src.module_name` (e.g. `from src.database import SmartCartDB`), never with relative imports.

### Frontend

```bash
cd frontend
npm install
npm run dev       # Vite dev server, default :5173
npm run build     # production build to frontend/dist
npm run lint      # oxlint
```

Talks to the backend via `VITE_API_URL` in `frontend/.env` (defaults to `http://localhost:8000`; CORS is wide open on the API side).

## Backend architecture (`src/`)

Data flows in one direction through distinct stages — when changing behavior, know which stage owns it:

1. **Scraping** (`src/scrapers/scraper_coto.py`, `scraper_dia.py`) — hit each retailer's internal API directly (Coto: internal BFF REST endpoint; Día: VTEX GraphQL `productSearchV3`), paginating per category. Each scraper's `if __name__ == "__main__"` block only iterates a small hardcoded list of MVP category IDs — the live catalog is intentionally narrow. `src/scrapers/{coto,dia}_categories.json` are separate, larger static dumps of each store's full category taxonomy (id/slug → `"Top -> Sub -> Leaf"` path string); they exist only for `category_tree.py` to build the mega-menu and are not otherwise linked to scraped products.
2. **Normalization + persistence** (`src/database.py`, `SmartCartDB`) — `save_store_products()` computes `unified_id = f"prod_{ean}"` and upserts into two tables: `unified_products` (one row per EAN, cross-store) and `store_products` (one row per store's offer, `ON CONFLICT` keyed on `(store_id, store_sku)`). Raw per-store promo payloads are normalized here via `src/promotion_parser.py`'s `PromoTransformer` (`.coto()` / `.dia()`) into one of four standard promo `type`s consumed later by the flattener: `direct_discount`, `conditional_discount_flat`, `conditional_discount` (e.g. "2nd unit 50% off"), `multi_buy` (e.g. 3x2). Each product's raw scraped category also gets normalized here through `SmartCartDB.CATEGORY_MAP` into one of only 4 coarse buckets (Lácteos/Golosinas/Almacén/Otros — everything else falls to Otros) — this is the value that ends up in `unified_products.category` and is what `GET /category/{name}` filters on.
3. **Embeddings** (`src/embeddings.py`) — a separate offline pipeline (`EmbeddingPipeline.generate_and_save_embeddings()`) that encodes `"{brand} {name}"` per product with `all-MiniLM-L6-v2` and backfills `unified_products.name_embedding` (pgvector `vector(384)`, HNSW index, cosine ops). Run this after scraping new products, before semantic search will find them.
4. **Category tree for the mega-menu** (`src/category_tree.py`) — an unrelated, purely-in-memory concern from the 4-bucket `CATEGORY_MAP` above: it parses both `*_categories.json` taxonomy dumps and merges Coto's and Día's differently-worded categories into one tree, in three layers of increasing cost/risk: (1) normalized-text equality, (2) token-subset containment (e.g. "Golosinas" ⊆ "Golosinas y Alfajores" — the safe default for catching "X" vs "X y Z" pairs with no false positives), (3) a conservative (0.90) cosine-similarity backstop reusing the same sentence-transformers model `/search` already has loaded. A small manual alias dict (`MANUAL_SUBCATEGORY_ALIASES`/`MANUAL_TOPLEVEL_ALIASES`) is the escape hatch for real duplicates neither automated step catches. **Do not lower the 0.90 threshold to catch more merges** — empirically, genuine near-duplicate category pairs and merely-related sibling categories occupy overlapping similarity bands (e.g. a true duplicate pair scored 0.798 while a false-positive-risk sibling pair scored 0.778), so threshold tuning alone can't safely separate them; add merges via the alias dicts instead. `build_category_tree()` takes the model as a parameter (dependency injection) so tests can run without loading it.
5. **Search & optimization API** (`src/api.py`) — FastAPI app; loads the sentence-transformers model and builds the category tree once at startup (`lifespan`, stored in the `ml_models` dict). Endpoints:
   - `GET /search?q=` — pgvector cosine-distance nearest-neighbor over `name_embedding`.
   - `GET /categories` — the flat 4-bucket list from `CATEGORY_MAP`.
   - `GET /categories/tree` — the merged Coto+Día taxonomy from `category_tree.py`, for the mega-menu. Its `has_direct_category_match` flag per top-level node tells the frontend whether to route a click to `GET /category/{name}` (exact match against the 4-bucket column) or fall back to `GET /search?q=<label>` (nearly always, since the coarse column only covers 3 of ~15 real top-levels).
   - `GET /category/{name}` — unlike `/search`, this one also computes `min_price` and picks a best-available `image_url` per product; `/search`'s response omits both (a known, pre-existing gap predating this API's current shape — not something to "fix" incidentally).
   - `POST /optimize` — the core flow: `src/flattener.py`'s `flatten_cart_prices()` first "flattens" each cart line into its cheapest net cost per store for the requested quantity (evaluating all applicable promos, gated by `user_memberships`), then `src/optimizer.py`'s `optimize_cart()` builds a CP-SAT model (`ortools`) with one boolean var per (product, store) pair plus a per-store "active" var, enforcing each store's minimum-spend threshold as a hard constraint and minimizing total cost (subtotal + delivery − capped bank-card discount). Returns HTTP 400 with a human-readable `detail` when infeasible. Post-solve, `api.py` also computes single-store baselines for comparison (a separate, simpler calculation — not routed through the solver, so it can legitimately diverge from the optimizer's own numbers), semantic "smart replacement" suggestions (nearest-neighbor by embedding within the same category, ≥20% cheaper for equal weight), and — when Día is part of the split — a VTEX "magic link" checkout URL (`generate_vtex_magic_link`).

## Frontend architecture (`frontend/src`)

Plain React state (Context + `useReducer`/`useState`, no Redux/Zustand/React Query) and native `fetch` (no axios) — deliberate choices for an app this size; don't introduce a state/data-fetching library without a concrete reason. Tailwind is v4, configured CSS-first (theme tokens live in `src/index.css` under `@theme`, not in a `tailwind.config.js`/`postcss.config.js`, which don't exist in this project).

- `api/` — thin `fetch` wrappers per resource (`products.js`, `categories.js`, `optimize.js`) over `api/client.js`'s `apiFetch`/`ApiError`. `optimize.js`'s `optimizeCart()` deliberately catches the backend's 400 "infeasible" response and returns `{ok: false, detail}` instead of throwing, since that's an expected outcome the UI renders inline, not an error state.
- `context/` — `CartContext` (`{unified_id: {name, quantity}}`, persisted to `localStorage`, mirrors the shape the old Streamlit prototype used) and `ProfileContext` (bank cards, memberships, delivery zone → looks up `utils/deliveryCosts.js`'s hardcoded per-zone cost table).
- `hooks/useProductFilters.js` — all product-listing facets (brand, price range, store availability, sort) are derived 100% client-side over an already-fetched result array; there's no server round-trip per filter change (unlike the Carrefour reference this UI's layout is modeled on), so there's intentionally no "Apply" button. Price bounds/sorting go through `utils/formatters.js`'s `resolveDisplayPrice()` rather than raw `product.min_price`, because `GET /search` results don't have `min_price` populated (see backend note above) — this helper falls back to the cheapest `available_at_stores[].base_price`.
- `components/megamenu/` — routing rule for any click (top-level, subcategory, or leaf) comes from the backend's `has_direct_category_match` flag (see `/categories/tree` above): `/categoria/:bucket` (→ `GET /category/{name}`) when true, otherwise `/buscar?q=` (→ `GET /search`).
- `components/optimize/` — renders `POST /optimize`'s response; `BaselineComparison` explicitly handles the case where the "optimized" split costs *more* than a single-store baseline (splitting across stores duplicates delivery cost, which can outweigh per-item savings on small carts) — don't assume savings is always positive there.
- Routes (`App.jsx`): `/` (home), `/buscar` (search results, reads `?q=`), `/categoria/:bucket` (category results), `/carrito` (cart + profile inputs + optimize flow, in that order since profile fields are only consumed at optimize-time).
