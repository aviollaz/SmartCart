"""
Tests del loader de descuentos bancarios (src/bank_promos.py).

Sin red, sin DB: el archivo se fabrica en un tmp_path.

Lo que se protege acá es el contrato con `optimize_cart`, que es implícito y
frágil: la forma exacta del dict, que `discount_pct` sea entero (es coeficiente
de una restricción CP-SAT), que el orden sea el que hace correcta la selección, y
que un archivo ausente o roto no deje al optimizador sin descuentos.
"""
import json
from datetime import date

import pytest

from src.bank_promos import (
    FALLBACK_BANK_PROMOS,
    SIN_TOPE_CAP,
    load_bank_promos,
)

LUNES = date(2026, 8, 3)
MARTES = date(2026, 8, 4)
DOMINGO = date(2026, 8, 9)


def _registro(entidad="galicia", pct=20.0, dias=("lunes",), tope=5000, periodo="transaccion"):
    return {
        "store": "coto_online",
        "entidad": entidad,
        "porcentaje_descuento": pct,
        "dias_validos": list(dias),
        "tope_reintegro": tope,
        "tope_periodo": periodo,
        "descripcion": f"{pct:.0f}% con {entidad}",
        "promo_id": f"coto_{entidad}_{pct:.0f}",
        "texto_legal": "",
        "scraped_at": "2026-08-05T00:00:00+00:00",
    }


def _escribir(tmp_path, promos):
    ruta = tmp_path / "bank_promos.json"
    ruta.write_text(
        json.dumps({"scraped_at": "2026-08-05T00:00:00+00:00", "promos": promos}),
        encoding="utf-8",
    )
    return str(ruta)


# ------------------------------------------------------------------- fail-open

def test_archivo_inexistente_cae_al_fallback(tmp_path):
    """
    Sin el artefacto la app tiene que comportarse como antes de que existiera el
    scraper, no quedarse sin descuentos: el usuario no vería un error, vería
    precios peores sin explicación.
    """
    assert load_bank_promos(today=LUNES, path=str(tmp_path / "no_existe.json")) == FALLBACK_BANK_PROMOS


def test_archivo_corrupto_cae_al_fallback(tmp_path):
    ruta = tmp_path / "roto.json"
    ruta.write_text("{esto no es json", encoding="utf-8")
    assert load_bank_promos(today=LUNES, path=str(ruta)) == FALLBACK_BANK_PROMOS


def test_json_valido_con_forma_inesperada_cae_al_fallback(tmp_path):
    ruta = tmp_path / "otra_forma.json"
    ruta.write_text(json.dumps({"promos": ["una lista, no un dict"]}), encoding="utf-8")
    assert load_bank_promos(today=LUNES, path=str(ruta)) == FALLBACK_BANK_PROMOS


def test_el_fallback_no_se_puede_mutar_desde_afuera(tmp_path):
    """El llamador recibe copias; si no, un cambio suyo se filtra al siguiente request."""
    promos = load_bank_promos(today=LUNES, path=str(tmp_path / "nada.json"))
    promos["coto_online"].append({"card": "intruso"})
    assert len(FALLBACK_BANK_PROMOS["coto_online"]) == 1


# ---------------------------------------------------------------- filtro por día

def test_filtra_por_el_dia_de_hoy(tmp_path):
    """
    El modelo CP-SAT no tiene noción de día: aplica el porcentaje y listo. Si se
    cargaran todos los descuentos, un usuario que compra un lunes vería el ahorro
    del martes y elegiría una tienda por una razón falsa.
    """
    ruta = _escribir(tmp_path, {"coto_online": [
        _registro(entidad="icbc", pct=30, dias=("lunes",)),
        _registro(entidad="naranja_x", pct=25, dias=("martes",)),
    ]})

    del_lunes = load_bank_promos(today=LUNES, path=ruta)
    assert [p["card"] for p in del_lunes["coto_online"]] == ["icbc"]

    del_martes = load_bank_promos(today=MARTES, path=ruta)
    assert [p["card"] for p in del_martes["coto_online"]] == ["naranja_x"]


