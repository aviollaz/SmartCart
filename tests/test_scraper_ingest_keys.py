"""
Suite pura: que los tres scrapers emitan las dos claves de las que depende el
resto del pipeline, `source_category` y `shelf`.

Es el riesgo silencioso que destapó el barrido de columnas en NULL. Las dos se
leían con `prod.get(...)` defensivo y los dos scrapers VTEX tenían el parámetro
con default `None`, así que un scraper que dejara de mandarlas **no rompía nada**:

* Sin `source_category` se escribe NULL, y a partir de ahí todo barrido parcial
  poda CERO filas reportando `deleted: 0` con `skipped: False` — indistinguible
  de "no se dio de baja nada", porque `source_category = ANY(...)` nunca matchea
  un NULL.
* Sin `shelf` el producto queda sin góndola: desaparece de `GET /category`, no
  puede ser sustituto de nada y nada avisa.

`save_store_products` ahora las exige con `prod['...']` en vez de `.get()`, así
que la falta explota en el ingest; estos tests la atajan un paso antes, sobre la
salida real de cada scraper. Los fixtures son los de test_scraper_truncation.py:
montan respuestas falsas por tienda y ya cubren los tres formatos de payload.
"""
import pytest

from src.shelves import SHELVES, keys_for_store
from test_scraper_truncation import (
    CarrefourScraper,
    CotoScraper,
    DiaScraper,
    _RespuestaFalsa,
    _falsear_coto,
    _falsear_paginas,
    _pagina_vtex,
    _respuesta_coto,
)

# Una clave real de cada tienda, para que la góndola resuelva de verdad y no por
# el camino del None. Salen de la tabla, así que no pueden quedar desactualizadas.
CLAVES = {store: keys_for_store(store)[0] for store in ("coto", "dia", "carrefour")}


def _barrer_coto(monkeypatch):
    scraper = CotoScraper()
    _falsear_coto(monkeypatch, scraper, [
        _RespuestaFalsa(200, _respuesta_coto([1, 2])),
        _RespuestaFalsa(200, _respuesta_coto([])),
    ])
    return scraper.scrape_category(CLAVES["coto"]), CLAVES["coto"], "coto"


def _barrer_dia(monkeypatch):
    scraper = DiaScraper()
    _falsear_paginas(monkeypatch, scraper, [_pagina_vtex([1, 2]), _pagina_vtex([])])
    return scraper.scrape_entire_category(CLAVES["dia"]), CLAVES["dia"], "dia"


def _barrer_carrefour(monkeypatch):
    scraper = CarrefourScraper()
    _falsear_paginas(monkeypatch, scraper, [_pagina_vtex([1, 2]), _pagina_vtex([])])
    return scraper.scrape_entire_category(CLAVES["carrefour"]), CLAVES["carrefour"], "carrefour"


BARRIDOS = (_barrer_coto, _barrer_dia, _barrer_carrefour)


@pytest.mark.parametrize("barrer", BARRIDOS, ids=lambda f: f.__name__)
def test_cada_producto_lleva_la_categoria_de_origen(barrer, monkeypatch):
    productos, clave, _ = barrer(monkeypatch)

    assert productos, "el fixture no produjo productos"
    for prod in productos:
        assert prod["source_category"] == clave


@pytest.mark.parametrize("barrer", BARRIDOS, ids=lambda f: f.__name__)
def test_cada_producto_lleva_su_gondola(barrer, monkeypatch):
    productos, clave, store = barrer(monkeypatch)

    esperada = next(s for s in SHELVES.values() if clave in s.keys_for(store)).slug
    for prod in productos:
        assert prod["shelf"] == esperada


@pytest.mark.parametrize("barrer", BARRIDOS, ids=lambda f: f.__name__)
def test_no_se_emiten_las_claves_que_nadie_persiste(barrer, monkeypatch):
    """
    `category`, `tags` e `is_weighable` salían de los tres scrapers y ninguna
    llegaba a la base: las dos primeras las reemplazó `shelf`, y `is_weighable`
    nunca estuvo en ningún INSERT — se calculaba y se tiraba.
    """
    productos, _, _ = barrer(monkeypatch)

    for prod in productos:
        assert not {"category", "tags", "is_weighable"} & set(prod)
