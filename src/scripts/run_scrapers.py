"""
Corre todos los scrapers de punta a punta y deja la base lista para usar.

Uso:
    python -m src.scripts.run_scrapers                  # las tres tiendas + embeddings
    python -m src.scripts.run_scrapers --store coto     # solo una tienda
    python -m src.scripts.run_scrapers --skip-embeddings
    python -m src.scripts.run_scrapers --prune-dry-run  # ver qué se borraría
    python -m src.scripts.run_scrapers --no-prune       # no borrar nada

Al terminar cada tienda se borran sus filas obsoletas: las de productos que la
tienda ya no ofrece. Sin eso quedan para siempre con `in_stock = TRUE` y el
optimizador las sigue cotizando. Sólo se poda una tienda que terminó su recorrido
completo, y `SmartCartDB.prune_missing_store_products` aborta si el borrado se
lleva una fracción sospechosa del catálogo.

El paso de embeddings no es opcional en la práctica: los productos nuevos no
aparecen en GET /search hasta tener su name_embedding. Solo conviene saltearlo
si se van a correr las tiendas por separado y generar los embeddings al final,
para no cargar el modelo tres veces.

Requiere Postgres arriba (docker-compose up -d).
"""
import argparse
import sys
import time
import traceback

from src.database import SmartCartDB
from src.scrapers import scraper_carrefour, scraper_coto, scraper_dia


def _run_store(db, store_id, label, categories, scrape, pause) -> tuple[int, set]:
    """
    Recorre las categorías de una tienda y devuelve (productos, SKUs vistos).

    El set de SKUs es lo que después habilita el pruning, y por eso se arma acá y
    no dentro de `save_store_products`: sólo tiene sentido como el universo de un
    recorrido COMPLETO. Si esta función levanta a mitad de camino, el llamador se
    queda sin el set y no poda, que es lo correcto — con un recorrido parcial todo
    lo que faltó ver parece discontinuado.
    """
    total = 0
    seen_skus = set()

    for category in categories:
        print(f"\n=== [{label}] {category} ===")
        products = scrape(category)

        if products:
            db.save_store_products(products, store_id)
            total += len(products)
            seen_skus.update(p["store_sku"] for p in products if p.get("store_sku"))

        time.sleep(pause)

    return total, seen_skus


def run_coto(db: SmartCartDB) -> tuple[int, set]:
    scraper = scraper_coto.CotoScraper()
    return _run_store(db, "coto_online", "COTO", scraper_coto.MVP_CATEGORIES,
                      scraper.scrape_category, 2.0)


def run_dia(db: SmartCartDB) -> tuple[int, set]:
    scraper = scraper_dia.DiaScraper()
    return _run_store(db, "dia_online", "DÍA", scraper_dia.MVP_CATEGORIES,
                      scraper.scrape_entire_category, 3.5)


def run_carrefour(db: SmartCartDB) -> tuple[int, set]:
    scraper = scraper_carrefour.CarrefourScraper()
    return _run_store(db, "carrefour_online", "CARREFOUR", scraper_carrefour.MVP_CATEGORIES,
                      scraper.scrape_entire_category, 3.5)


def main():
    # El scrapeo tarda varios minutos; sin esto Python bufferea la salida al
    # redirigirla a un archivo o un pipe y no se ve el progreso hasta el final.
    sys.stdout.reconfigure(line_buffering=True)

    parser = argparse.ArgumentParser(description="Corre los scrapers de SmartCart.")
    parser.add_argument(
        "--store",
        choices=["coto", "dia", "carrefour", "all"],
        default="all",
        help="Qué tienda scrapear (default: all).",
    )
    parser.add_argument(
        "--skip-embeddings",
        action="store_true",
        help="No regenerar embeddings al terminar.",
    )
    parser.add_argument(
        "--no-prune",
        action="store_true",
        help="No borrar las filas de productos que la tienda ya no ofrece.",
    )
    parser.add_argument(
        "--prune-dry-run",
        action="store_true",
        help="Informar cuántas filas obsoletas se borrarían, sin borrarlas.",
    )
    args = parser.parse_args()

    db = SmartCartDB()
    runners = {
        "coto": (run_coto, "coto_online"),
        "dia": (run_dia, "dia_online"),
        "carrefour": (run_carrefour, "carrefour_online"),
    }
    selected = list(runners) if args.store == "all" else [args.store]

    started = time.time()
    totals = {}
    pruned = {}

    for store in selected:
        runner, store_id = runners[store]
        try:
            totals[store], seen_skus = runner(db)
        except Exception:
            # Una tienda caída no debe tirar abajo el scrapeo de la otra.
            print(f"\n[ERROR] Falló el scrapeo de '{store}':")
            traceback.print_exc()
            totals[store] = None
            # Sin pruning: el recorrido quedó incompleto y lo que no se llegó a
            # ver es indistinguible de lo discontinuado.
            continue

        if not args.no_prune:
            print(f"\n=== [PRUNING] {store} ===")
            pruned[store] = db.prune_missing_store_products(
                store_id, seen_skus, dry_run=args.prune_dry_run
            )

    if not args.skip_embeddings:
        print("\n=== EMBEDDINGS ===")
        try:
            # Import diferido: carga sentence-transformers, que es lento.
            from src.embeddings import EmbeddingPipeline

            EmbeddingPipeline().generate_and_save_embeddings()
        except Exception:
            print("\n[ERROR] Falló la generación de embeddings:")
            traceback.print_exc()

    print("\n" + "=" * 60)
    print("RESUMEN")
    print("=" * 60)
    for store, count in totals.items():
        linea = f"  {store:6} -> {'FALLÓ' if count is None else f'{count} productos'}"
        p = pruned.get(store)
        if p:
            if p["skipped"]:
                linea += f"  | pruning OMITIDO ({p['reason']})"
            else:
                linea += f"  | -{p['deleted']} obsoletas, -{p['orphans']} sin ofertas"
        print(linea)
    print(f"  tiempo -> {time.time() - started:.0f}s")
    print("=" * 60)

    # Exit code distinto de 0 si alguna tienda falló, para que sirva en CI.
    return 1 if any(count is None for count in totals.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
