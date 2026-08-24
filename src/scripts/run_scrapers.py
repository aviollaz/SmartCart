"""
Corre todos los scrapers de punta a punta y deja la base lista para usar.

Uso:
    python -m src.scripts.run_scrapers                  # las tres tiendas + embeddings
    python -m src.scripts.run_scrapers --store coto     # solo una tienda
    python -m src.scripts.run_scrapers --skip-embeddings
    python -m src.scripts.run_scrapers --prune-dry-run  # ver qué se borraría
    python -m src.scripts.run_scrapers --no-prune       # no borrar nada

Este es el CLI *interactivo*, para desarrollo. El camino desatendido (cron) es
`src/scripts/orchestrator.py`, que reusa los runners de este módulo y le agrega
logging a archivo, telemetría en Postgres, lockfile y timeout. La lógica de
recorrido vive acá y en un solo lugar: el orquestador no la duplica.

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
import logging
import sys
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable

from src.database import SmartCartDB
from src.scrapers import scraper_carrefour, scraper_coto, scraper_dia

logger = logging.getLogger(__name__)


@dataclass
class StoreRunResult:
    """
    Lo que dejó el recorrido de una tienda.

    Existe porque el orquestador necesita distinguir tres desenlaces que la vieja
    tupla `(int, set)` no podía expresar: todo bien, algo se perdió pero el resto
    sirve, y no se pudo hacer nada. Sin esa distinción la telemetría sólo puede
    decir "corrió" o "explotó", que es justo lo que no ayuda a las 3 de la mañana.
    """
    store: str                              # "coto"
    store_id: str                           # "coto_online"
    items_scraped: int = 0                  # filas efectivamente persistidas
    seen_skus: set = field(default_factory=set)
    # Las claves de categoría cuyo barrido cerró bien. Es el ALCANCE del pruning:
    # sólo se borran filas cuya `source_category` está acá, así que una categoría
    # caída ya no le cuesta el pruning al resto de la tienda.
    ok_categories: set = field(default_factory=set)
    categories_total: int = 0
    categories_ok: int = 0
    categories_failed: int = 0
    errors: list = field(default_factory=list)

    @property
    def complete(self) -> bool:
        """
        Si el barrido cubrió TODAS las categorías.

        Ya NO es lo que habilita el pruning —eso ahora lo decide `ok_categories`,
        categoría por categoría—, pero sigue siendo lo que separa un barrido limpio
        de uno con pérdidas para la telemetría y el resumen.
        """
        return self.categories_total > 0 and self.categories_failed == 0

    @property
    def first_error(self) -> str | None:
        return self.errors[0] if self.errors else None


def _run_store(
    db: SmartCartDB,
    store: str,
    store_id: str,
    label: str,
    categories: Iterable[str],
    scrape: Callable[[str], list],
    pause: float,
) -> StoreRunResult:
    """
    Recorre las categorías de una tienda y devuelve qué pasó con cada una.

    La caída de UNA categoría no aborta la tienda: se loguea, se cuenta como
    fallida y se sigue con la siguiente. Rescatar las categorías que sí anduvieron
    vale la pena, y ahora tampoco cuesta el pruning: `ok_categories` acumula sólo
    las que cerraron bien y el borrado se acota a ellas. Tolerar el fallo sin dejar
    que contamine la decisión de borrar, que es el punto, ya no obliga a apagar el
    pruning de la tienda entera.

    El set de SKUs se arma acá y no dentro de `save_store_products` porque sólo
    tiene sentido junto al alcance que lo acompaña: es el universo de lo que las
    categorías de `ok_categories` ofrecen hoy.
    """
    categories = list(categories)
    result = StoreRunResult(store=store, store_id=store_id, categories_total=len(categories))

    for category in categories:
        logger.info("[%s] categoría '%s'", label, category)
        try:
            products = scrape(category)

            if products:
                saved = db.save_store_products(products, store_id)
                result.items_scraped += saved
                result.seen_skus.update(p["store_sku"] for p in products if p.get("store_sku"))
            else:
                logger.warning("[%s] categoría '%s' no devolvió productos.", label, category)

            result.categories_ok += 1
            result.ok_categories.add(category)
        except Exception as exc:
            # Un 500 de la tienda, un hash de persisted query rotado o Postgres
            # caído a mitad del barrido. Ninguno de los tres justifica perder las
            # categorías que ya entraron.
            result.categories_failed += 1
            result.errors.append(f"{category}: {type(exc).__name__}: {exc}")
            logger.exception("[%s] falló la categoría '%s'.", label, category)

        time.sleep(pause)

    return result


def run_coto(db: SmartCartDB) -> StoreRunResult:
    scraper = scraper_coto.CotoScraper()
    return _run_store(db, "coto", "coto_online", "COTO", scraper_coto.MVP_CATEGORIES,
                      scraper.scrape_category, 2.0)


def run_dia(db: SmartCartDB) -> StoreRunResult:
    scraper = scraper_dia.DiaScraper()
    return _run_store(db, "dia", "dia_online", "DÍA", scraper_dia.MVP_CATEGORIES,
                      scraper.scrape_entire_category, 3.5)


def run_carrefour(db: SmartCartDB) -> StoreRunResult:
    scraper = scraper_carrefour.CarrefourScraper()
    return _run_store(db, "carrefour", "carrefour_online", "CARREFOUR",
                      scraper_carrefour.MVP_CATEGORIES, scraper.scrape_entire_category, 3.5)


# A nivel módulo y no dentro de main(): el orquestador lo importa para armar su
# propio bucle con telemetría en vez de re-declarar la lista de tiendas. Sumar una
# tienda es una entrada acá, no dos listas que se desincronizan.
STORE_RUNNERS: dict[str, tuple[Callable[[SmartCartDB], StoreRunResult], str]] = {
    "coto": (run_coto, "coto_online"),
    "dia": (run_dia, "dia_online"),
    "carrefour": (run_carrefour, "carrefour_online"),
}


def build_arg_parser(description: str = "Corre los scrapers de SmartCart.") -> argparse.ArgumentParser:
    """Los flags que comparten este CLI y el orquestador, definidos una sola vez."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--store",
        choices=[*STORE_RUNNERS, "all"],
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
    return parser


