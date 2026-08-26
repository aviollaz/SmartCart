# src/taxonomy.py
"""
Los dumps estáticos de la taxonomía de cada cadena.

`src/scrapers/{coto,dia,carrefour}_categories.json` mapean la clave con la que se
scrapea una categoría —el id `catv…` en Coto, el slug de URL en los dos VTEX— a su
ruta legible ("Almacén -> Golosinas -> Alfajores"). Se regeneran con los scripts
`get_*_categories` de `src/scrapers/`.

Este módulo es lo que quedó de `src/category_tags.py`. Ahí vivían dos cosas más
que ya no existen:

* Los **tags** por producto (la ruta slugificada guardada en
  `unified_products.tags`) y el filtro de "misma góndola" por solapamiento `&&`.
  Los reemplazó una sola columna, `unified_products.shelf`, con la góndola
  canónica de `src/shelves.py`: como las tres cadenas escriben el mismo slug para
  el mismo estante, comparar es una igualdad y no hay vocabulario que conciliar.
* `category_label()`, la hoja de la ruta, que alimentaba los 4 buckets de
  `SmartCartDB.CATEGORY_MAP`. Ese dict tampoco existe más.

Lo que sobrevive es el uso para el que los archivos fueron scrapeados: son la
referencia para **elegir** claves nuevas al agregar una góndola a `SHELVES`, y
`tests/test_shelves.py` los usa para verificar que toda clave de la tabla exista
de verdad en la taxonomía de su tienda. Sin eso, un typo en una fila nueva no
falla: scrapea cero productos y la góndola queda vacía sin que nada avise.
"""
import json
import os
from functools import lru_cache

_BASE_DIR = os.path.dirname(__file__)

_TAXONOMY_PATHS = {
    "coto": os.path.join(_BASE_DIR, "scrapers", "coto_categories.json"),
    "dia": os.path.join(_BASE_DIR, "scrapers", "dia_categories.json"),
    "carrefour": os.path.join(_BASE_DIR, "scrapers", "carrefour_categories.json"),
}


@lru_cache(maxsize=None)
def load_taxonomy(store: str) -> dict:
    """
    El dump de categorías de una tienda ("coto" | "dia" | "carrefour").

    Devuelve {id_o_slug: "Top -> Sub -> Hoja"}, o {} si la tienda no tiene dump.
    Cacheado: estos archivos no cambian en runtime.
    """
    path = _TAXONOMY_PATHS.get(store)
    if not path or not os.path.exists(path):
        return {}

    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def category_path(store: str, category_key: str) -> str | None:
    """La ruta legible de una clave ("Almacén -> Golosinas -> Alfajores"), o None."""
    return load_taxonomy(store).get(category_key) or None
