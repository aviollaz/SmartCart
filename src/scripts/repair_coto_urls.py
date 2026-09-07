"""
Reparación one-shot de las URLs de Coto ya guardadas.

Uso:
    python -m src.scripts.repair_coto_urls --dry-run   # informe, sin escribir
    python -m src.scripts.repair_coto_urls             # aplica

`build_coto_url()` armaba el slug con el nombre crudo del producto, así que
cualquier nombre con "%" ("Bizcochos 100% Vegetal") producía un escape
porcentual inválido y el CDN de Coto contesta **400 Bad Request**. Medido sobre
la base: **1.954 de 8.143** URLs de Coto guardadas (24%) tienen caracteres que
no deberían estar en una ruta.

Normalmente el proyecto no repara datos con scripts: la vía es re-scrapear, que
es lo que dice CLAUDE.md y por eso toda columna derivada tiene que estar en el
`ON CONFLICT DO UPDATE SET`. Acá se hace igual, y por un motivo acotado: el
barrido de Coto tarda ~2-3 h, corre de madrugada y viene saliendo PARTIAL varias
noches seguidas, mientras que estos links son lo que más se ve del producto —el
desglose de /optimize abre una pestaña por producto de Coto, porque Coto no
tiene carrito por URL como las VTEX.

**Lo que lo vuelve seguro es que `_slugify` es idempotente sobre su propia
salida**: aplicarla al slug ya guardado da exactamente lo mismo que aplicarla al
nombre original, porque las dos transformaciones que el slug viejo ya sufrió
—minúsculas y espacios a guiones— son un subconjunto de lo que hace `_slugify`.
Verificado sobre casos reales de la base antes de escribir esto. O sea que no
hace falta el nombre del producto —que en `store_products.name` puede ser NULL
en filas viejas— y la reparación no puede inventar una URL distinta de la que va
a escribir el próximo barrido.

Es idempotente y no borra nada: correrlo dos veces no cambia nada la segunda.
"""
import argparse
import logging
import re

import psycopg
from dotenv import load_dotenv

from src.scrapers.scraper_coto import _slugify
from src.schema import resolve_conn_string

logger = logging.getLogger(__name__)

STORE_ID = "coto_online"

# Una URL de Coto es "<prefijo>/productos/<slug>/_/R-<id>-<id>-200". Se captura
# el slug para pasarlo por _slugify y se deja el resto intacto: el código R- es
# lo único que resuelve la página y no se toca nunca.
URL_RE = re.compile(r"^(https://www\.coto\.com\.ar/productos/)(.*?)(/_/R-.+)$")


def repair_url(url: str) -> str | None:
    """La URL saneada, o None si ya estaba bien o no tiene la forma esperada."""
    match = URL_RE.match(url or "")
    if not match:
        return None

    prefijo, slug_viejo, sufijo = match.groups()
    slug_nuevo = _slugify(slug_viejo)
    if not slug_nuevo or slug_nuevo == slug_viejo:
        return None

    return f"{prefijo}{slug_nuevo}{sufijo}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Informa qué cambiaría y no escribe nada.")
    args = parser.parse_args()

    # Igual que migrate_shelves.py: el .env se carga en el entry point, no al
    # importar src.schema. Sin esto el script apunta al docker-compose local.
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    with psycopg.connect(resolve_conn_string()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, product_url FROM store_products"
                " WHERE store_id = %s AND product_url IS NOT NULL",
                (STORE_ID,),
            )
            filas = cur.fetchall()

            arreglos = []
            for fila_id, url in filas:
                nueva = repair_url(url)
                if nueva:
                    arreglos.append((nueva, fila_id))

            logger.info("%d URLs de Coto revisadas, %d hay que arreglar.",
                        len(filas), len(arreglos))
            for nueva, _ in arreglos[:5]:
                logger.info("  ejemplo -> %s", nueva)

            if not arreglos:
                return 0

            if args.dry_run:
                logger.info("--dry-run: no se escribió nada.")
                return 0

            cur.executemany(
                "UPDATE store_products SET product_url = %s WHERE id = %s",
                arreglos,
            )
            conn.commit()
            logger.info("%d URLs actualizadas.", len(arreglos))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
