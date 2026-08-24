# tests/test_scraper_truncation.py
"""
Suite pura (sin Postgres ni sentence-transformers) de la regla que comparten los
tres scrapers: se corta el barrido de una categoría con `break` SÓLO ante una
página válida y vacía; cualquier otro final anticipado levanta.

Por qué existe: el bucle de páginas tenía varias salidas por error que usaban el
mismo `break` que el final legítimo. La categoría cerraba corta, `_run_store` la
contaba OK, `StoreRunResult.complete` quedaba en True y el pruning borraba como
discontinuado todo lo que el barrido no alcanzó a recorrer. Cada test de acá es
uno de esos caminos.

Los fixtures son inline y recortados a mano de respuestas reales: sólo los campos
que el parser lee.
"""
import pytest

from src.scrapers.errors import CategoryScrapeError
from src.scrapers.scraper_carrefour import CarrefourScraper
from src.scrapers.scraper_coto import CotoScraper
from src.scrapers.scraper_dia import DiaScraper


# --------------------------------------------------------------- fixtures VTEX

def _producto_vtex(sku):
    return {
        "productId": str(sku),
        "productName": f"Producto de prueba {sku} 500 gr",
        "brand": "MarcaTest",
        "link": f"/producto-{sku}/p",
        "categories": ["/Almacén/Snacks/"],
        "properties": [],
        "clusterHighlights": [],
        "items": [{
            "ean": f"779000000{sku:04d}",
            "images": [],
            "sellers": [{"commertialOffer": {"ListPrice": 1000.0, "Price": 1000.0,
                                             "teasers": [], "discountHighlights": []}}],
        }],
    }


def _pagina_vtex(skus, records=None):
    productos = [_producto_vtex(s) for s in skus]
    return {"data": {"productSearch": {
        "recordsFiltered": records if records is not None else len(productos),
        "products": productos,
    }}}


ERRORES_GRAPHQL = {"errors": [{"message": "PersistedQueryNotFound"}]}


def _falsear_paginas(monkeypatch, scraper, paginas):
    """
    Reemplaza `scrape_category_slice` por una secuencia guionada.

    Cada elemento es o un payload a devolver, o una excepción a levantar. Se
    monkeypatchea el método y no el cliente httpx porque lo que se prueba acá es
    el bucle de paginación, no el transporte.
    """
    restantes = list(paginas)

    def fake(_category_query, _from_idx, _to_idx):
        assert restantes, "el bucle pidió más páginas de las guionadas"
        siguiente = restantes.pop(0)
        if isinstance(siguiente, Exception):
            raise siguiente
        return siguiente

    monkeypatch.setattr(scraper, "scrape_category_slice", fake)
    # El barrido real duerme entre páginas; en un test eso es tiempo muerto.
    monkeypatch.setattr("time.sleep", lambda *_: None)


# ---------------------------------------------------------------------- Día


def test_dia_una_pagina_caida_a_mitad_levanta_y_no_devuelve_lo_parcial(monkeypatch):
    # El caso que motiva todo: un 500 pasajero en la página 2. Antes esto
    # devolvía los 2 productos de la página 1 y se reportaba como categoría
    # completa, así que el pruning borraba el resto de la góndola.
    scraper = DiaScraper()
    _falsear_paginas(monkeypatch, scraper, [
        _pagina_vtex([1, 2]),
        CategoryScrapeError("[DÍA] HTTP 500 en la sección 16-31."),
    ])

    with pytest.raises(CategoryScrapeError):
        scraper.scrape_entire_category("almacen/snacks")


def test_dia_detecta_la_persisted_query_rotada(monkeypatch):
    # Día no tenía ninguna validación del payload: leía `data.productSearch` con
    # `.get()` encadenados, así que un 200 con `errors` rendía 0 productos y se
    # interpretaba como "categoría agotada".
    scraper = DiaScraper()
    _falsear_paginas(monkeypatch, scraper, [_pagina_vtex([1, 2]), ERRORES_GRAPHQL])

    with pytest.raises(CategoryScrapeError, match="PersistedQueryNotFound"):
        scraper.scrape_entire_category("almacen/snacks")


def test_dia_la_pagina_vacia_es_el_unico_final_valido(monkeypatch):
    scraper = DiaScraper()
    _falsear_paginas(monkeypatch, scraper, [
        _pagina_vtex([1, 2]),
        _pagina_vtex([3]),
        _pagina_vtex([]),
    ])

    productos = scraper.scrape_entire_category("almacen/snacks")

    assert [p["store_sku"] for p in productos] == ["1", "2", "3"]


def test_dia_una_pagina_que_repite_no_es_un_final(monkeypatch):
    # Si el endpoint deja de respetar el `from`, no sabemos qué falta: es un
    # fallo, no el fin de la categoría.
    scraper = DiaScraper()
    _falsear_paginas(monkeypatch, scraper, [_pagina_vtex([1, 2]), _pagina_vtex([1, 2])])

    with pytest.raises(CategoryScrapeError, match="paginación"):
        scraper.scrape_entire_category("almacen/snacks")


