# tests/test_flattener_deserialization.py
"""
Cubre cómo `flatten_cart_prices` deserializa `store_products.promotions_json`.

Existe porque esa columna es `jsonb`: psycopg devuelve una lista de Python ya
deserializada, y el flattener le hacía `json.loads()` encima. El TypeError caía
en un `except Exception: promotions = []`, así que el efecto no era un error
visible sino que NINGUNA promoción se aplicaba, en silencio, en todo el proyecto
(optimizador, baselines y sugerencias incluidos).

Ninguna suite lo detectaba: test_promos.py cubre el parser de promos y
test_optimizer_correctness.py monkeypatchea `flatten_cart_prices` entera, así que
el camino de deserialización no lo tocaba nadie.
"""
import json

import pytest

import src.flattener as flattener


SECOND_UNIT_HALF_OFF = [{
    "type": "conditional_discount",
    "promo_id": "dia_teaser_1",
    "description": "50% de descuento en la 2da unidad",
    "required_quantity": 2,
    "discount_percentage_on_next": 50.0,
    "requires_membership": None,
}]


class _FakeDB:
    """Reemplaza SmartCartDB para no depender de Postgres en esta suite."""

    conn_string = "postgresql://fake"

    def __init__(self, promotions_json):
        self._promotions_json = promotions_json

    def get_market_prices_for_cart(self, unified_ids):
        return [{
            "unified_product_id": unified_ids[0],
            "store_id": "dia_online",
            "base_price": 2805.0,
            "in_stock": True,
            "promotions_json": self._promotions_json,
            "image_url": None,
        }]


def _flatten_with(monkeypatch, promotions_json, quantity):
    monkeypatch.setattr(flattener, "SmartCartDB", lambda: _FakeDB(promotions_json))
    result = flattener.flatten_cart_prices([{"unified_id": "prod_x", "quantity": quantity}])
    return result["prod_x"]["dia_online"]


@pytest.mark.parametrize(
    "promotions_json",
    [
        # Lo que devuelve psycopg para una columna jsonb: lista ya deserializada.
        SECOND_UNIT_HALF_OFF,
        # Fila vieja guardada como texto plano.
        json.dumps(SECOND_UNIT_HALF_OFF),
        # Doble encodeo: el flattener ya toleraba este caso.
        json.dumps(json.dumps(SECOND_UNIT_HALF_OFF)),
    ],
    ids=["jsonb_list", "json_string", "double_encoded_string"],
)
def test_promo_aplica_sea_cual_sea_la_forma_de_promotions_json(monkeypatch, promotions_json):
    flat = _flatten_with(monkeypatch, promotions_json, quantity=2)

    # 2805 (1ra unidad) + 1402.50 (2da al 50%) = 4207.50
    assert flat["total_cost"] == 4207.5
    assert flat["effective_unit_price"] == 2103.75
    assert flat["applied_promo_id"] == "dia_teaser_1"


def test_sin_promociones_cae_al_precio_base(monkeypatch):
    for empty in (None, [], "", "no-es-json"):
        flat = _flatten_with(monkeypatch, empty, quantity=2)
        assert flat["total_cost"] == 5610.0
        assert flat["applied_promo_id"] is None


def test_promo_no_aplica_por_debajo_de_la_cantidad_requerida(monkeypatch):
    flat = _flatten_with(monkeypatch, SECOND_UNIT_HALF_OFF, quantity=1)

    assert flat["total_cost"] == 2805.0
    assert flat["applied_promo_id"] is None