def main():
    # El scrapeo tarda varios minutos; sin esto Python bufferea la salida al
    # redirigirla a un archivo o un pipe y no se ve el progreso hasta el final.
    sys.stdout.reconfigure(line_buffering=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    args = build_arg_parser().parse_args()

    db = SmartCartDB()
    selected = list(STORE_RUNNERS) if args.store == "all" else [args.store]

    started = time.time()
    results: dict[str, StoreRunResult | None] = {}
    pruned: dict[str, dict] = {}

    for store in selected:
        runner, store_id = STORE_RUNNERS[store]
        try:
            result = results[store] = runner(db)
        except Exception:
            # `_run_store` ya tolera el fallo de una categoría, así que llegar acá
            # significa algo estructural (construir el scraper, por ejemplo).
            logger.exception("Falló el scrapeo de '%s'.", store)
            results[store] = None
            continue

        if args.no_prune:
            continue
        if not result.ok_categories:
            logger.warning("Pruning de '%s' omitido: ninguna categoría terminó su barrido.",
                           store)
            continue
        if not result.complete:
            logger.warning(
                "Pruning de '%s' acotado a %d/%d categorías: las que fallaron quedan "
                "fuera del borrado.",
                store, result.categories_ok, result.categories_total,
            )

        pruned[store] = db.prune_missing_store_products(
            result.store_id, result.seen_skus, dry_run=args.prune_dry_run,
            categories=result.ok_categories,
        )

    if not args.skip_embeddings:
        try:
            # Import diferido: carga sentence-transformers, que es lento.
            from src.embeddings import EmbeddingPipeline

            EmbeddingPipeline().generate_and_save_embeddings()
        except Exception:
            logger.exception("Falló la generación de embeddings.")

    print("\n" + "=" * 60)
    print("RESUMEN")
    print("=" * 60)
    for store, result in results.items():
        if result is None:
            linea = f"  {store:10} -> FALLÓ"
        else:
            linea = f"  {store:10} -> {result.items_scraped} productos"
            if result.categories_failed:
                linea += f"  | {result.categories_failed}/{result.categories_total} categorías fallidas"
        p = pruned.get(store)
        if p:
            if p["skipped"]:
                linea += f"  | pruning OMITIDO ({p['reason']})"
            else:
                linea += (f"  | -{p['deleted']} obsoletas, -{p['orphans']} sin ofertas"
                          f" (sobre {len(result.ok_categories)} categorías)")
        print(linea)
    print(f"  tiempo -> {time.time() - started:.0f}s")
    print("=" * 60)

    # Exit code distinto de 0 si alguna tienda falló entera o en parte, para que
    # sirva en CI. El orquestador tiene su propia tabla de exit codes, más fina.
    fallo = any(r is None or r.categories_failed for r in results.values())
    return 1 if fallo else 0


if __name__ == "__main__":
    raise SystemExit(main())
