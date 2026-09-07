"""
Suite pura: la normalización del código de barras (`src/ean.py`).

Sin base y sin modelo. Cubre la falla concreta que dejó el barrido nocturno en
PARTIAL tres noches seguidas —Coto publicando el GTIN-14 de la caja contra una
columna VARCHAR(13), que revertía la transacción de la categoría entera— y, sobre
todo, la regla que la acompaña: **un código de 13 o menos se devuelve intacto**.

Esa segunda mitad es la que más vale proteger. Validar check digits sobre los
códigos cortos parece una mejora obvia y no lo es: la base tiene cientos de UPC
con los ceros a la izquierda comidos, las tres cadenas los comen igual y hoy
unifican bien entre sí; revalidarlos les cambiaría el `unified_id` y el barrido de
huérfanos borraría las filas viejas esa misma noche.
"""
import copy

import pytest

from src.ean import normalize_ean
from test_scraper_truncation import (
    CotoScraper,
    _RespuestaFalsa,
    _falsear_coto,
    _respuesta_coto,
)

# Los cinco de la góndola catv00003603 ("Almacén -> Golosinas -> Gomitas y
# Gelatinas"), tal como los devuelve la API de Coto, con el EAN-13 de la unidad de
# consumo que contienen. No son un ejemplo inventado: son exactamente las filas que
# hacían fallar la categoría todas las noches.
GTIN14_REALES = [
    ("77896451909380", "7896451909381"),  # Gomitas Beso Sabor Frutilla Docile 70g
    ("47896451912396", "7896451912398"),  # Gomitas Aros Ácidos Docile 80g
    ("77896451906174", "7896451906175"),  # Gomitas Diente De Vampiro Docile 80g
    ("87896451908625", "7896451908629"),  # Gomitas Culebritas Docile 80g
    ("97896451908813", "7896451908810"),  # Gomitas Sabor Plátano Docile 80g
]

# Códigos cortos sacados de la base de producción: EAN-8 y UPC de 11/12 dígitos.
CORTOS_REALES = [
    "78917286",       # Pastillas Sabor Naranja Docile 14g
    "34000006656",    # Pastillas duo Ice Breakers Strawberry 36 grs
    "654542999775",   # Chocolate Milk Hazelnut Belgium Est 100 Grm
    "7790040997417",  # un EAN-13 cualquiera, el caso mayoritario
]


@pytest.mark.parametrize("crudo, esperado", GTIN14_REALES)
def test_un_gtin14_valido_se_convierte_al_ean13_que_contiene(crudo, esperado):
    assert normalize_ean(crudo) == esperado
    assert len(normalize_ean(crudo)) == 13


@pytest.mark.parametrize("codigo", CORTOS_REALES)
def test_trece_o_menos_pasa_intacto(codigo):
    # El test que impide "mejorar" esto validando check digits: cualquier cambio
    # acá le reescribe el unified_id a cientos de productos que hoy unifican.
    assert normalize_ean(codigo) == codigo


@pytest.mark.parametrize("crudo", [None, "", "   ", "\n"])
def test_vacio_es_none(crudo):
    assert normalize_ean(crudo) is None


def test_un_catorce_con_check_digit_invalido_no_se_convierte():
    # 77896451909380 es válido; cambiarle el último dígito lo vuelve un código que
    # no sabemos leer. Ahí la respuesta correcta es None, no una conversión: si el
    # 14 no es un GTIN-14, el 13 que saldría de él no identifica nada.
    assert normalize_ean("77896451909381") is None


@pytest.mark.parametrize("crudo", [
    "7789645190938X",        # 14 caracteres, no todos dígitos
    "0000000000000000000",   # 19 dígitos
    "no-es-un-codigo-de-barras",
])
def test_lo_que_no_entra_ni_se_convierte_es_none(crudo):
    assert normalize_ean(crudo) is None


@pytest.mark.parametrize("crudo", [c for c, _ in GTIN14_REALES] + CORTOS_REALES)
def test_es_idempotente(crudo):
    # La salida de la conversión tiene que ser un valor estable: un segundo pase
    # (un re-scrapeo sobre datos ya normalizados) no puede moverlo.
    assert normalize_ean(normalize_ean(crudo)) == normalize_ean(crudo)


def test_no_es_numerico_pero_entra_en_la_columna(monkeypatch):
    # Coto manda el EAN como número y el `str()` viejo lo formateaba; que llegue un
    # int no tiene que cambiar nada.
    assert normalize_ean(7790040997417) == "7790040997417"
    assert normalize_ean(77896451909380) == "7896451909381"


def test_el_scraper_de_coto_emite_el_ean13(monkeypatch):
    """
    De extremo a extremo sobre la salida real del scraper, que es la capa donde
    `save_store_products` lo va a leer. Es el mismo patrón de
    tests/test_scraper_ingest_keys.py: el módulo puede estar bien y el scraper
    seguir sin llamarlo.
    """
    pagina = copy.deepcopy(_respuesta_coto([1, 2]))
    pagina["response"]["results"][0]["data"]["product_main_ean"] = "77896451909380"
    pagina["response"]["results"][1]["data"]["product_main_ean"] = "0000000000000000000"

    scraper = CotoScraper()
    _falsear_coto(monkeypatch, scraper, [
        _RespuestaFalsa(200, pagina),
        _RespuestaFalsa(200, _respuesta_coto([])),
    ])

    productos = scraper.scrape_category("catv_123")

    assert [p["ean"] for p in productos] == ["7896451909381", None]
    # El impresentable no se pierde: entra sin EAN y `save_store_products` le arma
    # el unified_id por tienda. No unificar cuesta una comparación; romper el lote
    # de la categoría costaba las 80 filas.
    assert productos[1]["store_sku"] == "sku00000002"
    assert all(p["ean"] is None or len(p["ean"]) <= 13 for p in productos)
