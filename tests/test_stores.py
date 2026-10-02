"""
El registro de supermercados (src/stores.py) contra todo lo que lo repite.

Los datos de cada tienda se derivan del registro, pero el código propio de cada
una (scrapers, transformador de promos) y los espejos fuera de Python no pueden
derivarse. Todos fallaban en silencio cuando les faltaba una tienda: sin
transformador los productos se guardaban sin promos, sin columna en
deliveryCosts.js /optimize daba KeyError, y sin entrada en scrape.yml la tienda
dejaba de barrerse de noche. Estos tests convierten cada olvido en un pytest rojo.
"""
import pathlib
import re

from src.database import PROMO_TRANSFORMERS
from src.promotions import SCRAPERS
from src.scripts.curar_frescos import _scrapers
from src.scripts.run_scrapers import STORE_RUNNERS
from src.stores import STORES

RAIZ = pathlib.Path(__file__).parent.parent
KEYS = [s.key for s in STORES]
IDS = [s.id for s in STORES]


def _leer(ruta):
    return (RAIZ / ruta).read_text(encoding="utf-8")


def test_registro_sin_duplicados():
    for campo in ("key", "id", "name"):
        valores = [getattr(s, campo) for s in STORES]
        assert len(set(valores)) == len(valores), campo


def test_registros_de_codigo_nombran_las_mismas_tiendas():
    assert set(STORE_RUNNERS) == set(KEYS)
    assert {store_id for _, store_id in STORE_RUNNERS.values()} == set(IDS)
    assert set(SCRAPERS) == set(KEYS)
    assert set(_scrapers()) == set(KEYS)
    assert set(PROMO_TRANSFORMERS) == set(IDS)


def test_constants_js_espeja_el_registro():
    fuente = _leer("frontend/src/utils/constants.js")
    bloque = fuente.split("export const STORES = [", 1)[1].split("];", 1)[0]
    frontend = re.findall(r'\{ id: "([^"]+)", name: "([^"]+)"', bloque)
    assert frontend == [(s.id, s.name) for s in STORES]


def test_cada_zona_de_envio_trae_todas_las_tiendas():
    fuente = _leer("frontend/src/utils/deliveryCosts.js")
    bloque = fuente.split("export const DELIVERY_COSTS_BY_ZONE = {", 1)[1].split("\n};", 1)[0]
    zonas = re.findall(r'^\s*("[^"]+"|\w+): \{([^}]*)\}', bloque, re.M)
    assert zonas
    for zona, costos in zonas:
        assert set(re.findall(r"(\w+):", costos)) == set(IDS), zona


def test_scrape_yml_barre_todas_las_tiendas():
    fuente = _leer(".github/workflows/scrape.yml")
    defaults = re.findall(r'tiendas:.*?default: "([^"]*)"', fuente, re.S) + re.findall(r"\$\{TIENDAS:-([^}]+)\}", fuente)
    assert len(defaults) == 2
    for lista in defaults:
        assert lista.split(",") == KEYS


def test_cada_tienda_tiene_su_dump_de_taxonomia():
    for key in KEYS:
        assert (RAIZ / "src" / "scrapers" / f"{key}_categories.json").exists(), key
