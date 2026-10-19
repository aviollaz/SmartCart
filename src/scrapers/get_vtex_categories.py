"""
Regenera `src/scrapers/<key>_categories.json` de una tienda VTEX desde su API
REST pública de catálogo (el "/3" es la profundidad del árbol).

Uso:
    python -m src.scrapers.get_vtex_categories --store dia
"""
import argparse
import json
import os
from urllib.parse import urlparse

import httpx

from src.scrapers.vtex_stores import VTEX_SCRAPERS


def slug_from_url(url: str) -> str:
    """
    La ruta de la URL de una categoría, sin dominio.

    Se parsea la URL en vez de recortar el dominio con `replace()`, que es lo que
    hacía antes. VTEX dejó de devolver el dominio de la tienda en este árbol y
    ahora contesta `https://diaio.myvtex.com/almacen/...` — su dominio interno—,
    así que el `replace("https://diaonline.supermercadosdia.com.ar/", "")` no
    recortaba nada y la clave quedaba siendo la URL entera. Regenerar el dump con
    esa versión no fallaba: escribía 586 claves que ningún scraper puede usar, y
    `tests/test_shelves.py` habría empezado a rechazar TODAS las claves de Día a
    la vez, sin ninguna pista de por qué.

    Cualquier dominio sirve, que es justamente el punto: la clave es la ruta.
    """
    return urlparse(url).path.strip("/")


def fetch_categories(base_url: str) -> dict:
    """{slug: "Nivel 1 -> Nivel 2 [-> Nivel 3]"} para los niveles 2 y 3 del árbol."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:152.0) Gecko/20100101 Firefox/152.0",
        "Accept": "application/json",
        "Referer": f"{base_url}/",
    }
    with httpx.Client(headers=headers, http2=True, timeout=20.0) as client:
        response = client.get(f"{base_url}/api/catalog_system/pub/category/tree/3")
        response.raise_for_status()
        tree = response.json()

    categories = {}
    for level1 in tree:
        for level2 in level1.get("children") or []:
            for level3 in level2.get("children") or []:
                slug = slug_from_url(level3.get("url") or "")
                if slug:
                    categories[slug] = f"{level1['name']} -> {level2['name']} -> {level3['name']}"
            slug = slug_from_url(level2.get("url") or "")
            if slug and slug not in categories:
                categories[slug] = f"{level1['name']} -> {level2['name']}"
    return categories


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", required=True, choices=sorted(VTEX_SCRAPERS))
    store = parser.parse_args().store

    categories = fetch_categories(VTEX_SCRAPERS[store].BASE_URL)
    path = os.path.join(os.path.dirname(__file__), f"{store}_categories.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(categories, f, indent=2, ensure_ascii=False)
    print(f"{len(categories)} categorías de {store} escritas en {path}")
