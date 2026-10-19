"""
Rango de compra: cada tienda en su mejor día (issue #17).

Puro Python: la matriz de precios y los descuentos bancarios se fabrican, y
`optimize_cart` corre de verdad. Lo único que cambia entre días son los
descuentos, que es exactamente lo que hace `load_bank_promos` con los reales.
"""
from datetime import date

import pytest
from pydantic import ValidationError

import src.api as api
from src.api import OptimizationRequest, _optimize_purchase_window
from src.optimizer import DEFAULT_DELIVERY_COSTS

COTO, DIA = "coto_online", "dia_online"
LUNES = date(2026, 10, 5)
DELIVERY = DEFAULT_DELIVERY_COSTS
CART = [{"unified_id": "prod_a", "quantity": 1}, {"unified_id": "prod_b", "quantity": 1}]


def _promo(card, pct, cap):
    return {"card": card, "discount_pct": pct, "cap": cap,
            "description": f"{pct}% con {card}", "is_membership": False}


# Galicia en Coto los jueves, Macro en Día los martes.
PROMOS_POR_DIA = {3: {COTO: [_promo("galicia", 20, 5000)]},
                  1: {DIA: [_promo("macro", 10, 5000)]}}


def _cell(cost):
    return {"total_cost": cost, "effective_unit_price": cost,
            "applied_promo_id": None, "promo_description": ""}


@pytest.fixture(autouse=True)
def _mundo_fijo(monkeypatch):
    # Cada producto lo vende una sola tienda y supera su mínimo: el split es
    # fijo (Coto + Día) y el total depende sólo de los descuentos.
    flat = {"prod_a": {COTO: _cell(25000)}, "prod_b": {DIA: _cell(25000)}}
    monkeypatch.setattr(api, "flatten_cart_prices", lambda *a, **k: flat)
    monkeypatch.setattr(api, "_today_ar", lambda: LUNES)
    monkeypatch.setattr(api, "load_bank_promos",
                        lambda day: PROMOS_POR_DIA.get(day.weekday(), {}))


def _run(purchase_days, cards=("galicia", "macro"), excluded=()):
    request = OptimizationRequest(cart=CART, user_cards=list(cards), purchase_days=purchase_days)
    result, _ = _optimize_purchase_window(request, CART, DELIVERY, list(excluded), list(excluded))
    return result


SIN_DESCUENTO = 25000 * 2 + 3000 * 2


def test_un_solo_dia_es_hoy():
    result = _run(1)
    assert result["total_spent_net"] == pytest.approx(SIN_DESCUENTO)
    assert result["today_total_spent_net"] is None
    assert all(not c.get("purchase_date") for c in result["split"].values())


def test_cada_tienda_en_su_dia():
    result = _run(7)
    assert result["split"][COTO]["purchase_date"] == "2026-10-08"  # jueves
    assert result["split"][DIA]["purchase_date"] == "2026-10-06"   # martes
    assert result["total_spent_net"] == pytest.approx(SIN_DESCUENTO - 5000 - 2500)
    assert result["today_total_spent_net"] == pytest.approx(SIN_DESCUENTO)


def test_rango_corto_solo_alcanza_a_una_tienda():
    result = _run(2)  # lunes y martes
    assert result["split"][DIA]["purchase_date"] == "2026-10-06"
    assert result["split"][COTO]["purchase_date"] is None
    assert result["total_spent_net"] == pytest.approx(SIN_DESCUENTO - 2500)


def test_sin_tarjetas_queda_todo_hoy():
    result = _run(7, cards=())
    assert result["today_total_spent_net"] is None
    assert all(not c.get("purchase_date") for c in result["split"].values())


def test_nunca_peor_que_comprar_todo_hoy(monkeypatch):
    # Hoy 20% sin tope; el martes 30% con tope de $500. optimize_cart se queda
    # con el de mayor %, que rinde menos: tiene que ganar comprar hoy.
    monkeypatch.setattr(api, "load_bank_promos", lambda day: {
        0: {COTO: [_promo("galicia", 20, 100_000_000)]},
        1: {COTO: [_promo("galicia", 30, 500)]},
    }.get(day.weekday(), {}))
    result = _run(7)
    assert result["total_spent_net"] == pytest.approx(SIN_DESCUENTO - 5000)
    assert result["today_total_spent_net"] is None


def test_inviable_hoy_no_recorre_los_demas_dias(monkeypatch):
    calls = []
    monkeypatch.setattr(api, "load_bank_promos", lambda day: calls.append(day) or {})
    result = _run(7, excluded=[COTO])  # prod_a se queda sin tienda
    assert result["status"] == "infeasible"
    assert calls == [LUNES]


def test_el_tope_de_supermercados_rige_en_las_dos_corridas(monkeypatch):
    vistos = []
    real = api.optimize_cart
    monkeypatch.setattr(api, "optimize_cart",
                        lambda **k: vistos.append(k["max_stores"]) or real(**k))
    request = OptimizationRequest(cart=CART, user_cards=["galicia", "macro"],
                                  purchase_days=7, max_stores=2)
    _optimize_purchase_window(request, CART, DELIVERY, [], [])
    assert vistos == [2, 2]


@pytest.mark.parametrize("days", [0, 8])
def test_rango_fuera_de_limites_es_422(days):
    with pytest.raises(ValidationError):
        OptimizationRequest(cart=[], purchase_days=days)