def test_dia_agotar_el_tope_de_paginas_levanta(monkeypatch):
    # Llegar a MAX_PAGES significa que el corte por página vacía nunca llegó: la
    # categoría quedó recorrida a medias.
    from src.scrapers import scraper_dia

    scraper = DiaScraper()
    monkeypatch.setattr(scraper_dia, "MAX_PAGES", 3)
    _falsear_paginas(monkeypatch, scraper, [
        _pagina_vtex([1]), _pagina_vtex([2]), _pagina_vtex([3]),
    ])

    with pytest.raises(CategoryScrapeError, match="tope"):
        scraper.scrape_entire_category("almacen/snacks")


# ---------------------------------------------------------------- Carrefour


def test_carrefour_una_pagina_caida_a_mitad_levanta(monkeypatch):
    scraper = CarrefourScraper()
    _falsear_paginas(monkeypatch, scraper, [
        _pagina_vtex([1, 2], records=100),
        CategoryScrapeError("[CARREFOUR] HTTP 500 en la sección 16-31."),
    ])

    with pytest.raises(CategoryScrapeError):
        scraper.scrape_entire_category("almacen/snacks")


def test_carrefour_detecta_la_persisted_query_rotada_a_mitad(monkeypatch):
    # Carrefour ya detectaba esto y lo logueaba, pero después seguía con un
    # `break`: la categoría se cerraba corta y se reportaba exitosa igual.
    scraper = CarrefourScraper()
    _falsear_paginas(monkeypatch, scraper, [_pagina_vtex([1, 2], records=100), ERRORES_GRAPHQL])

    with pytest.raises(CategoryScrapeError, match="PersistedQueryNotFound"):
        scraper.scrape_entire_category("almacen/snacks")


def test_carrefour_corta_bien_por_records_filtered(monkeypatch):
    # El final legítimo por conteo: 2 productos de 2. No debe levantar.
    scraper = CarrefourScraper()
    _falsear_paginas(monkeypatch, scraper, [_pagina_vtex([1, 2], records=2)])

    productos = scraper.scrape_entire_category("almacen/snacks")

    assert [p["store_sku"] for p in productos] == ["1", "2"]


# --------------------------------------------------------------------- Coto


def _respuesta_coto(skus):
    return {"response": {
        "groups": [{"display_name": "Snacks"}],
        "results": [{
            "id": str(sku),
            "value": f"Producto de prueba {sku} 500 gr",
            "data": {
                "sku_id": f"sku{sku:08d}",
                "product_main_ean": f"779000000{sku:04d}",
                "product_brand": "MarcaTest",
                "price": [{"store": "200", "listPrice": 1000.0, "formatPrice": 1000.0}],
                "in_stock": True,
                "discounts": [],
            },
        } for sku in skus],
    }}


class _RespuestaFalsa:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def _falsear_coto(monkeypatch, scraper, respuestas):
    restantes = list(respuestas)

    def fake_get(_url):
        assert restantes, "el bucle pidió más páginas de las guionadas"
        return restantes.pop(0)

    monkeypatch.setattr(scraper.client, "get", fake_get)
    monkeypatch.setattr("time.sleep", lambda *_: None)


def test_coto_un_http_no_200_a_mitad_levanta(monkeypatch):
    # Coto ya relanzaba las excepciones, pero un 500 no es una excepción: era un
    # `if status != 200: break`, con el mismo efecto silencioso.
    scraper = CotoScraper()
    _falsear_coto(monkeypatch, scraper, [
        _RespuestaFalsa(200, _respuesta_coto([1, 2])),
        _RespuestaFalsa(500),
    ])

    with pytest.raises(CategoryScrapeError, match="HTTP 500"):
        scraper.scrape_category("catv_123")


def test_coto_la_pagina_sin_resultados_es_el_final_valido(monkeypatch):
    scraper = CotoScraper()
    _falsear_coto(monkeypatch, scraper, [
        _RespuestaFalsa(200, _respuesta_coto([1, 2])),
        _RespuestaFalsa(200, _respuesta_coto([])),
    ])

    productos = scraper.scrape_category("catv_123")

    assert [p["store_sku"] for p in productos] == ["sku00000001", "sku00000002"]


def test_coto_una_pagina_que_repite_no_es_un_final(monkeypatch):
    scraper = CotoScraper()
    _falsear_coto(monkeypatch, scraper, [
        _RespuestaFalsa(200, _respuesta_coto([1, 2])),
        _RespuestaFalsa(200, _respuesta_coto([1, 2])),
    ])

    with pytest.raises(CategoryScrapeError, match="paginación"):
        scraper.scrape_category("catv_123")
