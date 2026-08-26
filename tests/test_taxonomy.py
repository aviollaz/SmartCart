"""
Tests de src/taxonomy.py: los dumps estáticos de categorías de cada cadena.

Puro Python, contra los archivos reales. Es lo que quedó de
`tests/test_category_tags.py` — el resto de ese archivo cubría los tags por
producto y el filtro por solapamiento, que ya no existen (los reemplazó la
góndola canónica, ver tests/test_shelves.py).
"""
import pytest

from src.shelves import STORES
from src.taxonomy import category_path, load_taxonomy


@pytest.mark.parametrize("store", STORES)
def test_el_dump_de_cada_tienda_esta_presente_y_no_vacio(store):
    """
    Un dump ausente devuelve {} en silencio, y a partir de ahí `category_path`
    contesta None para todo: los scrapers seguirían andando, pero sin evidencia
    de categoría para el parser dietario y con el test de claves de
    tests/test_shelves.py pasando en falso sobre un diccionario vacío.
    """
    assert len(load_taxonomy(store)) > 100


def test_category_path_devuelve_la_ruta_legible():
    assert category_path("coto", "catv00003596") == "Almacén -> Golosinas -> Alfajores"


def test_category_path_de_clave_desconocida_es_none():
    assert category_path("coto", "catv00000000") is None
    assert category_path("tienda_inexistente", "lo-que-sea") is None


def test_load_taxonomy_de_tienda_desconocida_no_levanta():
    """Los scrapers la consultan con el nombre de su tienda; un KeyError acá
    tumbaría un barrido entero por un archivo faltante."""
    assert load_taxonomy("tienda_inexistente") == {}
