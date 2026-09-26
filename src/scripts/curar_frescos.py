"""
Herramienta de curado de `src/fresh_items.py`.

Uso:
    python -m src.scripts.curar_frescos
    python -m src.scripts.curar_frescos --shelf frutas --top 3
    python -m src.scripts.curar_frescos --dump frescos.json      # guarda lo bajado
    python -m src.scripts.curar_frescos --from frescos.json      # reusa sin re-scrapear

Baja EN VIVO las góndolas de `FRESH_SHELVES` con los mismos scrapers del barrido
nocturno y reporta dos cosas:

1. **Obsoletos**: SKUs de la tabla que la cadena ya no publica. Es la señal de
   mantenimiento — un SKU dado de baja deja al ítem con una tienda menos sin que
   nada falle, y un reemplazo (mismo producto, SKU nuevo) entra como oferta suelta.
2. **Sin emparejar**: cada producto que no está en la tabla, con sus vecinos más
   cercanos en las otras dos cadenas por embedding. Son CANDIDATOS: el modelo pone
   "ananá" cerca de "nalga", así que decide una persona (ver el docstring de
   `src/fresh_items.py` para las reglas de curado).

Baja en vivo y no lee la base a propósito: curar es decidir sobre lo que las
cadenas venden hoy, y no depende de que el barrido haya corrido ni escribe nada
en ninguna parte. Tarda un par de minutos por las pausas anti-bot de los
scrapers.

Marcas en la salida: `PIEZA` = el nombre declara un peso aproximado o mínimo por
unidad (precio por pieza, no por kilo: no entra a la tabla). `[kg]`/`[un]` = la
unidad de venta leída del nombre, para no emparejar un kilo contra una unidad.
"""
import argparse
import json
import re
import sys
import unicodedata

from sentence_transformers import SentenceTransformer

from src.embeddings import DEFAULT_EMBEDDING_MODEL
from src.fresh_items import FRESH_ITEMS, FRESH_SHELVES
from src.scrapers import scraper_carrefour, scraper_coto, scraper_dia
from src.shelves import SHELVES, STORES

_PIEZA = re.compile(r"peso\s+(aproximado|m[ií]nimo)", re.I)
_KG = re.compile(r"\bx\s*kg\b|\bxkg\b|\bpor\s+kg\b|\bkgm?\b", re.I)
_UN = re.compile(r"\bx\s*(ud|uni|un|u)\b\.?|\bx\s*unidad\b|\bx\s*atado\b", re.I)


def _scrapers():
    return {
        "coto": scraper_coto.CotoScraper().scrape_category,
        "dia": scraper_dia.DiaScraper().scrape_entire_category,
        "carrefour": scraper_carrefour.CarrefourScraper().scrape_entire_category,
    }


def fetch(shelves) -> list[dict]:
    scrape = _scrapers()
    rows = []
    for slug in shelves:
        for store in STORES:
            for key in SHELVES[slug].keys_for(store):
                try:
                    prods = scrape[store](key)
                except Exception as exc:  # noqa: BLE001 — se reporta y se sigue
                    print(f"  ! {store} {key}: {exc!r}", file=sys.stderr)
                    continue
                print(f"  {store:<9} {key}: {len(prods)}", file=sys.stderr)
                rows += [{
                    "shelf": slug, "store": store, "sku": p["store_sku"],
                    "name": p["name"], "price": p["base_price"],
                } for p in prods]
    return rows


def sale_unit(name: str) -> str:
    if _UN.search(name):
        return "un"
    if _KG.search(name):
        return "kg"
    return "?"


def _normalize(name: str) -> str:
    """El texto que se encodea: sin acentos ni la unidad, que no dicen QUÉ es."""
    text = unicodedata.normalize("NFKD", name.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = _KG.sub(" ", _UN.sub(" ", text))
    return " ".join(re.sub(r"[^a-z ]", " ", text).split())


def _label(row: dict) -> str:
    flags = " PIEZA" if _PIEZA.search(row["name"]) else ""
    return f"{row['name']} [{sale_unit(row['name'])}] ${row['price']:,.0f} (sku {row['sku']}){flags}"


def report(rows: list[dict], top: int) -> None:
    seen = {(r["store"], r["sku"]) for r in rows}
    shelves_fetched = {r["shelf"] for r in rows}

    print("\n=== Obsoletos (SKUs de la tabla que la cadena ya no publica) ===")
    stale = [(item.slug, store, sku) for item in FRESH_ITEMS
             if item.shelf in shelves_fetched
             for store, sku in item.skus.items() if (store, sku) not in seen]
    for slug, store, sku in stale:
        print(f"  {slug}: {store} {sku}")
    if not stale:
        print("  (ninguno)")

    curated = {(store, sku) for item in FRESH_ITEMS for store, sku in item.skus.items()}
    model = SentenceTransformer(DEFAULT_EMBEDDING_MODEL)
    vectors = model.encode([_normalize(r["name"]) for r in rows], normalize_embeddings=True)

    print(f"\n=== Sin emparejar (top {top} por cadena, distancia coseno) ===")
    for slug in sorted(shelves_fetched):
        print(f"\n## {slug}")
        for i, row in enumerate(rows):
            if row["shelf"] != slug or (row["store"], row["sku"]) in curated:
                continue
            print(f"- {row['store']}: {_label(row)}")
            for other in STORES:
                if other == row["store"]:
                    continue
                cands = [j for j, r in enumerate(rows) if r["shelf"] == slug and r["store"] == other]
                cands.sort(key=lambda j: -float(vectors[i] @ vectors[j]))
                for j in cands[:top]:
                    dist = 1 - float(vectors[i] @ vectors[j])
                    print(f"    {other:<9} {dist:.2f}  {_label(rows[j])}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--shelf", choices=FRESH_SHELVES, action="append",
                        help="limitar a una góndola (repetible); por defecto, las cuatro")
    parser.add_argument("--top", type=int, default=2, help="candidatos por cadena")
    parser.add_argument("--dump", help="guardar lo bajado en este JSON")
    parser.add_argument("--from", dest="source", help="leer de un JSON de --dump en vez de scrapear")
    args = parser.parse_args()

    shelves = args.shelf or list(FRESH_SHELVES)
    if args.source:
        with open(args.source, encoding="utf-8") as fh:
            rows = [r for r in json.load(fh) if r["shelf"] in shelves]
    else:
        rows = fetch(shelves)
    if args.dump:
        with open(args.dump, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, ensure_ascii=False, indent=1)
    report(rows, args.top)


if __name__ == "__main__":
    main()
