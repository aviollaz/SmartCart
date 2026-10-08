"""
Elegir el día más barato dentro del rango de compra (issue #17).

Puro Python: la matriz de precios y los descuentos bancarios se fabrican, y
`optimize_cart` corre de verdad. Lo único que cambia entre días son los
descuentos, que es exactamente lo que hace `load_bank_promos` con los reales.
"""
from datetime import date

import pytest
from pydantic import ValidationError

import src.api as api
from src.api import OptimizationRequest, _optimize_best_day

COTO = "coto_online"
LUNES = date(2026, 10, 5)
DELIVERY = {COTO: 3000, "dia_online": 3000, "carrefour_online": 3500}
GALICIA_JUEVES = {COTO: [{"card": "galicia", "discount_pct": 20, "cap": 5000,
                          "description": "20% con Galicia", "is_membership": False}]}


@pytest.fixture(autouse=True)
def _mundo_fijo(monkeypatch):
    # Un producto de $20.000 que sólo vende Coto: supera su mínimo de compra y
    # deja una sola asignación posible, así el total depende sólo del descuento.
    flat = {"prod_a": {COTO: {"total_cost": 20000, "effective_unit_price": 20000,
                              "applied_promo_id": None, "promo_description": ""}}}
    monkeypatch.setattr(api, "flatten_cart_prices", lambda *a, **k: flat)
    monkeypatch.setattr(api, "_today_ar", lambda: LUNES)
    monkeypatch.setattr(api, "load_bank_promos",
                        lambda day: GALICIA_JUEVES if day.weekday() == 3 else {})


def _run(purchase_days, cards=("galicia",)):
    request = OptimizationRequest(cart=[{"unified_id": "prod_a", "quantity": 1}],
                                  user_cards=list(cards), purchase_days=purchase_days)
    return _optimize_best_day(request, [{"unified_id": "prod_a", "quantity": 1}],
                              DELIVERY, [], [])


def test_un_solo_dia_es_hoy():
    result, _ = _run(1)
    assert result["purchase_date"] == "2026-10-05"
    assert result["today_total_spent_net"] is None
    assert result["total_spent_net"] == pytest.approx(23000)


def test_elige_el_dia_con_descuento_dentro_del_rango():
    result, promos = _run(7)
    assert result["purchase_date"] == "2026-10-08"  # jueves
    assert result["total_spent_net"] == pytest.approx(19000)  # 20.000 + 3.000 − 4.000
    assert result["today_total_spent_net"] == pytest.approx(23000)
    assert promos is GALICIA_JUEVES


def test_rango_que_no_llega_al_dia_con_descuento_queda_hoy():
    result, _ = _run(3)  # lunes a miércoles
    assert result["purchase_date"] == "2026-10-05"
    assert result["today_total_spent_net"] is None


def test_sin_la_tarjeta_todos_los_dias_empatan_y_gana_hoy():
    result, _ = _run(7, cards=())
    assert result["purchase_date"] == "2026-10-05"
    assert result["today_total_spent_net"] is None


def test_inviable_hoy_no_recorre_los_demas_dias(monkeypatch):
    calls = []
    monkeypatch.setattr(api, "load_bank_promos", lambda day: calls.append(day) or {})
    request = OptimizationRequest(cart=[{"unified_id": "prod_a", "quantity": 1}], purchase_days=7)
    # Coto excluida: el producto se queda sin tienda.
    result, _ = _optimize_best_day(request, [{"unified_id": "prod_a", "quantity": 1}],
                                   DELIVERY, [COTO], [COTO])
    assert result["status"] == "infeasible"
    assert calls == [LUNES]


@pytest.mark.parametrize("days", [0, 8])
def test_rango_fuera_de_limites_es_422(days):
    with pytest.raises(ValidationError):
        OptimizationRequest(cart=[], purchase_days=days)
