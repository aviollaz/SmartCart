"""
Migración one-shot: `unified_products.shelf` reemplaza a `category` y `tags`.

Uso:
    python -m src.scripts.migrate_shelves --dry-run   # backfill + informe, sin DROP
    python -m src.scripts.migrate_shelves             # backfill + DROP

Corre **después** de mergear el código, nunca antes. Los tres endpoints de
producto SELECTeaban `units_per_pack` y `category`: dropearlas primero los hace
contestar 500 con `UndefinedColumn`.

Los cuatro pasos, en este orden exacto:

 1. `ensure_schema()` — agrega `unified_products.shelf` y su índice.
 2. Backfill de `shelf` desde `tags`.
 3. Informe: cuántas filas quedaron sin góndola.
 4. DROP de `units_per_pack`, `category`, `tags` y el índice GIN.

**Por qué el backfill sale de `tags` y no de `store_products.source_category`,**
que sería lo obvio: `source_category` está en NULL en las 3.252 filas de Coto y
las 1.529 de Día, porque esa columna se agregó el 2026-08-24 y esas filas se
escribieron por última vez el 2026-08-21. `tags`, en cambio, ya trae el slug de
góndola adentro —`shelf_tags()` lo venía agregando a la ruta de taxonomía— en
6.401 de 6.401 productos, con exactamente uno cada uno. O sea que la columna
nueva se llena sin barrer nada.

**El paso 4 se aborta si quedó una sola fila sin góndola.** Dropear `tags` es lo
que vuelve irreversible el backfill: después de eso no hay de dónde recalcular el
slug salvo un barrido completo. Un `--force` sería exactamente la clase de
escotilla que se usa sin leer por qué existe, así que no hay: si quedan filas
sueltas, se miran y se decide a mano.

Después de esto conviene un barrido completo (`python -m src.scripts.run_scrapers`,
~30 min). No hace falta para que la app ande —el backfill ya dejó la góndola
puesta— pero es lo que llena `source_category` en Coto y Día, que hasta entonces
deja al pruning acotado sin poder borrar nada en esas dos tiendas (seguro, pero
inerte: `source_category = ANY(...)` nunca matchea un NULL).
"""
import argparse
import logging
import sys

import psycopg
from dotenv import load_dotenv

from src.schema import ensure_schema, resolve_conn_string
from src.shelves import SHELVES

logger = logging.getLogger(__name__)

# El orden importa: el índice GIN cuelga de `tags`, así que se va con ella.
_DROPS = (
    """
    ALTER TABLE unified_products
        DROP COLUMN IF EXISTS units_per_pack,
        DROP COLUMN IF EXISTS category,
        DROP COLUMN IF EXISTS tags;
    """,
    "DROP INDEX IF EXISTS idx_unified_products_tags;",
)


def _column_exists(cur, table: str, column: str) -> bool:
    cur.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
        """,
        (table, column),
    )
    return cur.fetchone() is not None


def backfill_shelf(cur) -> int:
    """
    Llena `shelf` desde el slug de góndola que ya vive dentro de `tags`.

    Sólo toca filas con `shelf IS NULL`, así que es idempotente y no pisa lo que
    un barrido posterior haya escrito bien.
    """
    if not _column_exists(cur, "unified_products", "tags"):
        logger.info("La columna `tags` ya no existe: el backfill ya corrió.")
        return 0

    cur.execute(
        """
        UPDATE unified_products
           SET shelf = (
                SELECT t FROM unnest(tags) AS t
                 WHERE t = ANY(%s)
                 LIMIT 1
           )
         WHERE shelf IS NULL
           AND tags IS NOT NULL
        """,
        (list(SHELVES),),
    )
    return cur.rowcount


def report_missing(cur) -> int:
    cur.execute("SELECT count(*) FROM unified_products WHERE shelf IS NULL")
    return cur.fetchone()[0]


def main(argv=None) -> int:
    load_dotenv()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Corre el backfill y el informe y revierte todo, sin dropear nada.",
    )
    args = parser.parse_args(argv)

    dsn = resolve_conn_string()
    try:
        with psycopg.connect(dsn) as conn:
            ensure_schema(conn)

            with conn.cursor() as cur:
                actualizadas = backfill_shelf(cur)
                logger.info("Backfill: %d filas recibieron su góndola.", actualizadas)

                faltantes = report_missing(cur)
                cur.execute("SELECT count(*) FROM unified_products")
                total = cur.fetchone()[0]
                logger.info("Góndola presente en %d de %d productos.", total - faltantes, total)

                if faltantes:
                    logger.error(
                        "ABORTADO: %d producto(s) sin góndola. Dropear `tags` ahora "
                        "los dejaría sin forma de recuperarla salvo un barrido "
                        "completo. Revisalos con: SELECT id, name, tags FROM "
                        "unified_products WHERE shelf IS NULL LIMIT 20;",
                        faltantes,
                    )
                    conn.rollback()
                    return 1

                if args.dry_run:
                    conn.rollback()
                    logger.info("Dry-run: nada se escribió. Sin --dry-run se dropearían "
                                "units_per_pack, category y tags.")
                    return 0

                for statement in _DROPS:
                    cur.execute(statement)
                logger.info("Columnas muertas eliminadas: units_per_pack, category, tags.")

        logger.info("Migración completa. Conviene correr ahora un barrido completo "
                    "(python -m src.scripts.run_scrapers) para llenar source_category.")
        return 0
    except Exception:
        logger.exception("La migración falló; no se escribió nada.")
        return 2


if __name__ == "__main__":
    sys.exit(main())
