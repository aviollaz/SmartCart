# CLAUDE.md

Guidance for Claude Code in this repository.

## Project overview

SmartCart finds the cheapest way to split a grocery cart across six Argentine supermarkets (Coto, Día, Carrefour, Vea, ChangoMás, Jumbo). It scrapes each store's internal API, unifies catalogs by EAN, lets the user build a cart via semantic search, and runs CP-SAT (OR-Tools) over promotions, bank/membership discounts, delivery costs and minimum spend.

- `src/` — Python/FastAPI backend + Postgres/pgvector. `frontend/` — React/Vite/Tailwind SPA. Two processes over HTTP.
- `docs/arquitectura.md`: how it works, stage by stage. `docs/operacion.md`: where it runs, deploy commands, Neon limits, PowerShell gotchas. Pending work: `gh issue list`.
- `ops/` holds only `vars.YAML` (Cloud Run env vars) and `probe_endpoints.py`.

## Commands

### Harness: el chequeo y las reglas de cierre

```bash
# Setup (una vez)
docker-compose up -d
pip install torch --index-url https://download.pytorch.org/whl/cpu && pip install -r requirements.txt
cd frontend && npm ci && cd ..

# EL chequeo — lo corren el hook Stop (.claude/hooks/stop_check.py) y CI (.github/workflows/ci.yml)
pytest -m "not catalogo"
cd frontend && npm run lint && npm run build
```

`-m "not catalogo"` deja afuera los tests marcados `@pytest.mark.catalogo` (necesitan Postgres **poblado** + el modelo); `pytest` a secas corre todo. Los de Postgres vacío (`test_schema`, `test_pruning`, …) se saltean sin Docker y corren de verdad en CI. El hook fuerza la base de docker-compose (`127.0.0.1`, `connect_timeout=1`); a mano, `pytest` usa la `DATABASE_URL` del `.env`, que puede ser Neon. Sin `connect_timeout`, un Postgres apagado en Windows **cuelga** el suite en vez de saltearlo.

- **No se termina una tarea con el chequeo en rojo.** No decir "listo" si falla; si no se puede arreglar, reportarlo con la salida. Un *skip* por falta de Postgres no es verde para cambios en `src/database.py`/`src/schema.py`: levantar Docker y correrlos.
- **Los tests verifican comportamiento observable** (entradas, salidas, efectos visibles), no implementación: nada de testear funciones privadas, estructura interna ni mockear todo.
- **Test primero.** Para cada feature o fix: definir y escribir los tests desde lo que tiene que pasar, correrlos y confirmar que **fallan**, recién después implementar.
- **Si un test existente falla, se arregla el código, no el test.** Cambiar un test solo vale si cambió el comportamiento esperado, y se explica por qué.
- **Tests legibles por una persona:** el nombre dice el comportamiento en castellano (`test_carrito_bajo_el_minimo_devuelve_400`), el cuerpo en tres bloques visibles (preparar / ejecutar / verificar), datos literales a la vista, una idea por test.
- **Todo plan de ejecución lista los tests que definen "terminado"** (nombre + qué verifica, una línea cada uno) antes de implementar, para que el usuario los revise.
- Un test nuevo que necesite la base poblada lleva `@pytest.mark.catalogo`.

### Backend

```bash
docker-compose up -d                              # only Postgres + pgvector, localhost:5432 (smartcart/smartuser/smartpassword)
cp .env.example .env                              # ANALYTICS_*: without it /optimize emits no analytics event
uvicorn src.api:app --reload                      # API on :8000, docs at /docs
python -m src.scripts.run_scrapers [--store <key>|all] [--skip-embeddings]   # interactive sweep + embeddings
python -m src.scripts.orchestrator                # unattended sweep (logs + telemetry); production runs it on GitHub Actions
python -m playwright install chromium             # one-off, only for the bank-promo scrapers (Día also needs the `tesseract` binary on PATH)
python -m src.scrapers.get_bank_promos [--store coto|dia|carrefour|all] [--dry-run]   # regenerate src/scrapers/bank_promos.json
python -m src.scrapers.get_vtex_categories --store dia   # regenerate a VTEX store's taxonomy dump
python -m src.scripts.medir_busqueda [--modo hibrido]    # /search relevance baseline (same SQL as the API)
python -m src.scripts.repair_coto_urls --dry-run  # one-shot: sanitize stored Coto product_url
python -m src.scripts.curar_frescos               # maintain src/fresh_items.py (live scrape, no DB)
docker build -t smartcart-api . && docker run -p 8080:8080 -e DATABASE_URL=... smartcart-api
pytest tests/test_optimizer.py                    # one file
pytest tests/test_api.py::test_fastapi_endpoints  # one test
```

- `run_scrapers` runs every store over `keys_for_store(<key>)`, then regenerates embeddings (a product without one is invisible to `/search`). A failed store doesn't stop the others; a failed category doesn't stop its store (`_run_store` reports it via `StoreRunResult`).
- `orchestrator` imports `STORE_RUNNERS` from `run_scrapers` and shares `build_arg_parser()`, so a new flag lands in both.
- `get_bank_promos`: a store that fails keeps its previous block in the JSON — an emptied block silently stops discounts that exist.
- Widening the catalog is a row in `src/shelves.py`. A new VTEX store is a `VtexCatalogScraper` subclass listed in `src/scrapers/vtex_stores.py`.
- Imports are always `src.module` (`pytest.ini` sets `pythonpath = .`), never relative.

### Frontend

```bash
cd frontend
npm run dev      # Vite on :5173; talks to VITE_API_URL (frontend/.env, default http://localhost:8000)
npm run build    # frontend/dist
npm run lint     # oxlint
```

### What the tests need

- **Postgres populated + model:** `test_api.py`, `test_search.py`, `test_search_ranking.py` (the model downloads on first run).
- **Postgres, no model:** `test_pruning.py`, `test_scraper_telemetry.py`, `test_save_concurrency.py` (synthetic ids, safe on a populated DB) and `test_schema.py` (idempotent DDL + catalog reads only).
- **Everything else is pure Python.**
- Two optimizer files, not redundant: `test_optimizer.py` hits the real DB and passes vacuously on an empty one. **New optimizer assertions go in `test_optimizer_correctness.py`**: it monkeypatches `flatten_cart_prices` with fixed matrices and `load_bank_promos` with `PROMOS_FIJAS`, and compares against `_brute_force_optimum`, a brute-force oracle with the solver's integer-cents arithmetic (truncating bank-discount division included).

## Backend (`src/`)

Data flows one way through these stages; know which one owns a behavior before changing it. Recurring doctrine: **erring expensive forfeits a saving; erring cheap breaks the promise the app makes.** When in doubt, quote higher, exclude less, and fail open.

### 1. Scraping (`src/scrapers/`)

