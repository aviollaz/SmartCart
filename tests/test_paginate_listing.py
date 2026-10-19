"""
Suite pura de `_paginate_listing` (src/api.py): el filtrado, las facetas y la
paginación de /search y /category.

Sin base y sin modelo: se le pasan filas de unified_products y ofertas ya
armadas, que es exactamente lo que recibe en producción.
"""
from src.api import _paginate_listing


def _fila(uid, brand="Marca A"):
    return {
        "id": uid, "ean": None, "name": f"Producto {uid}", "brand": brand,
        "shelf": "te-e-infusiones", "unit_type": "un", "total_volume_weight": 1.0,
        "is_gluten_free": False, "is_vegan": False, "distance": 0.0, "store_count": 1,
    }


def _oferta(store_id, base_price, promo=None, in_stock=True):
    return {
        "store_id": store_id, "product_url": None, "base_price": base_price,
        "in_stock": in_stock, "image_url": None, "promotions": [],
        "promo_unit_price": promo, "promo_description": None,
    }


def _params(**overrides):
    params = {
        "page": 1, "page_size": 48, "brands": [], "stores": [], "price_min": None,
        "price_max": None, "sort": "relevance", "hidden_stores": [],
    }
    params.update(overrides)
    return params


def _ids(page):
    return [p["unified_id"] for p in page["items"]]


def test_las_marcas_cuentan_el_universo_y_no_la_pagina():
    """El bug que esto arregla: una marca fuera de la página 1 no existía para el filtro."""
    filas = [_fila(f"p{i}", "Marca A") for i in range(5)] + [_fila("p5", "Marca B")]
    ofertas = {f["id"]: [_oferta("coto_online", 100.0)] for f in filas}

    page = _paginate_listing(filas, ofertas, _params(page_size=2))

    assert _ids(page) == ["p0", "p1"]
    assert page["total"] == 6
    assert page["brands"] == [{"brand": "Marca A", "count": 5}, {"brand": "Marca B", "count": 1}]


def test_elegir_una_marca_no_la_saca_del_resto_del_filtro():
    filas = [_fila("p0", "Marca A"), _fila("p1", "Marca B"), _fila("p2", None)]
    ofertas = {f["id"]: [_oferta("coto_online", 100.0)] for f in filas}

    page = _paginate_listing(filas, ofertas, _params(brands=["Marca B"]))

    assert _ids(page) == ["p1"]
    assert {b["brand"] for b in page["brands"]} == {"Marca A", "Marca B", "Sin marca"}


def test_total_y_corte_de_paginas():
    filas = [_fila(f"p{i}") for i in range(5)]
    ofertas = {f["id"]: [_oferta("coto_online", 100.0)] for f in filas}

    assert _ids(_paginate_listing(filas, ofertas, _params(page=3, page_size=2))) == ["p4"]
    assert _ids(_paginate_listing(filas, ofertas, _params(page=4, page_size=2))) == []


def test_hidden_stores_recalcula_precios_y_descarta_exclusivos():
    filas = [_fila("ambas"), _fila("solo_coto")]
    ofertas = {
        "ambas": [_oferta("coto_online", 50.0), _oferta("dia_online", 80.0)],
        "solo_coto": [_oferta("coto_online", 40.0)],
    }

    page = _paginate_listing(filas, ofertas, _params(hidden_stores=["coto_online"]))

    assert _ids(page) == ["ambas"]
    producto = page["items"][0]
    # min_price se calcula sobre la oferta que quedó, no sobre la de Coto.
    assert producto["min_price"] == 80.0
    assert [o["store_id"] for o in producto["available_at_stores"]] == ["dia_online"]
    assert page["price_bounds"] == [80.0, 80.0]


def test_el_orden_y_el_rango_usan_el_precio_con_promo():
    filas = [_fila("caro_con_promo"), _fila("medio"), _fila("barato")]
    ofertas = {
        "caro_con_promo": [_oferta("coto_online", 500.0, promo=50.0)],
        "medio": [_oferta("coto_online", 200.0)],
        "barato": [_oferta("coto_online", 100.0)],
    }

    page = _paginate_listing(filas, ofertas, _params(sort="price_asc"))
    assert _ids(page) == ["caro_con_promo", "barato", "medio"]
    assert page["price_bounds"] == [50.0, 200.0]

    page = _paginate_listing(filas, ofertas, _params(price_max=150.0))
    assert _ids(page) == ["caro_con_promo", "barato"]


def test_filtro_por_tienda_exige_stock():
    filas = [_fila("p0"), _fila("p1")]
    ofertas = {
        "p0": [_oferta("dia_online", 100.0, in_stock=False)],
        "p1": [_oferta("dia_online", 100.0)],
    }

    assert _ids(_paginate_listing(filas, ofertas, _params(stores=["dia_online"]))) == ["p1"]
