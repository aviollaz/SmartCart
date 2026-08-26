"""
Tests de la tabla de góndolas (src/shelves.py). Puro Python: corren contra los
dumps reales de taxonomía, sin base de datos ni modelo de embeddings.

Lo que se protege acá es la premisa del catálogo: barrer las mismas góndolas en
las tres tiendas. Una clave mal tipeada no rompe nada en runtime — el scraper
loguea "no devolvió productos" y sigue — así que sin estos tests la tienda queda
sin esa góndola y el optimizador simplemente deja de tener con qué comparar.

Desde que la góndola es la única taxonomía del proyecto, la tabla también decide
qué categoría tiene cada producto, qué se puede sustituir por qué y qué muestra
el mega-menú, así que estos tests cubren bastante más que el barrido.
"""
import pytest

from src.shelves import (
    SECTIONS,
    SHELVES,
    STORE_IDS,
    STORES,
    keys_for_store,
    sections,
    shelf_for_key,
    shelf_label,
)
from src.taxonomy import load_taxonomy


@pytest.mark.parametrize("store", STORES)
def test_todas_las_claves_existen_en_la_taxonomia(store):
    """
    Una clave que no está en el dump se barre igual y no devuelve nada: el
    scraper loguea "sin productos" y sigue, así que el typo queda invisible
    hasta que alguien nota que esa góndola está vacía.
    """
    taxonomia = load_taxonomy(store)
    desconocidas = [k for k in keys_for_store(store) if k not in taxonomia]

    assert not desconocidas, f"claves de {store} ausentes del dump: {desconocidas}"


@pytest.mark.parametrize("slug", SHELVES)
def test_cada_gondola_cubre_las_tres_tiendas(slug):
    """
    El sentido de la tabla es la alineación: una góndola que le falta a una
    tienda es exactamente el caso que no se puede comparar entre cadenas.
    """
    for store in STORES:
        assert SHELVES[slug].keys_for(store), f"'{slug}' no tiene claves de {store}"


@pytest.mark.parametrize("slug,store", [(s, t) for s in SHELVES for t in STORES])
def test_cada_clave_pertenece_a_una_sola_gondola(slug, store):
    """
    Una clave repetida en dos góndolas haría ambigua la góndola del producto:
    `shelf_for_key` devolvería una sola y el producto quedaría archivado en una
    que no es la que se quiso barrer.
    """
    for key in SHELVES[slug].keys_for(store):
        assert shelf_for_key(store, key) == slug


@pytest.mark.parametrize("store", STORES)
def test_las_claves_no_se_repiten_entre_gondolas(store):
    todas = [k for shelf in SHELVES.values() for k in shelf.keys_for(store)]

    assert len(todas) == len(set(todas)), f"claves duplicadas en {store}: {todas}"


@pytest.mark.parametrize("store", STORES)
def test_toda_clave_barrida_resuelve_a_una_gondola(store):
    """
    Lo que hace comparable el catálogo: las tres tiendas escriben el MISMO slug
    para el mismo estante, así que `unified_products.shelf` se compara por
    igualdad y no hay vocabulario que conciliar.

    Antes esto se resolvía con un solapamiento (`&&`) sobre la ruta de taxonomía
    de cada tienda, y sólo 7 de las 20 góndolas solapaban en los tres pares: la
    yerba es "Mate" en Coto, "Yerba mate" en Día y "Yerba" en Carrefour. Un
    solapamiento vacío significaba que ningún producto de esa góndola podía
    sustituir al de la otra tienda, y nada lo indicaba.
    """
    for key in keys_for_store(store):
        assert shelf_for_key(store, key) in SHELVES


def test_clave_ajena_a_la_tabla_no_recibe_gondola():
    """
    Una categoría de fuera de la tabla (un scrapeo manual) no recibe una góndola
    inventada. `save_store_products` la rechaza, que es la dirección segura: un
    producto sin góndola desaparece de GET /category y se queda sin sustitutos.
    """
    carnes = "catv00001460"  # Frescos -> Carniceria -> Carnes

    assert shelf_for_key("coto", carnes) is None


@pytest.mark.parametrize("store", STORES)
def test_keys_for_store_no_devuelve_duplicados(store):
    claves = keys_for_store(store)

    assert len(claves) == len(set(claves))


# ---------------------------------------------------------------------------
# Presentación: lo que consume el mega-menú
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("slug", SHELVES)
def test_el_slug_es_la_clave_del_diccionario(slug):
    """El slug se guarda en la base: que la fila y su clave difieran sería una
    góndola imposible de pedir por GET /category/{slug}."""
    assert SHELVES[slug].slug == slug


def test_las_etiquetas_son_unicas():
    """Dos góndolas con la misma etiqueta son indistinguibles en el menú."""
    labels = [shelf.label for shelf in SHELVES.values()]

    assert len(labels) == len(set(labels))


@pytest.mark.parametrize("slug", SHELVES)
def test_cada_gondola_esta_en_una_seccion_conocida(slug):
    """Una sección fuera de SECTIONS no rompe el menú (cae al ícono genérico)
    pero sí queda al final, fuera del orden pensado."""
    assert SHELVES[slug].section in SECTIONS


def test_sections_cubre_todas_las_gondolas_sin_repetir():
    agrupadas = [s["slug"] for section in sections() for s in section["shelves"]]

    assert sorted(agrupadas) == sorted(SHELVES)


def test_sections_respeta_el_orden_declarado():
    assert [s["section"] for s in sections()] == list(SECTIONS)


def test_shelf_label_traduce_el_slug():
    assert shelf_label("yerba-mate") == "Yerba y mate"
    assert shelf_label("no-existe") is None
    assert shelf_label(None) is None


def test_store_ids_cubre_las_tres_tiendas():
    """`STORE_IDS` es lo que usan run_scrapers y el optimizador para nombrar la
    misma tienda; una tienda de STORES sin id no se puede persistir."""
    assert set(STORE_IDS) == set(STORES)
