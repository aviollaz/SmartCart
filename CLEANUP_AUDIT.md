# Cleanup audit

Read-only audit of the repo for unused files, duplicated logic, and files that overlap in
purpose. No source was modified to produce this report. Branch: `cleanup` (off `main`).

Every finding below was cross-checked against `CLAUDE.md` first — it documents a number of
things that *look* like duplication but are deliberate (e.g. `run_scrapers.py` vs
`orchestrator.py` sharing `STORE_RUNNERS`, `test_optimizer.py` vs
`test_optimizer_correctness.py`, `EstimatedSubtotal`'s client-side estimate vs the real
`/optimize` total, the Oracle-VM ops docs existing alongside GitHub Actions). Those are listed
at the bottom as "ruled out," not repeated as findings.

Ordered by impact vs. risk, highest first.

---

## 1. `AGENTS.md` describes a retired architecture (high impact, ~zero risk)

- **Category**: overlapping purpose — stale fork of `CLAUDE.md`
- **File**: `AGENTS.md` (70 lines, read by Codex CLI the way `CLAUDE.md` is read by Claude Code)
- **How verified**: read in full and diffed conceptually against `CLAUDE.md`. It describes:
  Coto+Día only, no Carrefour (line 7); `src/category_tree.py`, `CATEGORY_MAP`, and
  `GET /categories/tree` as live (lines 50-58); `BaselineComparison.jsx` (line 69);
  `tests/test_category_tree.py` (line 30). Verified each is gone:
  - `git ls-files | grep -i category_tree` → no hits (file doesn't exist).
  - `grep -rn "CATEGORY_MAP" src/ tests/` → only hit is `src/taxonomy.py:19`, itself saying
    *"Ese dict tampoco existe más"* (that dict doesn't exist anymore either).
  - `grep -rln "BaselineComparison" frontend/src/` → no hits.
  - `git ls-files | grep test_category_tree` → no hits.
  - `docs/smartcart_spec.md` §2.1 independently confirms `GET /categories/tree` and
    `has_direct_category_match` were removed and replaced by `src/shelves.py` +
    `GET /category/{slug}`.
- **Confidence**: high.
- **Risk of changing**: low. It's documentation, not code — nothing imports or parses it. The
  only real risk is scope: if AV doesn't use Codex, deleting it is safe; if Codex is still used
  for this repo, it needs a content resync with `CLAUDE.md` (or a pointer to it), not deletion,
  since Codex reads `AGENTS.md` by filename convention and won't pick up `CLAUDE.md` on its own.
- **Impact**: it currently actively misleads — anyone (human or agent) using it would edit
  `src/category_tree.py` (deleted), reference a 4-bucket `category` column (deleted), or assume
  only 2 stores are supported. This is the single highest-value item in the whole audit: no code
  risk, and it's actively wrong today.

## 2. `src/scrapers/utils.py` is fully dead code (high impact, zero risk)

- **Category**: unused file
- **File**: `src/scrapers/utils.py` (158 lines) — `parse_coto_promotion()` (7-57),
  `parse_dia_product_and_promos()` (63-158)
- **How verified**:
  - `grep -rn "parse_coto_promotion|parse_dia_product_and_promos"` across the repo → only the
    file's own `def` lines.
  - `grep -rn "scrapers\.utils|scrapers import utils|import utils"` in `src/` → no hits.
  - `git log --oneline -- src/scrapers/utils.py` → one commit, `6636d3e "added promotion parser
    and tests"` — the same commit that introduced `src/promotion_parser.py`. This file is an
    early draft of promo parsing, immediately superseded by `PromoTransformer.coto()`/`.dia()`
    and never deleted. (Its own `clean_price()` only handles comma-decimals; the real one in
    `promotion_parser.py` handles the thousands/decimal ambiguity correctly — a second, worse
    implementation of the same function sitting unused.)
- **Confidence**: high.
- **Risk of removing**: none — zero importers, no `__main__` block, not named anywhere in
  `CLAUDE.md`/`README.md`/`AGENTS.md`/`docs/`.
- **Impact**: removes 158 lines of dead code that could be mistaken for the live promo parser.

## 3. `scraper_dia.py` / `scraper_carrefour.py`: ~80 lines of copy-pasted VTEX offer parsing (medium-high impact, low-medium risk)

- **Category**: duplicated logic
- **Files**: `src/scrapers/scraper_dia.py:102-171` (`process_products`, up through the
  volume/unit block) vs `src/scrapers/scraper_carrefour.py:139-199`
- **How verified**: read both functions in full. `src/scrapers/vtex.py` already extracts the two
  pieces CLAUDE.md documents as shared (`extract_search_payload()`, `read_availability()`), but
  the size/price/dietary-parsing block after that was never factored out — and Carrefour's own
  comments say *"Igual que en Día"* (same as in Día), acknowledging the duplication without
  removing it. Near-identical or byte-identical blocks:
  - sellers/`base_price` extraction (dia 119-130 / carrefour ~157-161)
  - `PrecioPorUnd`/`UnidaddeMedida` properties loop (dia 132-140 / carrefour ~167-171)
  - `extract_real_volume` fallback + magnitude branches + `normalize_magnitude()` call (dia
    142-171 / carrefour ~173-199 — ~30 lines, essentially line-for-line identical incl. comments)
  - `image_url` extraction, `dietary_sources` construction (same pattern both files)
- **Confidence**: high that it's duplicated; medium on the clean extraction shape — the two
  callers differ only in URL-building (`p.get("link")` vs `build_carrefour_url()`) and the
  `raw_promos` default (`[]` vs `{}`), so a shared `parse_vtex_offer(p, first_item, sellers,
  shelf, taxonomy_path, source_category, url)` in `vtex.py` looks viable.
- **Risk of changing**: low-medium. Covered by `tests/test_scraper_ingest_keys.py`,
  `tests/test_carrefour_scraper.py`, `tests/test_scraper_truncation.py`, so there's a real
  regression net — but a careless merge could drop a store-specific comment documenting a real
  gotcha (e.g. the dietary-flags false-positive rationale), or silently change the `raw_promos`
  default type.
- **Impact**: collapses ~70-90 duplicated lines into one shared helper, and closes the exact
  "fix lands in one store's copy, not the other" risk `CLAUDE.md` warns about elsewhere (stage
  10, re: keeping `run_scrapers.py`/`orchestrator.py` in sync).

## 4. `ClearCartButton.jsx` / `ClearHistoryButton.jsx`: near-identical component (medium impact, low risk)

- **Category**: duplicated logic / near-identical component
- **Files**: `frontend/src/components/cart/ClearCartButton.jsx` (71 lines, confirm-UI at
  ~15-71) vs `frontend/src/components/history/ClearHistoryButton.jsx` (72 lines, ~18-72)
- **How verified**: read both in full. Same two-step inline-confirm pattern (button → "Sí, X" /
  "Cancelar"), identical `containerRef`/`handleBlur`/Escape-key wiring, identical Tailwind
  classes, identical singular/plural branching. Differences are only the data source (`useCart()`
  vs `useHistory()`), the counted field, and four string literals.
  `ClearHistoryButton.jsx`'s own docstring says *"Misma forma que ClearCartButton"* — the
  duplication is acknowledged in the code itself.
- **Confidence**: high.
- **Risk of changing**: low — purely presentational, no external state contract. Main risk is
  keeping the Spanish copy correctly parameterized ("el único producto" vs "la única compra
  guardada" are different nouns, not just counts).
- **Impact**: removes ~45 duplicated lines and centralizes the confirm-button UX so a future a11y
  or interaction fix lands once instead of twice (a generic `ConfirmClearButton({count,
  singularLabel, pluralLabel, confirmLabel, onConfirm, className})`).

## 5. `run_scrapers.py` / `orchestrator.py`: small duplicated prune-decision block (low-medium impact, low risk)

- **Category**: duplicated logic (small)
- **Files**: `src/scripts/run_scrapers.py:269-285` (in `main()`) vs
  `src/scripts/orchestrator.py:222-254` (`_maybe_prune()`)
- **How verified**: read both. Both independently encode "skip pruning if `result.ok_categories`
  is empty, else call `db.prune_missing_store_products(store_id, seen_skus, dry_run=...,
  categories=result.prune_scope)`." `orchestrator.py`'s own module docstring explicitly frames
  the sweep loop itself as correctly shared via `STORE_RUNNERS` specifically to avoid this kind
  of silent drift — but this small block wasn't included in that sharing. The two versions
  already express the "was this a full sweep" check two different ways
  (`run_scrapers.py:271` tests `not result.complete`-equivalent via `ok_categories`,
  `orchestrator.py:240` tests `result.prune_scope is None`) — equivalent today only because
  `prune_scope` (`run_scrapers.py:84-101`) is itself defined in terms of `complete`.
- **Confidence**: medium — real duplication, but small, and the two call sites have different
  side effects around it (one builds a CLI summary dict, the other populates telemetry fields).
- **Risk of changing**: low — both paths are covered by `tests/test_pruning.py` and
  `tests/test_orchestrator.py`.
- **Impact**: small (~15-20 lines could become one shared helper), worth doing mainly to remove
  the risk of the two conditions drifting apart, not for line count.

## 6. `frontend/src/hooks/useDebouncedValue.js` is unused (low impact, zero risk)

- **Category**: unused file
- **File**: `frontend/src/hooks/useDebouncedValue.js` (12 lines, single export)
- **How verified**: `grep -rn "useDebouncedValue" frontend/src` → only the file's own
  `export function` line. A full importer sweep over `frontend/src` found no other file with
  zero importers besides legitimate Vite entry points (`App.jsx`, `main.jsx`, `index.css`).
- **Confidence**: high.
- **Risk of removing**: none.
- **Impact**: trivial (12 lines), but it's dead weight that could be mistaken for the project's
  debounce pattern instead of the one actually in use (`useFlattenedPrice.js`'s inline 300ms
  `setTimeout`).

## 7. `src/scripts/backfill_units.py` — likely-finished one-off migration, undocumented (low impact, low risk)

- **Category**: unused-in-spirit file (technically a manual script, so not flagged as dead code
  outright)
- **File**: `src/scripts/backfill_units.py` (41 lines) — recomputes `unit_type`/
  `total_volume_weight` for already-scraped rows via `size_parser.extract_real_volume()`.
- **How verified**: `grep -rn "backfill_units"` → only self-reference. `git log --oneline --
  src/scripts/backfill_units.py` → single commit (`816695f`), never touched since. Unlike every
  other file in `src/scripts/` (`run_scrapers.py`, `orchestrator.py`, `repair_coto_urls.py`,
  `medir_busqueda.py`, `migrate_shelves.py`), it is not named anywhere in `CLAUDE.md`,
  `README.md`, `AGENTS.md`, or `docs/TODO.md` — every sibling script has an explicit paragraph
  explaining why it still matters; this one has none.
- **Confidence**: medium — it fits the "manual script, exempt from the unused-file check"
  pattern, so this is a documentation gap more than dead code. It reads like a migration that
  already did its one job (bulk-fixing historical rows after `size_parser`/`normalize_magnitude`
  landed) and was never cleaned up or written into the docs, unlike `migrate_shelves.py`, which
  `CLAUDE.md` explicitly frames as "run by hand once."
- **Risk of removing**: low — no imports; `git log` recovers it if ever needed again.
- **Impact**: minor (41 lines), mostly reduces "what does this undocumented script do" friction
  for a future maintainer.

## 8. `frontend/src/utils/formatters.js` vs `ProductCard.jsx`: repeated one-line price formula (low impact, low risk)

- **Category**: duplicated logic (small)
- **Files**: `frontend/src/utils/formatters.js:117` (inside `resolveBestOffer`) vs
  `frontend/src/components/plp/ProductCard.jsx:72` (inside the local `StoreBreakdown`
  sub-component)
- **How verified**: `grep -rn "promo_unit_price\|base_price" frontend/src` → the formula
  `offer.promo_unit_price ?? offer.base_price` appears identically in both files. Read both call
  sites: `formatters.js` uses it to pick the single cheapest offer; `ProductCard.jsx` uses the
  same formula inline, per-offer, to render every store's net price side by side.
- **Confidence**: medium — same formula, but genuinely different purposes (pick-the-best vs.
  render-all), so it's a repeated inline expression, not a duplicated function.
- **Risk of changing**: low — extracting `netOfferPrice(offer)` into `formatters.js` and
  importing it is mechanical.
- **Impact**: small; guards against the two sites drifting if the net-price rule ever changes.

## 9. Shared fetch-hook skeleton across 3-4 frontend data hooks (medium impact, medium risk — flagged, not recommended as a first cut)

- **Category**: duplicated logic
- **Files**: `frontend/src/hooks/useCartProducts.js:27-74`,
  `frontend/src/hooks/useHabitualProducts.js:20-73`,
  `frontend/src/hooks/useUnavailableCartItems.js:28-72`, and partially
  `frontend/src/hooks/useFlattenedPrice.js:24-67`
- **How verified**: read all four in full. `useCartProducts` and `useHabitualProducts` share a
  near-identical shape (stable key from object keys, `useEffect` with a `cancelled` flag, fetch,
  fail-open `catch` with `console.warn`) — `useCartProducts`'s own docstring says *"Mismo patrón
  que useHabitualProducts, y por el mismo motivo."* `useUnavailableCartItems` repeats the same
  skeleton against a different endpoint; `useFlattenedPrice` adds its own debounce/cache layer on
  top of it.
- **Confidence**: medium. The boilerplate is genuinely repeated, but each hook's payload logic
  differs meaningfully — `useCartProducts` sorts ids (order not meaningful) and returns a dict;
  `useHabitualProducts` *preserves* id order (order is the ranking) and tracks `missing`
  separately; `useUnavailableCartItems` derives a filtered list from a different response shape.
  A literal merge would be awkward; a shared "cancellable-fetch-on-key-change" micro-utility is
  plausible but non-trivial to get right without subtly changing one hook's semantics.
- **Risk of changing**: medium — touches the cart page, home page habituales section, and the
  coverage warning; a careless extraction could reintroduce exactly the bugs the hooks' own
  comments warn against (losing habituales' order-as-ranking, or marking a product "unavailable"
  when it's just out of stock today).
- **Impact**: ~30-40 lines of boilerplate removable across 3 files, but the win is future
  maintainability more than current dead weight. Given the risk, this is a "ticket," not a quick
  edit — lowest priority of the real findings.

---

## Ruled out — already justified in `CLAUDE.md` or verified deliberate (not findings)

**Backend:**
- `run_scrapers.py` vs `orchestrator.py` sharing `STORE_RUNNERS`/`build_arg_parser()` — confirmed
  real and correctly shared (see finding 5 above for the one small gap that fell outside it).
- `src/scrapers/vtex.py`'s `extract_search_payload()`/`read_availability()` — genuinely shared
  between Día and Carrefour, exactly as documented.
- `src/substitutions.py`'s helpers — confirmed shared between `api.py`'s smart-replacement
  suggestions and `strategic_swaps.py`'s anchor lookup.
- `src/flattener.py`'s `evaluate_best_promo()` — single canonical promo-math implementation,
  used by both the optimizer and the catalog endpoints, as documented.
- `size_parser.py`'s `normalize_magnitude()`/`extract_real_volume()` — already internally
  deduplicated; no competing parser in `database.py`.
- `test_optimizer.py` vs `test_optimizer_correctness.py` — matches `CLAUDE.md`'s explanation
  (vacuous/integration vs. deterministic/oracle-based).
- `get_bank_promos.py`, `get_{coto,dia,carrefour}_categories.py`, `migrate_shelves.py`,
  `repair_coto_urls.py`, `medir_busqueda.py` — confirmed documented, independently-invoked
  manual entry points.
- `src/promotions/*` package — clean import graph; `CotoScraper`/`DiaScraper`/`CarrefourScraper`
  correctly share `DiscountScraper`/`PlaywrightScraper` as documented.
- `src/scrapers/http_retry.py` — single shared retry implementation, no ad hoc retry loops found
  elsewhere.
- Oracle-VM ops docs vs GitHub Actions path — explicitly two deployments in deliberate, dated
  parallel per `CLAUDE.md` stage 10.
- One stale in-code comment (not a real finding): `src/strategic_swaps.py:29-31`'s docstring
  claims `bank_promos` is duplicated in `optimizer.py`, `api.py` *and*
  `test_optimizer_correctness.py` — `api.py` doesn't actually reference it (`grep` for
  `BANK_PROMOS|bank_promos` in `src/api.py` returns nothing). The real single source is
  `src/bank_promos.py`'s `FALLBACK_BANK_PROMOS`, mirrored only in the one test file, matching
  `CLAUDE.md` stage 8. Worth a one-line comment fix if anyone touches that file; not worth a
  standalone change.

**Frontend:**
- `EstimatedSubtotal.jsx`/`CartProductsContext.jsx` recomputing a cart total independently of
  `/optimize` — explicitly deliberate (floor estimate, not the real total); it correctly reuses
  `resolveDisplayPrice()` from `formatters.js` rather than reimplementing price math.
- `LocationModal.jsx` in blocking-onboarding vs. dismissable-change-address mode — confirmed a
  single component gated by the `onClose` prop, not two, exactly as documented.
- `api/geocoding.js` using raw `fetch` instead of `api/client.js`'s `apiFetch` — targets an
  external host (Nominatim), not the backend, so `apiFetch` doesn't apply.
- `api/categories.js`, `api/logistics.js`, `api/prices.js` — the documented, deliberate
  "thin wrapper per resource" convention, not fragmentation.
- `stripUnavailableStores` nulling `min_price`/`unit_price` — documented behavior, not a bug.
- `CartContext` vs `CartProductsContext` — out of scope per `CLAUDE.md`'s explanation of the
  layering.
- Megamenu components (`MegaMenu`/`MegaMenuPanel`/`MegaMenuRail`) — clean composition, distinct
  sub-widgets, no overlap.
- `PurchaseHistorySection`/`HabitualesGrid`/`RecentCartsList`/`RecentCartCard`/
  `StoreBreakdownCard` — each has a genuinely distinct data shape and purpose despite similar
  naming.
- `cartOperations.js` (`applySwaps`, `mergeItems`) — pure, no duplication found elsewhere.

**Docs (found during this synthesis, not by either subagent):**
- `docs/smartcart_spec.md` §1-2 (the original "Roadmap de Implementación" table) describes an
  earlier plan — Coto+Día only, Streamlit frontend (Fase 4) — that no longer matches reality
  (3 stores, React frontend). Unlike `AGENTS.md`, the rest of the same file (§2.1 onward) *was*
  kept current (shelves, dietary flags, data model). This reads like an intentionally-preserved
  historical roadmap section sitting above the still-current spec, rather than an oversight —
  low-confidence finding, flagged for AV to confirm intent rather than acted on here.
- `README.md`'s "Dónde corre" table lists only the local dev setup and doesn't mention the public
  Cloud Run/Vercel demo `CLAUDE.md` and `ops/demo-publica.md` describe — but it does link to
  `ops/README.md` for "the detail," which does cover it. A documentation gap, not duplication;
  not flagged as a finding.

---

## Suggested order of operations, if AV wants to act on this

1. Resync or delete `AGENTS.md` (#1) — zero code risk, highest clarity win.
2. Delete `src/scrapers/utils.py` (#2) and `frontend/src/hooks/useDebouncedValue.js` (#6) —
   zero risk, free.
3. Merge `ClearCartButton`/`ClearHistoryButton` (#4) — low risk, clear win.
4. Extract the shared VTEX offer-parsing block from `scraper_dia.py`/`scraper_carrefour.py` (#3)
   — real payoff, but budget time for the regression-test pass.
5. Everything else (#5, #7, #8, #9) is optional polish — worth doing opportunistically, not worth
   a dedicated pass on its own.
