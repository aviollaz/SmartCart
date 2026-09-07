import re

import pytest

from src.scrapers.scraper_coto import _as_price, build_coto_url, resolve_coto_product_id


def test_build_url_del_enunciado():
    url = build_coto_url("Paleta Cocida Feteada Paladini Xkg", "00307037")
    assert url == (
        "https://www.coto.com.ar/productos/"
        "paleta-cocida-feteada-paladini-xkg-"
        "/_/R-00307037-00307037-200"
    )


def test_slug_en_minusculas_con_guiones_y_guion_final():
    url = build_coto_url("Semola Bonalma 500 Grm", "00539894")
    assert "/productos/semola-bonalma-500-grm-/_/" in url


def test_url_none_si_falta_dato():
    assert build_coto_url("", "00539894") is None
    assert build_coto_url("Semola Bonalma", None) is None


def test_id_preferido_a_nivel_item():
    assert resolve_coto_product_id({"id": "00307037"}, {"sku_id": "sku00999999"}) == "00307037"


def test_id_cae_a_sku_id_sin_prefijo():
    assert resolve_coto_product_id({}, {"sku_id": "sku00539894"}) == "00539894"


def test_id_cae_a_regex_sobre_url_vieja():
    prod_data = {"url": "_/R-00543421-00543421-200"}
    assert resolve_coto_product_id({}, prod_data) == "00543421"


def test_id_none_si_no_hay_nada():
    assert resolve_coto_product_id({}, {}) is None


def test_la_url_generada_no_tiene_el_patron_roto():
    """El bug original producía 'https://www.cotodigital.com.ar_/R-...'."""
    url = build_coto_url("Fécula De Papa Dicomere 450g", "00569958")
    assert ".com.ar_/" not in url
    assert url.startswith("https://www.coto.com.ar/productos/")


# --- Saneado del slug -------------------------------------------------------
#
# El slug sale del nombre del producto, que es texto libre de la tienda. Todo
# lo de acá abajo son nombres REALES del catálogo: hasta que se saneó, cada uno
# producía una URL que el CDN de Coto rechaza con 400, y el desglose de
# /optimize abre una pestaña por producto de Coto, así que se veía crudo.
#
# Los fixtures viejos eran todos ASCII alfanumérico, que es exactamente por qué
# el suite era ciego a esta clase entera de falla.


def test_el_porcentaje_no_queda_como_escape_invalido():
    """
    El caso que rompía: "100%" seguido de "-v" es un escape porcentual
    inválido y el CDN contesta 400 Bad Request antes de rutear.
    """
    url = build_coto_url("La Serenisima 100% Vegetal Almendra 1L", "00498602")
    assert "%" not in url
    assert url == (
        "https://www.coto.com.ar/productos/"
        "la-serenisima-100-vegetal-almendra-1l-"
        "/_/R-00498602-00498602-200"
    )


def test_los_acentos_se_bajan_a_ascii_en_vez_de_borrarse():
    """"Fécula" tiene que quedar "fecula", no "fcula"."""
    url = build_coto_url("Fécula De Papa Dicomere 450g", "00569958")
    assert "/productos/fecula-de-papa-dicomere-450g-/_/" in url


@pytest.mark.parametrize(
    "nombre",
    [
        "Yogur Ser 0% Frutilla 190g",          # porcentaje
        "Queso Port Salut / Cremoso Xkg",      # barra: agregaba un segmento
        "Jugo Baggio Multifruta #1 1L",        # numeral: trunca la URL
        "Arroz Gallo Oro 500g + 20% Gratis",   # más y porcentaje
        "Café La Virginia ¿Cuál? 250g",        # signos de pregunta
        "Fideos Matarazzo & Cia 500g",         # ampersand: abría un query param
        "Té Green Hills 25 Saquitos",          # acento
        "Aceite Natura  doble   espacio 900ml",  # espacios repetidos
    ],
)
def test_ningun_nombre_real_produce_caracteres_inseguros(nombre):
    url = build_coto_url(nombre, "00123456")
    ruta = url.removeprefix("https://www.coto.com.ar/productos/")
    slug = ruta.split("/_/")[0]

    # El slug queda con el alfabeto que Coto usa en sus propios links, y sólo
    # con ese: cualquier otro carácter o entra escapado (y hay que escaparlo
    # bien) o rompe la ruta.
    assert re.fullmatch(r"[a-z0-9-]+", slug), slug
    # Y no colapsa en guiones sueltos ni deja uno duplicado.
    assert "--" not in slug
    assert not slug.startswith("-")


def test_slug_conserva_el_guion_final_que_usa_coto():
    url = build_coto_url("Semola Bonalma 500 Grm!!!", "00539894")
    assert "/productos/semola-bonalma-500-grm-/_/" in url


def test_nombre_sin_alfanumericos_no_produce_url():
    """
    Una ruta ".../productos//_/R-..." tiene un segmento vacío y no es mejor que
    no linkear, así que se trata igual que un nombre ausente.
    """
    assert build_coto_url("!!! ???", "00539894") is None


def test_precio_nulo_no_rompe_el_barrido():
    """
    Coto manda `"formatPrice": null` en parte del catálogo. La clave EXISTE, así
    que `float(d.get("formatPrice", 0))` nunca aplicaba el default y levantaba
    TypeError — que el bucle de páginas atrapaba, cortando la categoría a mitad
    y reportándola como exitosa.
    """
    assert _as_price(None) == 0.0
    assert _as_price("") == 0.0
    assert _as_price("no-es-un-numero") == 0.0
    assert _as_price({}) == 0.0


def test_precio_valido_se_conserva():
    assert _as_price("1234.5") == 1234.5
    assert _as_price(1234.5) == 1234.5
    assert _as_price(0) == 0.0
