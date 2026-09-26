"""
Suite pura: la tabla curada de frescos (`src/fresh_items.py`).

Sin base, sin modelo y sin red. Lo que la tabla promete es estructural —un SKU
no puede pertenecer a dos productos, un producto tiene que comparar algo— y todo
eso se verifica sobre la tabla misma. Que cada SKU siga existiendo en la cadena
NO se testea acá: depende de la red y cambia sin que nadie toque el repo; eso lo
reporta `python -m src.scripts.curar_frescos` en su sección "Obsoletos".
"""
from collections import Counter

import pytest

from src.fresh_items import (
    FRESH_ITEMS,
    FRESH_SHELVES,
    UNIT_MEASURES,
    fresh_item_for,
    resolve_identity,
)
from src.shelves import SHELVES, STORE_IDS, STORES

SLUGS = [item.slug for item in FRESH_ITEMS]


def test_la_tabla_no_esta_vacia():
    assert FRESH_ITEMS


def test_los_slugs_son_unicos():
    repetidos = [s for s, n in Counter(SLUGS).items() if n > 1]
    assert not repetidos


def test_las_etiquetas_son_unicas():
    # Dos ítems con el mismo nombre serían indistinguibles en la grilla.
    labels = Counter(item.label for item in FRESH_ITEMS)
    assert not [label for label, n in labels.items() if n > 1]


def test_ningun_sku_pertenece_a_dos_items():
    """
    La regla que más importa. Si un SKU estuviera en dos ítems, el índice se
    quedaría con el último y el primero perdería esa oferta sin avisar — la misma
    forma de "gana la última escritura" que ya vació la góndola de dulce de leche.
    """
    claves = Counter((store, sku) for item in FRESH_ITEMS for store, sku in item.skus.items())
    assert not [k for k, n in claves.items() if n > 1]


@pytest.mark.parametrize("item", FRESH_ITEMS, ids=SLUGS)
def test_cada_item_compara_al_menos_dos_cadenas(item):
    assert len(item.skus) >= 2


@pytest.mark.parametrize("item", FRESH_ITEMS, ids=SLUGS)
def test_las_tiendas_son_conocidas(item):
    assert set(item.skus) <= set(STORES)


@pytest.mark.parametrize("item", FRESH_ITEMS, ids=SLUGS)
def test_la_gondola_es_de_frescos(item):
    assert item.shelf in FRESH_SHELVES
    assert item.shelf in SHELVES


@pytest.mark.parametrize("item", FRESH_ITEMS, ids=SLUGS)
def test_la_unidad_es_kg_o_un(item):
    assert item.unit in UNIT_MEASURES


@pytest.mark.parametrize("item", FRESH_ITEMS, ids=SLUGS)
def test_ningun_sku_vacio(item):
    assert all(sku and sku.strip() == sku for sku in item.skus.values())


def test_el_indice_resuelve_cada_sku_a_su_item():
    for item in FRESH_ITEMS:
        for store, sku in item.skus.items():
            assert fresh_item_for(STORE_IDS[store], sku) is item


def test_el_indice_distingue_tiendas():
    # "8312" es el limón de Carrefour; el mismo string en Día no es nada.
    assert fresh_item_for("carrefour_online", "8312").slug == "limon"
    assert fresh_item_for("dia_online", "8312") is None


# ------------------------------------------------------------ resolve_identity

def _producto(**overrides):
    base = {
        "store_sku": "sku_x", "ean": "7790040997417", "name": "Nombre de la tienda",
        "brand": "Marca", "unit_type": "un", "total_volume_weight": 1.0,
    }
    return {**base, **overrides}


def test_un_sku_curado_toma_la_identidad_canonica():
    """
    La manzana roja de Día: el scraper la manda como ('un', 1.0) porque el parser
    no lee "x Kg.", y con el nombre de Día. Sale con el id, el nombre y la medida
    del ítem, iguales para las tres cadenas.
    """
    ident = resolve_identity("dia_online", _producto(
        store_sku="90039", ean=None, name="Manzana Roja x Kg.", brand="Dia"))

    assert ident == {
        "unified_id": "fresh_manzana-roja",
        "ean": None,
        "name": "Manzana roja x kg",
        "brand": None,
        "unit_type": "g",
        "total_volume_weight": 1000.0,
    }


def test_las_tres_cadenas_convergen_al_mismo_unified_id():
    item = fresh_item_for("coto_online", "sku00000529")
    ids = {resolve_identity(STORE_IDS[store], _producto(store_sku=sku))["unified_id"]
           for store, sku in item.skus.items()}
    assert ids == {"fresh_manzana-roja"}


def test_un_item_por_unidad_queda_en_un():
    ident = resolve_identity("carrefour_online", _producto(store_sku="691815"))  # mango
    assert (ident["unit_type"], ident["total_volume_weight"]) == ("un", 1.0)


def test_un_sku_curado_pisa_el_ean_aunque_venga_uno():
    # Si una cadena empezara a mandar un EAN real para un fresco curado, la tabla
    # sigue mandando: el ítem ya compara las tres cadenas y un EAN de una sola lo
    # separaría de las otras dos.
    ident = resolve_identity("coto_online", _producto(store_sku="sku00000529"))
    assert ident["unified_id"] == "fresh_manzana-roja"
    assert ident["ean"] is None


def test_fuera_de_la_tabla_con_ean_unifica_por_ean():
    prod = _producto()
    ident = resolve_identity("coto_online", prod)
    assert ident["unified_id"] == "prod_7790040997417"
    assert ident["ean"] == "7790040997417"
    assert (ident["name"], ident["brand"]) == ("Nombre de la tienda", "Marca")
    assert (ident["unit_type"], ident["total_volume_weight"]) == ("un", 1.0)


def test_fuera_de_la_tabla_sin_ean_queda_por_tienda():
    ident = resolve_identity("dia_online", _producto(store_sku="999999", ean=None))
    assert ident["unified_id"] == "dia_online_999999"
