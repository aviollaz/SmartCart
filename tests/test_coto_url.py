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