Each scraper calls the store's internal API (Coto: BFF REST; VTEX stores: GraphQL `productSearchV3`) over the keys its store has in `src/shelves.py`.

- **Page loops `break` only on a valid empty page; every other early exit raises `CategoryScrapeError`** (`errors.py`): non-200, transport error, a page repeating seen SKUs (the endpoint ignores `page`), exhausting `MAX_PAGES`. A truncated category counted OK makes everything it missed look discontinued, and pruning deletes it. `tests/test_scraper_truncation.py` covers each path per store.
- **Coto prices can be `null` with the key present**: read them via `_as_price()` (`float(d.get(k, 0))` raises).
- **Coto URLs: `build_coto_url()`, slug via `_slugify()`.** The API's `url` is a relative fragment, and a raw `%` from the product name makes the CDN answer 400 (24% of stored URLs were broken). `_slugify` is idempotent, which is what lets `repair_coto_urls` fix stored rows.
- **VTEX URLs: `vtex.storefront_url(link, BASE_URL)` keeps only the path.** VTEX has returned internal domains (`diaio.vtexcommercestable.com.br`, `diaio.myvtex.com`) that redirect to an admin login. `product_url` is in `ON CONFLICT`, so one sweep repairs stored rows.
- **The persisted-query `sha256Hash` locks the field set server-side**: read anything beyond the known fields with `.get()`.
- **A rotated hash answers 200 with `errors` and no `data`**: `extract_search_payload()` raises instead of reading it as an empty last page.
- **VTEX's gateway also answers 200 + `errors` on transient failures** ("Request failed with status code 500"). `is_transient_graphql_error` retries only when *every* error is 429/5xx, so a rotated hash still fails at once.
- **`in_stock` comes from `read_availability()`, defaulting to `True` when the field is absent**: a rotated hash dropping it would otherwise mark the whole catalog sold out. Today `hideUnavailableItems: True` filters sold-out items server-side; loosening it returns items with `AvailableQuantity: 0`. Per-address availability is not covered (no `regionId` is sent); the UI says so in `StoreBreakdownCard`.
- **One VTEX scraper**: `VtexCatalogScraper` (`vtex.py`) does payload, retries and pagination; a store declares `STORE_KEY`, `LABEL`, `BASE_URL`. It POSTs the JSON body and derives `map` from the slug's segment count.
- **Taxonomy dumps** (`src/scrapers/<key>_categories.json`) feed the dietary parser (the path is evidence text) and `tests/test_shelves.py` (every key must exist). Regenerate with `get_vtex_categories`, which parses the URL path (`slug_from_url`) because VTEX changes domains.
- **Vea:**
  - `ListPrice` is not a price (always `Price` × 82,645 or × 100): `PromoTransformer.vea()` replaces it with `Price`.
  - No product promo is visible anywhere (teasers, highlights, checkout simulation), so Vea is quoted without promos.
  - It sells through sales channel 34 (`Store.sales_channel`); the cart URL fails with `sc=1`.
  - In Oct 2026 its descriptions carried a card skimmer (`<img onerror="eval(atob(…))">`). `clean_description()` stores plain text only; a test pins a defanged copy.
- **ChangoMás** (masonline.com.ar, `sc=1`):
  - `ListPrice` is a real list price and the gap is an open discount (the public schema.org offer shows `Price` to everyone), so `PromoTransformer.changomas()` is Día's rule. `teasers` came empty on every product sampled (Nov 2026).
  - Prices are per branch (the same yerba is $5.289 in CABA, $4.399 in Córdoba); the catalog, with no `regionId`, returns CABA's.
  - The $20.000 minimum comes from a real checkout. No endpoint publishes it: the minicart theme prop `minPurchaseAmount` says 2000 and is stale.
- **Jumbo** (jumbo.com.ar) is Cencosud like Vea, and behaves like it everywhere:
  - The same tree: every Vea key exists in Jumbo, so `jumbo=` copies `vea=` row by row (its three `()` included). A key change on one is worth checking on the other.
  - The same broken `ListPrice` (`Price` × 82,645): `PromoTransformer.jumbo()` is Vea's rule. `teasers` came empty (Nov 2026).
  - Sales channel 32 (`sc=1` errors out on checkout). The $20.000 minimum comes from a real checkout; the simulation's `minimumOrderValue` says 0, which makes Vea's 0 (same source) suspect.
- **The `warning` mechanism stays for next time** (no store has one today). A store with a `warning` on its `Store` row and the matching text in `constants.js` stays in the catalog and the solver, but the frontend excludes it unless the user opts in (`ProfileContext.optedInStores`), and `ProductPage` never links to it. `tests/test_stores.py` checks both sides match.

### 1b. Shelves (`src/shelves.py`)

`SHELVES` maps 75 canonical shelf slugs to per-store key tuples (141 Coto, 109 Día, 86 Carrefour, 104 Vea, 97 ChangoMás, 104 Jumbo), in nine `SECTIONS`. One row decides what gets scraped, a product's category (`unified_products.shelf`), what can substitute what, and what the mega-menu draws.

