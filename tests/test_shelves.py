"""
Tests de la tabla de góndolas (src/shelves.py). Puro Python: corren contra los
dumps reales de taxonomía, sin base de datos ni modelo de embeddings.

Lo que se protege acá es la premisa del catálogo: barrer las mismas góndolas en
las tres tiendas. Una clave mal tipeada no rompe nada en runtime — el scraper
loguea "no devolvió productos" y sigue — así que sin estos tests la tienda queda
sin esa góndola y el optimizador simplemente deja de tener con qué comparar.
"""
import itertools

import pytest

from src.category_tags import filter_tags, load_taxonomy
from src.shelves import (
    SHELVES,
    STORES,
    keys_for_store,
    shelf_for_key,
    shelf_tags,
)

PARES = list(itertools.combinations(STORES, 2))


@pytest.mark.parametrize("store", STORES)
def test_todas_las_claves_existen_en_la_taxonomia(store):
    """Una clave que no está en el dump se scrapea sin tags y sin avisar."""
    taxonomia = load_taxonomy(store)
    desconocidas = [k for k in keys_for_store(store) if k not in taxonomia]

    assert not desconocidas, f"claves de {store} ausentes del dump: {desconocidas}"


@pytest.mark.parametrize("shelf", SHELVES)
def test_cada_gondola_cubre_las_tres_tiendas(shelf):
    """
    El sentido de la tabla es la alineación: una góndola que le falta a una
    tienda es exactamente el caso que no se puede comparar entre cadenas.
    """
    gondola = SHELVES[shelf]

    for store in STORES:
        assert gondola.get(store), f"'{shelf}' no tiene claves de {store}"


@pytest.mark.parametrize("shelf,store", [(s, t) for s in SHELVES for t in STORES])
def test_cada_clave_pertenece_a_una_sola_gondola(shelf, store):
    """
    Una clave repetida en dos góndolas haría ambiguo el tag canónico:
    `shelf_for_key` devuelve la primera y el producto quedaría etiquetado con
    una góndola que no es la que se quiso barrer.
    """
    for key in SHELVES[shelf][store]:
        assert shelf_for_key(store, key) == shelf


@pytest.mark.parametrize("store", STORES)
def test_las_claves_no_se_repiten_entre_gondolas(store):
    todas = [k for g in SHELVES.values() for k in g[store]]

    assert len(todas) == len(set(todas)), f"claves duplicadas en {store}: {todas}"


@pytest.mark.parametrize("shelf,par", [(s, p) for s in SHELVES for p in PARES])
def test_cada_gondola_solapa_entre_tiendas(shelf, par):
    """
    La razón de ser del tag canónico.

    Sin él sólo 7 de las 20 góndolas solapaban en los tres pares: cada cadena
    nombra distinto el mismo estante ("Mate" / "Yerba mate" / "Yerba"), y
    `filter_tags` + el `&&` de Postgres comparan literales. Un solapamiento
    vacío significa que ningún producto de esa góndola puede sustituir al de la
    otra tienda — la sugerencia no aparece y nada indica que falta.
    """
    gondola = SHELVES[shelf]
    a, b = par

    tags_a = {t for k in gondola[a] for t in filter_tags(shelf_tags(a, k))}
    tags_b = {t for k in gondola[b] for t in filter_tags(shelf_tags(b, k))}

    assert tags_a & tags_b, f"'{shelf}': {a} y {b} no comparten ningún tag"


@pytest.mark.parametrize("store", STORES)
def test_el_tag_canonico_esta_en_cada_clave(store):
    for key in keys_for_store(store):
        assert shelf_for_key(store, key) in shelf_tags(store, key)


def test_el_tag_canonico_no_se_duplica():
    """Cuando la hoja de la tienda ya se llama igual que la góndola."""
    tags = shelf_tags("dia", "almacen/golosinas-y-alfajores/alfajores")

    assert tags.count("alfajores") == 1


def test_gondolas_distintas_no_solapan():
    """
    El tag canónico agrega alcance, no lo afloja: sigue sin poder sugerirse una
    mermelada para reemplazar un aceite.
    """
    aceites = filter_tags(shelf_tags("dia", "almacen/aceites-y-aderezos"))
    mermeladas = filter_tags(shelf_tags("coto", "catv00001408"))

    assert not set(aceites) & set(mermeladas)


def test_clave_ajena_a_la_tabla_no_recibe_tag_de_gondola():
    """
    Una categoría que no está en la tabla (ej. un scrapeo manual) conserva el
    comportamiento anterior en vez de recibir una góndola inventada.
    """
    carnes = "catv00001460"  # Frescos -> Carniceria -> Carnes

    assert shelf_for_key("coto", carnes) is None
    assert shelf_tags("coto", carnes) == ["frescos", "carniceria", "carnes"]


@pytest.mark.parametrize("store", STORES)
def test_keys_for_store_no_devuelve_duplicados(store):
    claves = keys_for_store(store)

    assert len(claves) == len(set(claves))
