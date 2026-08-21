"""
Tests de los tags estrictos de categoría. Corren contra los dumps reales de
taxonomía (src/scrapers/*_categories.json), sin base de datos ni modelo.
"""
import pytest

from src.category_tags import category_label, filter_tags, tags_for_category
from src.shelves import keys_for_store

# Las categorías que efectivamente se barren. Se leen de la tabla de góndolas en
# vez de copiarse acá: una copia se desactualiza sin que ningún test falle, que
# es justo lo que estos casos tendrían que detectar.
COTO_MVP = keys_for_store("coto")
DIA_MVP = keys_for_store("dia")
CARREFOUR_MVP = keys_for_store("carrefour")


@pytest.mark.parametrize("category_id", COTO_MVP)
def test_todas_las_categorias_mvp_de_coto_resuelven(category_id):
    assert tags_for_category("coto", category_id)


@pytest.mark.parametrize("slug", DIA_MVP)
def test_todas_las_categorias_mvp_de_dia_resuelven(slug):
    assert tags_for_category("dia", slug)


@pytest.mark.parametrize("slug", CARREFOUR_MVP)
def test_todas_las_categorias_mvp_de_carrefour_resuelven(slug):
    assert tags_for_category("carrefour", slug)


def test_tags_son_segmentos_slugificados():
    assert tags_for_category("coto", "catv00003596") == ["almacen", "golosinas", "alfajores"]


def test_slug_multipalabra_usa_guiones():
    assert tags_for_category("dia", "almacen/aceites-y-aderezos") == ["almacen", "aceites-y-aderezos"]


def test_clave_desconocida_devuelve_lista_vacia():
    """Para que los scrapers caigan al comportamiento anterior en vez de romper."""
    assert tags_for_category("coto", "catv00000000") == []
    assert tags_for_category("tienda_inexistente", "lo-que-sea") == []


def test_category_label_es_la_hoja():
    assert category_label("coto", "catv00003596") == "Alfajores"
    assert category_label("coto", "catv00000000") is None


def test_filter_tags_descarta_el_top_level():
    """Sin esto 'almacen' matchearía contra medio catálogo."""
    assert filter_tags(["almacen", "golosinas", "alfajores"]) == ["golosinas", "alfajores"]


def test_filter_tags_vacio_si_no_alcanza_la_profundidad():
    assert filter_tags(None) == []
    assert filter_tags([]) == []
    assert filter_tags(["almacen"]) == []


def _solapan(a, b):
    """Réplica en Python del operador && de Postgres que usa api.py."""
    return bool(set(filter_tags(a)) & set(filter_tags(b)))


def test_leche_de_coto_y_de_dia_son_sustituibles_pese_a_distinta_profundidad():
    """
    Coto anida "Frescos -> Lácteos -> Leches" y Día "Frescos -> Leches".
    Un filtro por prefijo de rama fallaría acá; el solapamiento no.
    """
    coto = tags_for_category("coto", "catv00003266")
    dia = tags_for_category("dia", "frescos/leches")
    assert len(coto) != len(dia), "el test pierde sentido si ambas tienen la misma profundidad"
    assert _solapan(coto, dia)


def test_alfajores_de_ambas_tiendas_son_sustituibles():
    coto = tags_for_category("coto", "catv00003596")
    dia = tags_for_category("dia", "almacen/golosinas-y-alfajores/alfajores")
    assert _solapan(coto, dia)


def test_aderezos_y_carnes_no_colisionan():
    """La colisión que motivó el refactor: mayonesa sugerida para reemplazar carne."""
    aderezos = tags_for_category("dia", "almacen/aceites-y-aderezos")   # Almacén -> Aceites y Aderezos
    carnes = tags_for_category("coto", "catv00001460")                  # Frescos -> Carniceria -> Carnes

    assert aderezos and carnes, "ambas categorías deben existir en la taxonomía"
    assert not _solapan(aderezos, carnes)


def test_el_top_level_compartido_no_alcanza_para_solapar():
    """Harinas y alfajores comparten 'almacen', pero no son sustituibles."""
    harinas = tags_for_category("coto", "catv00001412")
    alfajores = tags_for_category("coto", "catv00003596")

    assert harinas[0] == alfajores[0] == "almacen"
    assert not _solapan(harinas, alfajores)


def test_la_puntuacion_no_sobrevive_al_slug():
    """
    "Sal, aderezos y saborizadores" salía como `sal,-aderezos-y-saborizadores`.
    Un tag con coma adentro no rompe nada visible: simplemente no matchea nunca
    con el && de Postgres, que es la peor forma de fallar.
    """
    tags = tags_for_category("carrefour", "almacen/sal-aderezos-y-saborizadores")

    assert tags == ["almacen", "sal-aderezos-y-saborizadores"]
    assert not any("," in t for t in tags)


def test_ninguna_categoria_scrapeada_produce_un_tag_con_puntuacion():
    for store, claves in (("coto", COTO_MVP), ("dia", DIA_MVP), ("carrefour", CARREFOUR_MVP)):
        for clave in claves:
            for tag in tags_for_category(store, clave):
                assert tag == tag.strip("-")
                assert all(c.isalnum() or c == "-" for c in tag), f"{store}/{clave}: {tag}"