- **Alignment is the point.** Products unify by EAN, so they only compare if every store swept the same shelf. Favor branded packaged goods, where EANs coincide.
- **Every row names every store; an empty tuple is a decision.** Vea's and Jumbo's three feminine-care rows are `()` because their single leaf mixes pads, liners and tampons. Two mixed Día leaves stay out of Limpieza for the same reason, and five ChangoMás rows are `()`: one canned-goods leaf mixes tuna with peas, one mixes sausages with salami, one frozen leaf mixes fries with nuggets. `test_shelves.py` requires the store to be named, not to have keys.
- **No key may be an ancestor of another key of the same store** (`test_ninguna_clave_contiene_a_otra`): the parent's batch carries the child's products and the last shelf swept wins `shelf`. Use the sibling leaves.
- **A key existing in the dump doesn't mean it has products.** Stores rename nodes and keep the old one empty (Día, Sep 2026: 20 dead keys, 15 empty shelves, all categories "OK"). When a store's keys read empty, regenerate its dump first; the diff names the dead keys.
- **Keys returning byte-identical results** (Día's two yogurt leaves): keep one.
- **`shelf_for_key()` returns `None` outside the table, and `save_store_products()` rejects the product** instead of inventing a shelf.
- **Out on purpose:** perfumes and make-up (no aligned Día node), diapers, medicines, fresh fish, in-store bakery. Beef and pork share `carnes` because Coto mixes them.
- **`SECTIONS` is presentation only**: an unlisted section sorts last with the generic icon. `STORE_IDS` is re-exported from `src/stores.py`.

### 1c. Fresh produce and meat (`src/fresh_items.py`)

Scale codes (GS1 prefix 20-29) are invented per chain, so `normalize_ean()` drops them. `FRESH_ITEMS` declares which SKU of each chain is the same product; `resolve_identity()` gives them `unified_id = fresh_{slug}` with the item's name and unit (`"kg"` → `('g', 1000.0)`, `"un"` → `('un', 1.0)`). Quantity 1 of a `kg` item is 1 kg (integers only, issue #31).

- **Hand-curated, not a similarity threshold**: "ananá" sits at 0.49 from "nalga", closer than real pairs. Embeddings only propose (`curar_frescos`).
- **Curation rules:** same variety and common grade (no premium lines); one SKU per store per item (the flattener can't handle two); no pieces sold at approximate weight (all of Coto's chicken); at least two chains. `tests/test_fresh_items.py` enforces the structural ones; line comments justify non-identical joins.
- **Maintenance:** a re-listed SKU drops out silently. Run `curar_frescos` periodically and read "Obsoletos". Moving a SKU changes its `unified_id`; the old row is pruned that night.

### 2. Persistence (`src/database.py`, `src/schema.py`)

`save_store_products()` upserts `unified_products` (one row per `prod_{ean}`) and `store_products` (`ON CONFLICT (store_id, store_sku)`), normalizing promos through `PROMO_TRANSFORMERS[store_id]` into `direct_discount`, `conditional_discount_flat`, `conditional_discount` or `multi_buy`. A store missing from that dict is a `KeyError`; it used to save silently without promos.

- **`shelf` and `source_category` are read with `prod['…']`, never `.get()`.** A `NULL` `source_category` makes scoped pruning delete nothing while reporting success; a `NULL` `shelf` hides the product from `/category` and substitution. `test_scraper_ingest_keys.py` checks each scraper's output.
- **`src/schema.py` owns all DDL**, idempotent (`IF NOT EXISTS`), applied by `SmartCartDB`, `EmbeddingPipeline`, `ScraperTelemetry` and the API's `lifespan` (which logs and continues, for read-only roles). **It never drops anything**: destructive changes go in a one-off script like `migrate_shelves.py`. `test_schema.py` asserts both.
- **Every derived column goes in `ON CONFLICT DO UPDATE SET`, in the same edit that adds it.** A re-scrape is the only way to correct data, so an omitted column is frozen at its first value. `unified_product_id` is the sharpest case: omitted, an EAN correction left the offer on the old product forever. Exception: `name_tsv`, a generated column.
- **`unit_type` is only `'g'`, `'ml'` or `'un'`**, via `size_parser.normalize_magnitude()`; anything unknown becomes `(1.0, 'un')`. A value outside that vocabulary silently drops out of every size comparison. The VTEX `< 1.0` branches decide magnitude (per litre/kilo) and shouldn't change without fresh data; `normalize_magnitude()` only decides vocabulary.
- **EANs go through `normalize_ean()` (`src/ean.py`) in every scraper:**
  - A GTIN-14 becomes its GTIN-13 only if the check digit validates; anything else over 13 characters becomes `None` and the product lands as `{store_id}_{store_sku}`. (`VARCHAR(13)` overflow used to roll back whole categories.)
  - **Codes of 13 characters or fewer pass untouched, unvalidated.** Validating would re-key hundreds of UPCs that already unify, and the pruner would delete their rows.
  - Exception: 13 digits starting with `2` (scale codes) become `None`, because chains reuse those numbers for different products.
- **Pruning** (`prune_missing_store_products(store_id, seen_skus, categories=…)`) deletes the store's rows not seen in the sweep, then orphaned `unified_products`.
  - `seen_skus` must be the complete universe, so a partial sweep prunes only its clean categories (`StoreRunResult.prune_scope` = `ok_categories`).
  - A complete sweep prunes the whole store, which is the only way rows with `NULL` `source_category` ever leave.
  - Brakes: an empty `seen_skus` never prunes (rotated-hash signature), and a delete over `MAX_PRUNE_RATIO` (30%) **of the scope** aborts.
  - **Never replace this with a percentage tolerance on `complete`**: that deletes live catalog in proportion to what failed.
  - `--prune-dry-run` runs the real DELETEs and rolls back.
- **Batches are sorted by `unified_id` before writing.** Stores run in parallel, and different lock orders deadlock (`test_save_concurrency.py` deadlocks 3/3 without it). Writes retry on `_TRANSIENT_WRITE_ERRORS` (3 attempts): two stores inserting the same new EAN hit `UniqueViolation` on the second unique index, and the retry takes the UPDATE path. `_prepare_row` is separate from `_write_rows` so the batch can be sorted first.
- **`store_products.name` is the store's own name**; `unified_products.name` is whoever wrote last. Nothing reads it yet.
- **`store_products.description`** is VTEX's text through `vtex.clean_description()`: HTML flattened, Carrefour's private-label template, empty HTML and repeated names dropped. Coto sends `None`. Display only; **never in `dietary_sources`**.
- **`unified_products.name_tsv`** (hybrid search): generated `tsvector`, `spanish` config, accents stripped via the `IMMUTABLE` wrapper `smartcart_unaccent()`, GIN index.
- **Carrefour's price gap is the Mi Carrefour member price.** `.carrefour()` emits it with `requires_membership: "mi_carrefour"` when the highlights or teasers use card/loyalty wording, so users without the membership see list price.
- **Dietary flags** (`src/dietary_parser.py`):
  - Explicit phrases only; never the bare tokens `gluten` or `vegetal`, which also match "contiene gluten".
  - Only text about that product: name, brand, category path, structured fields. Never `description`/marketing, which names sibling products (a Hellmann's ketchup read as vegan).
  - Flags are **overwritten** on conflict, never OR-accumulated, so a false positive can be fixed. `FALSE` means "no evidence".

### 3. Embeddings (`src/embeddings.py`)

Offline: encodes `"{brand} {name}"` with `all-MiniLM-L6-v2` into `name_embedding` (`vector(384)`, HNSW, cosine). Run it after scraping.

### 4. Precedent from the retired category tree

`src/category_tree.py` is gone. One lesson from it is still cited: true near-duplicate categories and merely related ones overlap in similarity (0.798 vs 0.778), so no threshold separates them. **A vocabulary mismatch gets an explicit table, never a looser cutoff**; `src/shelves.py` is that table.

### 5. Logistics (`src/coto_logistics.py`, `src/vtex_logistics.py`, one module per VTEX store)

Online, before the solver: per store, does it deliver here and what does shipping cost. **Fail-open**: only an affirmative "no" excludes a store; any failure keeps it competing at the per-zone cost (`source: "fallback"`). `ok=False` ("couldn't tell") is distinct from `covered=False` ("the store said no"), and **only successful lookups are cached** (30 min), so a timeout doesn't pin the fallback.

- **Coto:**
  - The route is the ATG actor `GET /rest/model/atg/actors/cProfileActor/getCobertura?lat=&lng=`: public, no cookie, no `_dynSessConf`. Older notes about `www.coto.com.ar/getCobertura` or a `getCostoEnvio` POST are wrong.
  - Its SPA answers **200 with `index.html` for any unknown path**, so `_fetch_json()` requires a JSON content type.
  - Coverage means `sucursal.mensajeError == "-"`.
  - There is no anonymous address-level shipping cost (those actors need login). The published tariff (`getParametros2` → `ENTREGA_RAPIDA_COSTO`) **disappeared in Nov 2026**, so Coto always uses the per-zone fallback. That valid-but-empty answer is cached as the `_SIN_TARIFA` sentinel (`None` already means "nothing cached"); it used to be re-fetched on every `/optimize`.
  - Open question, don't change in passing: `MINIMOGENERAL = 30000` vs the `15000` min spend in `DEFAULT_MIN_SPEND_LIMITS`.
- **Shared VTEX part** (`vtex_logistics.py`): a request that never raises, the 30-minute success cache, `resolve()`'s fail-open contract. A store supplies `delivery_options(client, lat, lng) -> [(cents, branch)] | None`.
- **Día:**
  - `regions` lists the branches (`sellers: []` is a real "no"), then `orderForms/simulation` per seller with dummy SKU `10001664`.
  - Coverage is **any** seller with a delivery SLA, not the first: in Moreno one branch only offers pickup.
  - A failed seller makes the answer indeterminate.
  - **Shipping depends on weight** (issue #15). `quote_cart()` simulates the real cart at the chosen branch (`None` if any line lacks home delivery). After the solve, `_requote_dia_shipping` re-optimizes when the quote is higher, at most `DIA_REQUOTE_ROUNDS` times, and **the cost only rises** (lowering it can oscillate between two splits). It is skipped without coordinates or on a fallback lookup.
- **Vea:** `regions` ignores the coordinate (~88 branches everywhere), so Vea can't say "no". One simulation carries one item per branch (~2 s). Home delivery is the SLA named "Envío a Domicilio"; cost is `sla.price` + the cheapest window.
- **ChangoMás:** `regions` does filter by coordinate (Ushuaia: `sellers: []`, a real "no", as in Día). Every covered address also lists four national sellers (`masonlineprod0008/0014/0095/0101`) that answer `withoutStock`, so it simulates once with one item per seller (Vea's pattern) and keeps the seller with an "Envío a domicilio" SLA. Cost is `sla.price` + the cheapest window: $3.999 in all four zones, but $13.000 in Quilmes (same branch as Lanús, so it is distance-based).
- **Jumbo:** Vea's code with its own domain, channel 32 and SKU (`cencosud_lookup()` in `vea_logistics.py`). `regions` ignores the coordinate too; "Envío a Domicilio" is $3.999 in all four zones (Nov 2026), Córdoba and Ushuaia are pickup only.
- **`_resolve_logistics_stage` runs the six stores in parallel** (`ThreadPoolExecutor`; `map` keeps list order, so `excluded_stores` order is stable): the stage costs the slowest store (usually Vea, 2-6 s cold), not the sum. Meanwhile `optimize_shopping_cart` flattens the cart in another thread and passes `flat_prices` down (`_optimize_purchase_window`, `_requote_dia_shipping`, `_enrich_successful_result`, `build_semantic_suggestions(cart_prices=…)`) instead of each re-flattening.

### 6. API (`src/api.py`)

Loads the sentence-transformers model once in `lifespan` (`ml_models`).

**Stores** are declared once per language: `src/stores.py` (`Store`: `key`, `id`, `name`, `min_spend`, `delivery_cost`, `checkout_domain`, `sales_channel`) and `frontend/src/utils/constants.js`'s `STORES`. Store lists, min spends, delivery defaults, promo store sets, image priority and checkout stores derive from them. `tests/test_stores.py` checks what can't be derived:
- the per-store code tables: `run_scrapers.STORE_RUNNERS`, `promotions.SCRAPERS`, `curar_frescos._scrapers()`, `database.PROMO_TRANSFORMERS`;
- every zone of `deliveryCosts.js`;
- the `scrape.yml` defaults;
- the taxonomy dumps.

`optimize_cart` indexes `delivery_costs[store]` with no default, so a zone missing a store crashes `/optimize`.

**`GET /search`** (SQL in `src/search.py`, shared with `medir_busqueda`):
- **Retrieve-then-rerank in one query:** a pool of `SEARCH_POOL_SIZE` (100) by pure distance (what HNSW accelerates), reordered by `distance − STORE_BONUS × min(store_count − 1, STORE_BONUS_CAP)`. **The pool must exceed `limit`**: the client only sees what Postgres chose, so reranking there can't change which products appear.
- **`hnsw.ef_search` (default 40) caps the pool**, so it is raised per connection with `set_config` (plain `SET` takes no bind parameter). `test_search_ranking.py` asserts the full pool.
- **`STORE_BONUS = 0.01` is calibrated; don't raise it.** Its worst-case cost (0.02) is ~18% of the median top-20 spread. At 0.02 "yogur bebible" loses actual drinkable yogurts; at 0.05 rank 79 reaches the top.
- `distance` is returned raw, never the ranking score. `store_count` counts `in_stock` offers and excludes `hidden_stores` in SQL, so ranking uses stores the user can buy from.
- Hybrid mode (lexical `ts_rank_cd` over `name_tsv` + dense, Reciprocal Rank Fusion k=60; `build_lexical_query` passes letters and numbers only) is off (`DEFAULT_SEARCH_MODE = "denso"`) until measured (issue #24).

**Listings** (`/search`, `/category`) return `ProductPage` (`items, total, page, page_size, brands, price_bounds`, 48 per page) with every grid filter resolved server-side in `_paginate_listing`.
- The browser only holds one page, and shipping a whole shelf costs too much (`vinos`: 1.572 products, 1,8 MB, ~13 s).
- The universe (the whole shelf, or the search pool) is built in Python because the filter/sort price, `_display_price`, comes from the promo evaluator.
- `hidden_stores` (coverage ∪ user-disabled) strips offers before `_build_product_response`, so prices come out computed over what's left.
- Facets count before the brand/price/store filters, so picking a brand doesn't erase the others.

**Product payloads:**
- **All product endpoints use `_build_product_response()` and `_build_store_offer()`**; only `distance` differs (raw for `/search`, `0.0` elsewhere). `min_price` is the minimum *list* price, a fallback only.
- **`promo_unit_price`** is the net price at quantity 1 via `flattener.evaluate_best_promo()`, the optimizer's own evaluator. Conditional promos stay `None` until their threshold.
- **`quantity_promo`** (`_best_quantity_promo`) announces the best `required_quantity > 1` promo when it beats the q=1 price.
- **Memberships:** only the ones the user declared (`memberships` / `user_memberships`), so a club price is never shown to a non-member. **Bank cards never enter product prices**: they're capped store-wide discounts, `/optimize`-only.
- **`unit_price`** (`_build_unit_price`): the announced price (cheapest `promo_unit_price ?? base_price`) over `total_volume_weight`, per kilo for `'g'` and per litre for `'ml'`, **one base always**: two bases in one grid break the comparison. `None` for `'un'`, which means the parser gave up. `substitutions.format_size()` keeps its 1000 cutoff because it writes a size, not a comparison base. Multipacks are never multiplied, so the error can only run expensive.

**Other endpoints:**
- **`GET /categories`**: `src/shelves.py` grouped by section; no DB.
- **`GET /category/{slug}`**: a slug outside `SHELVES` is **404**, not `[]`. Ordered by `store_count DESC, name, u.id`; the order must be total for stable pages.
- **`GET /deals?limit=&memberships=&section=`**: biggest discount at q=1 via `_build_store_offer` (`discount_pct`). An unknown section is 404. There is no fixed threshold: without memberships the catalog tops out at 60%. Cached 10 minutes per membership set (~18.000 offers, ~1 s). The frontend's `DEALS_LIMIT` must not exceed `DEALS_MAX_LIMIT` (422 hides the section).
- **`POST /products/by-ids`** (up to `MAX_PRODUCTS_BY_IDS = 100`, enforced by Pydantic): **an absent id means exactly "pruned"**.
  - It doesn't filter by `in_stock`: nobody stocking a product today is `store_count == 0`, not absence.
  - It takes no dietary filters.
  - Order follows the request, deduped.
  - It **does not fail open to `[]`**: an empty answer would claim every usual product was delisted.
- **`GET /logistics/{coto,dia,carrefour,vea,changomas,jumbo}/coverage`**: thin wrappers for the address onboarding.

**`POST /optimize`:** logistics → flatten (`flatten_cart_prices`: cheapest net cost per line per store at that quantity) → `optimize_cart` (CP-SAT: a bool per (product, store), an active var per store, min spend as a hard constraint, at most one bank promo per store chosen among the user's (each with its cap and its own minimum purchase), minimizing subtotal + delivery − bank discount, plus `MANUAL_CHECKOUT_MARGIN` ($5) per product placed in a store without a cart link, `checkout_domain` None, i.e. Coto) → enrichment. The margin is objective-only: totals are always real. It sends near-ties away from Coto, whose checkout is a checklist of links, and keeps Coto closed when all it offers is near-ties. An infeasible cart is a 400 with a human `detail`.
- **`user_excluded_stores`**: the solver, `price_savings` and swaps get coverage ∪ user exclusions. The response's `excluded_stores` stays **coverage only**, because `LogisticsNotice` and the analytics KPI read it. Unknown ids and excluding every store are 422.
- **Excluding a store is not making it expensive.** A product sold only by an excluded store would turn its constraint into `sum([]) == 1`, a plain "infeasible" blamed on minimum spend. `optimize_cart` detects it first and returns `unavailable_products` with the real cause.
- **`purchase_days`** (1-7, issue #17) lets each store be bought on its best day (`_optimize_purchase_window`):
  - It solves with today's promos, then with every day's promos merged per store, each tagged with its `date`, which comes back as `split[store].purchase_date`.
  - The merged run **wins only if it beats today**, so a tie keeps today instead of a day that makes the user wait.
  - Only bank discounts vary by day. `today_total_spent_net` is set only when the range won.
  - "Today" is `_today_ar()` (UTC−3; Cloud Run runs in UTC).
- **Enrichment** (`_enrich_successful_result`) never changes the split or the total; each feature runs behind `_optional_feature`, so one failure can't take the others:
  - **`price_savings`**: per line, the average of the *other* non-excluded stores minus what's paid, summed net, plus `pct`. Shipping and bank discount are outside it, so it is **not comparable with `total_spent_net`**. There is no "whole cart at each store" baseline.
  - **`suggestions`**: same-shelf embedding neighbours at the **equivalent quantity** (`substitutions.equivalent_quantity()`, within ±10%), offered only if the real line cost is ≥20% lower.
  - **`fewer_stores_options`**: re-solves with `max_stores=k` for each k below the split's store count, reusing `flat_prices` and the winning promos. Each extra checkout is a cost only the user can price, so it is shown, not weighted into the objective. `max_stores` is a hard `sum(y) <= k` (1..N), forwarded to swaps, and named in the infeasible message.
  - **`strategic_swaps`** (stage 7), and a VTEX cart-by-URL "magic link" (`generate_vtex_magic_link`, built from `store_item_id`, never `store_sku`).
- **Paying server-side with stored store sessions was rejected**: it needs the user's passwords, a DB leak becomes purchases, and captchas/3DS break it. The magic link uses the session already in the user's browser.

### 7. Store-closure heuristic (`src/strategic_swaps.py`)

CP-SAT can't change the cart, so one cheap store-exclusive product forces that store open and its minimum drags the rest of the cart in. `find_strategic_swaps()` finds each active store's **anchors** (products no other non-excluded store sells), pulls same-shelf replacements, and re-solves with that store excluded. `strategic_swaps` is always present on success; `[]` is normal.

- **The what-if calls `optimize_cart()`; never hand-roll the cost.** A second arithmetic beside the solver's integer cents is a guaranteed silent mismatch. Pass `flat_prices=` **filtered to that cart's UIDs**: a stray UID becomes a phantom product.
- **A store with zero anchors is skipped without a query**: closing it was already a point the solver rejected. Test anchors, not split size: a **single-store split** is the worst case (a $1.550 vinegar dragged 15 alfajores into Carrefour's minimum).
- **Anchors are computed against non-excluded stores**, not active ones: closing a store can switch another on.
- **Replacements are strict**: same shelf, compatible unit, weight 0,5x-2x. Otherwise the heuristic "saves" by shrinking the cart. The simulation prices real cost, never per-gram. All-or-nothing per store, fail-open.
- **No duplicated `unified_id`** (a candidate already in the cart, or one replacement for two anchors): the flattener reads the last occurrence and the solver the first, so the cost would match no real cart.
- Candidates are priced at the **anchor's quantity**, one flatten call per distinct quantity, because conditional promos unlock above a threshold.
- **Candidates come from one query** (`substitutions.comparable_candidates`, `CROSS JOIN LATERAL`, `LIMIT` per anchor), shared with `suggestions`. One query per anchor cost ~12 round trips (0,6 s → 0,13 s, same candidates).
- **Multipacks are compared, never multiplied** (`extract_pack_count()` gates six-packs against six-packs). The number beside `xN` is sometimes the total and sometimes per unit, and inflating the weight makes a product look cheap.

### 8. Bank discounts (`src/promotions/`, `src/bank_promos.py`)

Offline pipeline writing `src/scrapers/bank_promos.json`: store-wide card/wallet discounts, not tied to products.

- **`DiscountScraper.scrape()` is a fixed template method** (fetch → iterate → translate → validate → dedupe → report). Subclasses implement `_fetch_raw`, `_iter_raw_promos` and `_to_discount`; discards are counted centrally (`self.discards`). `BankDiscount` is frozen and validates itself; an invalid record is dropped, never repaired.
- **Transports:**
  - Coto: `httpx` on `getPromocionesMulticanal`, public, no token.
  - Vea: Master Data `JN/bankDiscount`, a JSON *string* shared with Jumbo/Disco. Day `"6"` is Saturday **and** Sunday. The bank comes from `banks[].name` only. Promos with an exclusion list ("NO INCLUYE … CARNES, LECHES": CencoPay's 20%, Amex Platinum) are discarded, which is why CencoPay left the selector.
  - Jumbo: the same entity, `JumboScraper(VeaScraper)` with `WEBSITE = "jumboargentina"`. Its unknown entities are regional newspaper clubs and in-store promos, rightly discarded.
  - ChangoMás: GDN's content service, `gdn-services/content/banks-promotions` + `financing-banks` (bank `id → name`), public. Online = `ecommerce` or `express_ecommerce_all`; almost everything is in-store, and in Nov 2026 no online promo was live, so `MIN_EXPECTED_DISCOUNTS = 0` (an empty block is normal, not a failure). Promos with an explicit exclusion list ("NO INCLUYE: … aceites, harinas, leches") are discarded. `isMasClub` → `masclub`, a membership; its UI option is added only once a promo lands in the JSON (`test_promos.py`).
  - Día, Carrefour: `PlaywrightScraper`, importing playwright lazily so the API runs without Chromium.
- **Coto's bank identity comes from the logo filename** (`logo_naranjax2.png`), so `banks.py`'s alias boundary blocks letters but allows digits.
- **Día:** days come from clicking the day tabs. Its "Ver Legales" modal must be open → read → close. **The card face is an image** (the DOM only says "ONLINE / TIENDAS / Ver Legales"), so `card_ocr.py` reads it with Tesseract (green channel + threshold; 12/12 cards in Nov 2026). Percentage and cap come from the card first, the legal is the fallback: some legals never state the % (MODO, BNA+), and Naranja X publishes one card per plan sharing one legal that lists all three, which used to yield 30% with the 20% plan's cap. Pillow is imported inside `read_card()`, like Playwright: the API imports `src.promotions` and its image has no Pillow (a top-level import crashed the 18-Nov deploy). Without Tesseract it logs and falls back to the legal; **an entity missing from the JSON may be unreadable, not discount-less** — check the discards before dropping its option.
- **Carrefour:** the big number on financing cards is the installment count, so financing is filtered before reading it. Only `logoOnline` cards apply online. Promos only for over-60s or ANSES beneficiaries are discarded ("VÁLIDO CON MI CARREFOUR PARA MAYORES DE 60 AÑOS O ANSES" used to load as a 10% for every Mi Carrefour member; the profile doesn't know the user's age). The scraper reads `/promociones-bancarias`; the home now links to `/descuentos-bancarios`, which also exists.
- **Minimum purchase** ("en compras iguales o superiores a $100.000", MODO in Vea/Jumbo/Día): `BankDiscount.compra_minima`, read by `extract_min_purchase()` in the Vea/Jumbo, ChangoMás, Día and Carrefour scrapers, travels as `min_purchase` and is a solver constraint: the promo only applies if that store's **product** subtotal (without shipping, the conservative side) reaches it, so the solver can move products to unlock it. A text that mentions a minimum without a readable amount is still discarded (`monto minimo ilegible`). Several amounts → the **highest**, the reverse of caps, for the same reason. The loader also emits `title` ("20% de descuento con MODO") and `conditions` ("Tope $25.000 por mes · compra mínima $100.000"), which `bank_discount` carries to `StoreBreakdownCard`: title and amount on one row, conditions below in small grey. One string put the cap next to the applied amount and read as "you have $X left".
- **`legal_parser.py` rules**, each learned from a real text:
  - a cap is read only after a tope word;
  - worked examples are stripped first;
  - ties take the lower cap;
  - `parse_money_ars` reads `.` as a thousands separator, the opposite of `coto_logistics.parse_amount`;
  - `strict` percentages, so "CFT 0%" isn't a discount.
- **`load_bank_promos(day)` filters by weekday** (CP-SAT has no calendar) keeps **one promo per entity: the lowest tier** (lowest %, then lowest cap), and sorts by descending % (stable output only: `optimize_cart` lets every promo the user holds compete and uses the one that saves most). Several promos of one entity on one day at one store are plans or segments (Naranja X 20/25/30%, Patagonia 15-35%) and the profile can't say which one the user has: quoting the top one promised 30% to plan-inicial users. A missing or corrupt file gives `FALLBACK_BANK_PROMOS`, which is **empty**: never invent a discount. An empty day returns `{}`.
- **The UI offers exactly the entities with a discount in `bank_promos.json`, plus `mi_carrefour`** (its member price moves product prices), enforced both ways by `tests/test_promos.py`. Half the banks (Galicia, Santander, BBVA, MODO…) only had installments: ticking them changed nothing. `banks.py` still recognizes them, so **regenerating the JSON can make that test fail**: add or remove the option in `frontend/src/utils/paymentOptions.js` (`CARD_OPTIONS`/`MEMBERSHIP_OPTIONS`, `{value, label}`) in the same commit. The optimizer compares slugs by equality, and labels must equal `display_name(value)`. `ProfileContext` drops saved cards/memberships that are no longer offered. `MEMBERSHIP_ENTITIES` decides `is_membership` (it travels in `user_memberships`, not `user_cards`).

### 9. Analytics emitter (`src/analytics.py`)

One `cart_optimized` event per optimization to **SmartCart Performance Analyzer** (`../SmartCart Performance Analyzer`; production: Cloud Run `smartcart-analytics` + database `smartcart_analytics` in the same Neon project; dev: `:5433`/`:8001`). `build_cart_optimized_event()` forwards, computes nothing; aggregates are the analyzer's job.

- **Analytics can neither break nor slow `/optimize`**: a `BackgroundTask` with a 2 s timeout, try/except, log only.
- **`BackgroundTasks` don't survive a `raise HTTPException`**, so the infeasible branch **returns `JSONResponse(status_code=400, content={"detail": msg})`**. It is byte-identical on the wire; a `raise` would silently drop every infeasible event (the friction KPI). The engine-failure 500 deliberately emits nothing.
- **Config comes from `.env` via `load_dotenv()`** (exported vars still win). `uvicorn --reload` reloads code, not the environment. Without `ANALYTICS_API_KEY` nothing is emitted, which looks healthy, so `analytics_status()`/`check_analyzer_health()` report it in `lifespan` and `GET /`.
- Unknown keys ride along (the analyzer keeps `raw_payload`). The frontend adds `anon_user_id` (minted in `ProfileContext`, key not versioned) and `zone`.

### 10. Unattended operation (`src/scripts/orchestrator.py`, `.github/workflows/`)

Adds only operations concerns around `run_scrapers.py`. Details and commands in `docs/operacion.md`.

**Telemetry and status:**
- **Telemetry rows open as `RUNNING` before the work** and update on exit (`ScraperTelemetry.step()`, one row per store + embeddings, shared `run_id`). A killed run leaves a stranded `RUNNING` row instead of nothing. `start_time` comes from Python. The writer is fail-open on its own connection.
- **Status:** `SUCCESS` = every category OK and the prune not aborted. `PARTIAL` = some category OK plus a failed one, an empty one, or a skipped prune. `FAILED` = none OK. A skipped prune is PARTIAL because its brakes only fire on a broken scraper.
- **An empty category is PARTIAL, not an error**: it's what a dead key looks like (stage 1b). Names go in `error_message`, count in `categories_empty`. It doesn't raise, so one empty aisle doesn't cost the store its prune.
- **`save_store_products()` raises and returns the row count.** Its old `except` hid lost batches and let the run prune against SKUs that never landed.
- **Logs:** `logs/orchestrator_YYYYMMDD.log` plus a retention sweep, not `TimedRotatingFileHandler` (it only rotates in a process alive at midnight). A filter stamps `run_id` on every record.
- **Exit codes are the monitoring contract:** `0` all SUCCESS · `1` any PARTIAL/FAILED · `2` startup failure (no DB, so no telemetry) · `143` SIGTERM (closes the open telemetry row).

**The sweep on Actions:**
- **GitHub Actions against Neon.** WSL2 cron never fired; AWS has no free tier for new accounts; Oracle never delivered capacity (A1 Always Free was halved to 2 OCPU/12 GB on 15-Jun-2026).
- **The nightly path has no bash**: `workflow_dispatch` takes one free-text `args` input passed through `env` (never `${{ }}` inside `run`, which becomes code). The one branch is the `DATABASE_URL` presence check.
- **Torch from PyTorch's CPU index**, here and in the `Dockerfile`: PyPI's wheel brings CUDA, which filled the runner's disk (26-27 Sep 2026: red job, no telemetry) and made the image 10,3 GB instead of 2,78. The workflow file is part of the pip cache key.
- **The sweep takes ~1 h 15 min** (Día/Vea ~45 min, Coto/Carrefour ~1 h 10 min, ChangoMás and Jumbo not yet measured on Actions; parallel matrix). **The schedule is not the start time**: on `0 6` runs were on time until 20 Oct 2026, then GitHub's delay grew to ~9 h. On 18 Nov the cron moved off the hour (`23 5`). If it stays late, trigger `workflow_dispatch` from Cloud Scheduler.
- **`keepalive.yml`**: GitHub disables schedules after 60 days without commits, and scheduled runs don't count.
- **`bank-promos.yml`** (Mondays) regenerates `bank_promos.json` and opens/updates the PR `promos-bancarias-semanal` only when a promo changed (ignoring `scraped_at`), with an in/out table and the promo tests' result (a `GITHUB_TOKEN` PR doesn't trigger `ci.yml`). It never commits to main: a misread page would be an invented discount. Merging still needs a Cloud Run redeploy; the repo must allow Actions to create PRs.
- **`ops/probe_endpoints.py` is the gate for every new place the sweep runs**: JSON content type and expected shape, never just 200. It imports nothing from `src/`.

**Hosting and limits:**
- **No backups, by design**: the catalog is derived, user data lives in `localStorage`, so moving hosts is a `DATABASE_URL` edit and one sweep. **Exception: the analytics warehouse** is not derived and must be moved or copied.
- **Demo: API on Cloud Run, frontend on Vercel, DB on Neon.**
  - The API peaks at 413 MB, which rules out Render (0,1 CPU), Koyeb and Hugging Face Spaces (Docker now paid).
  - `CMD` honours `$PORT` in shell form; the model downloads at build time, since cold start is the normal case.
  - No spend cap: `--max-instances 3` + a budget alert.
  - Dropping torch for ONNX at runtime (it only encodes the `/search` query) would shrink image and RSS, gated on measuring cold start first.
- **Cloud Run `us-east1` and Neon `aws-us-east-1` share a region, and that is load-bearing**: `/optimize` makes ~10 sequential queries, ~100 ms each when Neon sat in São Paulo (until Nov 2026). The DB moved, not the API, because Cloud Run in São Paulo is Tier 2.
- **`SMARTCART_POOL_MIN_SIZE=0` is required against Neon**: an open connection keeps Neon awake and burns the 100 CU-hours in ~4 days. `SMARTCART_POOL_MAX_IDLE` (60 s) keeps a visit from billing ~15 minutes.
- **Cold start is Cloud Run's** (29,7 s vs 0,25 s warm). Cloud Scheduler `smartcart-warm` hits `GET /` every 10 minutes from 08 to 24 AR. **Never point it at an endpoint that queries the DB**: that keeps Neon awake and spends the month in a week. Actions' cron was too unpunctual for it.
- **CORS is an explicit list** (`CORS_ORIGINS`): `"*"` with credentials is forbidden by the spec.

## Frontend (`frontend/src`)

- **Plain React state** (Context + `useReducer`/`useState`) and native `fetch`; don't add a state or data-fetching library without a concrete reason. Tailwind v4 is CSS-first: tokens in `src/index.css` `@theme`; there is no `tailwind.config.js`.
- **Repeated items with buttons have a fixed height**: cart lines, product cards, history rows, suggestions, checklist rows. Clip text (`line-clamp-2`/`truncate`, full text in `title`), and reserve slots for optional parts. Otherwise the next row's button moves under the cursor. `PriceBlock`'s `fixedSlots` and `QuantityStepper`'s fixed size exist for this.
- **`api/`**: thin wrappers over `apiFetch`/`ApiError`. `optimizeCart()` returns `{ok: false, detail}` on the infeasible 400, which is rendered inline, not as an error.

**Contexts:**
- `CartContext` stores `{unified_id: {name, quantity}}` in `localStorage`.
- `ProfileContext` holds cards, memberships and `location`, and derives `coordinates` (null when skipped).
- **The delivery zone is derived, never asked.** `deliveryCosts.js`'s `resolveZoneFromAddress()` maps Nominatim's `address` to a zone via `PARTIDO_ZONES` (data: a missing partido is a one-line fix). It handles three shapes: CABA via `state`, GBA via `state_district`, GBA via `city` only. `null` means unknown and falls back to the first zone.
- **The per-zone table is the only source** of Día/Carrefour fallback shipping and of Coto's. `delivery_costs` must carry every store key, because `optimize_cart` indexes it without a default.

**Onboarding:**
- **`LocationModal`**: blocking without `onClose`; dismissable with it (from the Header's `MapPin` and the cart's `AddressField`).
  - It geocodes **on submit only** (Nominatim allows 1 req/s).
  - **One main button, two steps:** "Verificar ubicación" checks every store's coverage and shows in one line which ones don't deliver; the same button then reads "Confirmar ubicación", saves and closes. A store that doesn't deliver is not asked about again: the user can't change where they live, so confirming accepts buying without it. Changing the point (candidate, search, click, drag) goes back to "Verificar"; reopening with a saved address starts at "Confirmar", which just closes.
  - Wheel zoom is on (Leaflet keeps the event, so the modal doesn't scroll). A point picked on the map doesn't recenter, so the user's zoom survives; a search candidate does.
  - It shows **several candidates** to pick from, because duplicate street names would bind the wrong branch.
  - "Seguir sin dirección" stores `{skipped: true}`, distinct from `null` (never onboarded).
  - New profile fields need no key version: old profiles just lack them and get the step.
- **`MembershipModal`** is the second step (`membershipsAsked`), because memberships change grid prices. Every product fetch and `useFlattenedPrice` send them. Editable in the cart and the Header's "Mis clubes".

**Store exclusion and the grid:**
- **Disabled stores** (`excludedStores`) travel as `user_excluded_stores` and leave the catalog. `hiddenStores = unavailableStores ∪ excludedStores` strips offers everywhere a price is shown. Where the *cause* is shown, coverage and user choice stay separate: `CoverageWarning` and the grid notice are coverage-only. The last enabled store is locked.
- **`useProductFilters` is state only**: filtering, sorting, paging and facets come from the backend. Any filter change resets to page 1. `SearchResultsPage` remounts `ResultsView` with a `key` instead of a reset effect. The price slider commits on release.
- **Prices go through `resolveDisplayPrice()`**: the cheapest `promo_unit_price ?? base_price`, and only then `min_price` (list-only; preferring it hid every direct discount).
- `stripUnavailableStores()` nulls `min_price` and `unit_price`, which the backend computed over offers that are no longer listed. `formatUnitPrice()` only formats the backend's `unit_price`.

**Purchase history** (`HistoryContext`, `utils/purchaseHistory.js`): on the home, and on `/carrito` only when the cart is empty.
- Written only on a successful optimize.
- **`smartcart_history_v1` is never bumped**: losing it loses months of signal no user action can rebuild. Tolerate new fields in `normalizeHistory()`.
- **An entry younger than `SESSION_WINDOW_MS` (30 min) is replaced, not appended.** Swaps, undo and re-runs re-optimize, and appending would over-weight the carts the user fiddled with most. The window errs short: splitting one session is visible; merging two destroys one.
- Rejected alternatives:
  - hashing the cart (swaps change it);
  - counting uids once per entry (the entry is what's duplicated);
  - a "ya compré" button (nobody presses it);
  - recording on the checkout-link click (Coto has no link).
- **`MAX_ENTRIES = 20`, trimmed inside `recordPurchase()`**: storage writes swallow quota errors, so an unbounded history would silently stop the cart from persisting.
- Habituales count **purchases, not units**, need ≥2, and are computed before `stripUnavailableStores`. "Repetir" **merges** (`mergeItems`), never overwrites. Delisted products are never purged from history.

**Cart:**
- **Line prices** come from `POST /products/by-ids` in `CartProductsContext`, shared by `CartPage` and `CartDrawer` to avoid a double fetch. It sits between `ProfileProvider` and `HistoryProvider`. It fails open: names and quantities still draw.
- **The estimated subtotal is the sum of displayed prices** (q=1, no shipping, no bank discounts) and its label promises no direction: `/optimize` adds shipping and minimums but also quantity promos and bank discounts, so the total lands above or below. Adding anchor-store shipping was rejected (ignores minimums, drifts further with cards, needs client-side logic). A ceiling read as a bug. It renders only when every line has a price. The header shows "~$X". Label only, no explanatory paragraph (the FAQ has it).
- **Coverage warning** (`useUnavailableCartItems`): reuses `/price-preview` only when `unavailableStores` is non-empty, never mutates the cart, and doesn't flag ids absent from the response (absent = out of stock everywhere).

**Optimize results** (`components/optimize/`):
- `SavingsPanel` shows the total; when the saving is `> 0`, a shelf-tag layout above it: the baseline struck through (`total_spent_net + saving`, same shipping) and a highlighted `%` badge, so the % checks on screen. Without the baseline users compared the % against the estimated subtotal. The saving in pesos and what it compares against live in "Ver de dónde sale": users don't read loose text.
- `MoreOptions` is a closed `<details>` with signed effects: `StrategicSwapCard` (−$X), `FewerStoresCard` (+$X; choosing it sets `profile.maxStores` and re-optimizes) and `SuggestionsList` (`applySwaps` with quantity). The sign keeps "sacá Coto" and "comprá solo en Coto" from reading as contradictory.
- `StoreBreakdownCard` per store. Coto's buy button is a checklist of links: a loop of `window.open` gets blocked from the second window. Coto's shipping reads "Envío (estimado)" on `source == "fallback"`.
- `LogisticsNotice` renders only for stores that `/optimize` found uncovered **and** weren't already in `unavailableStores` when it was requested (`knownUncovered` in `CartPage`): a known store was already announced (onboarding, the grid notice), and repeating it on every run was noise. `ProfileContext` re-checks in the background, per address, every store with no stored verdict (failed onboarding lookup, or a store added after the address was saved), so a "no" reaches the grid before the cart is built.

**Pages:**
- **Mega-menu** (`SectionBar`, in the header on every page): a row of rectangular section buttons from `GET /categories`; hover (mouse) or tap (touch) drops `MegaMenuPanel` with that section's shelves; every click goes to `/categoria/:shelf`. It replaced a "Categorías" button + modal that users didn't find. `sectionIcons.js` maps section names exactly, with a fallback icon.
- **Home:** no demo-cart button (users tapped it repeatedly without reading, then couldn't empty the cart; `/demo-cart` is gone); a muted looping recording of the real app (`frontend/public/como-funciona.mp4`, re-record when the UI changes a lot) as "how it works"; "Mejores descuentos de hoy" in a `ProductCarousel` with a section dropdown fed by `GET /categories`. With a filter chosen the section shows an empty message instead of hiding, or the dropdown would vanish.
- **Product:** `ProductCard` and `ProductPage` share `useProductPricing`, so they never disagree. `ProductPage` uses `/products/by-ids` (absent = "ya no está en el catálogo"), and its description is attributed ("Según Día").
- **FAQ** (`/ayuda`): **no numbers that live elsewhere** (minimums, shipping, percentages). The feedback block hides while `FEEDBACK_FORM_URL` is empty.
- **Routes:** `/`, `/buscar?q=`, `/categoria/:shelf`, `/producto/:unifiedId`, `/ayuda`, `/carrito`.
