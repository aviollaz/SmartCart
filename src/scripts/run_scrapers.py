"""
Corre todos los scrapers de punta a punta y deja la base lista para usar.

Uso:
    python -m src.scripts.run_scrapers                  # ambas tiendas + embeddings
    python -m src.scripts.run_scrapers --store coto     # solo una tienda
    python -m src.scripts.run_scrapers --skip-embeddings

El paso de embeddings no es opcional en la práctica: los productos nuevos no
aparecen en GET /search hasta tener su name_embedding. Solo conviene saltearlo
si se van a correr las dos tiendas por separado y generar los embeddings al
final, para no cargar el modelo dos veces.

Requiere Postgres arriba (docker-compose up -d).
"""
import argparse
import sys
import time
import traceback

from src.database import SmartCartDB
from src.scrapers import scraper_coto, scraper_dia


def run_coto(db: SmartCartDB) -> int:
    scraper = scraper_coto.CotoScraper()
    total = 0

    for category_id in scraper_coto.MVP_CATEGORIES:
        print(f"\n=== [COTO] {category_id} ===")
        products = scraper.scrape_category(category_id)

        if products:
            db.save_store_products(products, "coto_online")
            total += len(products)

        time.sleep(2.0)

    return total


def run_dia(db: SmartCartDB) -> int:
    scraper = scraper_dia.DiaScraper()
    total = 0

    for category_query in scraper_dia.MVP_CATEGORIES:
        print(f"\n=== [DÍA] {category_query} ===")
        products = scraper.scrape_entire_category(category_query)

        if products:
            db.save_store_products(products, "dia_online")
            total += len(products)

        time.sleep(3.5)

    return total


def main():
    # El scrapeo tarda varios minutos; sin esto Python bufferea la salida al
    # redirigirla a un archivo o un pipe y no se ve el progreso hasta el final.
    sys.stdout.reconfigure(line_buffering=True)

    parser = argparse.ArgumentParser(description="Corre los scrapers de SmartCart.")
    parser.add_argument(
        "--store",
        choices=["coto", "dia", "all"],
        default="all",
        help="Qué tienda scrapear (default: all).",
    )
    parser.add_argument(
        "--skip-embeddings",
        action="store_true",
        help="No regenerar embeddings al terminar.",
    )
    args = parser.parse_args()

    db = SmartCartDB()
    runners = {"coto": run_coto, "dia": run_dia}
    selected = list(runners) if args.store == "all" else [args.store]

    started = time.time()
    totals = {}

    for store in selected:
        try:
            totals[store] = runners[store](db)
        except Exception:
            # Una tienda caída no debe tirar abajo el scrapeo de la otra.
            print(f"\n[ERROR] Falló el scrapeo de '{store}':")
            traceback.print_exc()
            totals[store] = None

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
        print(f"  {store:6} -> {'FALLÓ' if count is None else f'{count} productos'}")
    print(f"  tiempo -> {time.time() - started:.0f}s")
    print("=" * 60)

    # Exit code distinto de 0 si alguna tienda falló, para que sirva en CI.
    return 1 if any(count is None for count in totals.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
