# src/category_tags.py
"""
Tags estrictos de categoría, derivados de la taxonomía propia de cada tienda.

Los scrapers ya reciben la clave exacta con la que cada archivo de taxonomía
está indexado: `scrape_category()` recibe el `category_id` de Coto
(ej. "catv00003596") y `scrape_entire_category()` recibe el slug de Día
(ej. "almacen/golosinas-y-alfajores/alfajores"). Hasta ahora esa ruta se
descartaba y solo se guardaba la etiqueta hoja, que después colapsaba a uno de
los 4 buckets de `SmartCartDB.CATEGORY_MAP`.

Guardar la ruta completa como tags resuelve la colisión semántica que motivó
este módulo: la mayonesa cuelga de "Almacén -> Aceites y Aderezos" y la carne de
"Frescos -> Carnes", así que estructuralmente no pueden matchear. No hace falta
ningún ruleset de keywords sobre el nombre del producto.

Sobre el operador de comparación: las dos tiendas anidan distinto. Coto pone la
leche en "Frescos -> Lácteos -> Leches" (3 niveles) y Día en "Frescos -> Leches"
(2 niveles). Por eso comparar por prefijo de rama falla de forma asimétrica
justo en el caso principal (buscar en una tienda el sustituto de un producto de
la otra), y la comparación correcta es el SOLAPAMIENTO sobre los segmentos
específicos, ver `filter_tags()`.
"""
import json
import os
from functools import lru_cache

from src.text_utils import slugify_segment

_BASE_DIR = os.path.dirname(__file__)

_TAXONOMY_PATHS = {
    "coto": os.path.join(_BASE_DIR, "scrapers", "coto_categories.json"),
    "dia": os.path.join(_BASE_DIR, "scrapers", "dia_categories.json"),
    "carrefour": os.path.join(_BASE_DIR, "scrapers", "carrefour_categories.json"),
}


@lru_cache(maxsize=None)
def load_taxonomy(store: str) -> dict:
    """
    Carga el dump estático de categorías de una tienda ("coto" | "dia").
    Devuelve {id_o_slug: "Top -> Sub -> Hoja"}. Cacheado: los scrapers lo
    consultan una vez por categoría y estos archivos no cambian en runtime.
    """
    path = _TAXONOMY_PATHS.get(store)
    if not path or not os.path.exists(path):
        return {}

    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def tags_for_category(store: str, category_key: str) -> list[str]:
    """
    Resuelve el id/slug de categoría de una tienda a sus segmentos slugificados.

    "catv00003596" -> ["almacen", "golosinas", "alfajores"]

    Devuelve [] si la clave no está en la taxonomía, para que los scrapers
    caigan al comportamiento anterior en vez de romper.
    """
    raw_path = load_taxonomy(store).get(category_key)
    if not raw_path:
        return []

    return [slugify_segment(part) for part in raw_path.split("->") if part.strip()]


def category_label(store: str, category_key: str) -> str | None:
    """
    Etiqueta hoja legible de una categoría (ej. "Alfajores"), tal como la
    espera `SmartCartDB.CATEGORY_MAP`. None si la clave no está en la taxonomía.
    """
    raw_path = load_taxonomy(store).get(category_key)
    if not raw_path:
        return None

    parts = [part.strip() for part in raw_path.split("->") if part.strip()]
    return parts[-1] if parts else None


def filter_tags(tags: list[str] | None) -> list[str]:
    """
    Segmentos utilizables para comparar dos productos ("misma góndola"),
    descartando el top-level.

    Descartar el top-level es lo que da la estrictez: sin eso "almacen"
    matchearía contra medio catálogo. Los tags completos igual se guardan en la
    base porque sirven para facetas.

    Se usa con el operador de solapamiento de Postgres (`&&`), no de
    containment (`@>`), justamente por la diferencia de profundidad entre
    tiendas descrita arriba:

        leche Coto ["frescos","lacteos","leches"] -> ["lacteos","leches"]
        leche Día  ["frescos","leches"]           -> ["leches"]
        ambos solapan en "leches" -> son sustituibles

        mayonesa   ["almacen","aceites-y-aderezos"] -> ["aceites-y-aderezos"]
        carne      ["frescos","carnes"]             -> ["carnes"]
        no solapan -> no son sustituibles

    Devuelve [] cuando no hay suficiente ruta para decidir, y en ese caso quien
    llama debe caer al filtro por `category`.
    """
    if not tags or len(tags) < 2:
        return []

    return list(tags[1:])