def test_un_dia_sin_descuentos_devuelve_vacio_y_no_el_fallback(tmp_path):
    """
    Que hoy no haya nada vigente es la respuesta correcta, no una falla. Caer al
    fallback acá inventaría un descuento de Galicia que hoy no rige.
    """
    ruta = _escribir(tmp_path, {"coto_online": [_registro(dias=("lunes",))]})
    assert load_bank_promos(today=DOMINGO, path=ruta) == {}


def test_una_tienda_sin_descuentos_hoy_no_aparece(tmp_path):
    """`bank_promos.get(j, [])` en el optimizador ya cubre las tiendas ausentes."""
    ruta = _escribir(tmp_path, {
        "coto_online": [_registro(dias=("lunes",))],
        "dia_online": [_registro(dias=("martes",))],
    })
    assert set(load_bank_promos(today=LUNES, path=ruta)) == {"coto_online"}


# --------------------------------------------------------- orden y forma del dict

def test_ordena_de_mayor_a_menor_descuento(tmp_path):
    """
    `optimize_cart` elige con `next(p for p in promos if p["card"] in user_cards)`:
    se queda con el PRIMERO que matchea, no con el mejor. Con datos reales hay
    tres promos de Naranja X en Coto (30/25/20), así que el orden ES la selección.
    """
    ruta = _escribir(tmp_path, {"coto_online": [
        _registro(entidad="naranja_x", pct=20, dias=("martes",)),
        _registro(entidad="naranja_x", pct=30, dias=("martes",)),
        _registro(entidad="naranja_x", pct=25, dias=("martes",)),
    ]})
    pcts = [p["discount_pct"] for p in load_bank_promos(today=MARTES, path=ruta)["coto_online"]]
    assert pcts == [30, 25, 20]


def test_discount_pct_es_entero(tmp_path):
    """
    ortools no acepta coeficientes float: optimize_cart hace
    `subtotal_var * discount_pct` dentro de una restricción.
    """
    ruta = _escribir(tmp_path, {"coto_online": [_registro(pct=30.0)]})
    pct = load_bank_promos(today=LUNES, path=ruta)["coto_online"][0]["discount_pct"]
    assert isinstance(pct, int) and pct == 30


def test_sin_tope_se_traduce_a_un_tope_alto_y_no_a_cero(tmp_path):
    """Un cap de 0 anularía el descuento; None rompería la aritmética del modelo."""
    ruta = _escribir(tmp_path, {"coto_online": [_registro(tope=None, periodo=None)]})
    assert load_bank_promos(today=LUNES, path=ruta)["coto_online"][0]["cap"] == SIN_TOPE_CAP


def test_las_claves_son_las_que_espera_el_optimizador(tmp_path):
    ruta = _escribir(tmp_path, {"coto_online": [_registro()]})
    promo = load_bank_promos(today=LUNES, path=ruta)["coto_online"][0]
    assert set(promo) == {"card", "discount_pct", "cap", "description", "is_membership"}


@pytest.mark.parametrize("entidad, es_membresia", [
    ("comunidad_coto", True),
    ("mi_carrefour", True),
    ("galicia", False),
    ("carrefour_banco", False),
])
def test_marca_las_membresias(tmp_path, entidad, es_membresia):
    """
    El optimizador compara las membresías contra user_memberships y las tarjetas
    contra user_cards. Sin esta marca, "Comunidad Coto" se buscaría entre las
    tarjetas y no se aplicaría nunca.
    """
    ruta = _escribir(tmp_path, {"coto_online": [_registro(entidad=entidad)]})
    promo = load_bank_promos(today=LUNES, path=ruta)["coto_online"][0]
    assert promo["is_membership"] is es_membresia


def test_el_fallback_tiene_la_forma_que_consume_el_optimizador():
    """Se usa tal cual cuando no hay archivo, así que no puede divergir."""
    for promos in FALLBACK_BANK_PROMOS.values():
        for promo in promos:
            assert {"card", "discount_pct", "cap", "description"} <= set(promo)
            assert isinstance(promo["discount_pct"], int)
