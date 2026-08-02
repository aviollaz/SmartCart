# tests/test_flattener_quantity_math.py
"""
Cómo escala el precio con la cantidad, y qué queda aislado por tienda.

Los tres casos de acá salieron de bugs reportados sobre las cards de producto
(capturas en docs/references/). Dos resultaron ser de presentación en React,
pero uno era matemática del backend, así que los tres quedan clavados acá para
que la próxima vez no haya que volver a diagnosticar de qué lado estaba.

Los valores son los de los productos reales de las capturas.
"""
import pytest

import src.flattener as flattener


# "50% 2da Llevando 2" de Coto sobre Dulce de leche repostero VACALIN 1Kg.
# OJO: discount_price_per_unit NO es "cada unidad sale 5430". Es el promedio por
# unidad llevando exactamente 2: (7240 + 3620) / 2. De ahí que multiplicarlo por
# q regalara el descuento a las unidades sueltas.
COTO_FLAT_BASE = 7240.0
COTO_FLAT_PROMO = [{
    "type": "conditional_discount_flat",
    "promo_id": "coto_36637723",
    "description": "50% 2da Llevando 2",
    "required_quantity": 2,
    "regular_price": 7240.0,
    "discount_price_per_unit": 5430.0,
    "requires_membership": None,
}]

# "50%Dto" de Coto sobre Mini Torta Rellena Aires De Luján 30g.
COTO_DIRECT_BASE = 476.0
COTO_DIRECT_PROMO = [{
    "type": "direct_discount",
    "promo_id": "coto_36642871",
    "description": "50%Dto",
    "required_quantity": 1,
    "regular_price": 476.0,
    "discount_price_per_unit": 238.0,
    "requires_membership": None,
}]


class _FakeMultiStoreDB:
    """Una fila por tienda, como devuelve get_market_prices_for_cart()."""

    conn_string = "postgresql://fake"

    def __init__(self, per_store):
        self._per_store = per_store

    def get_market_prices_for_cart(self, unified_ids):
        return [
            {
                "unified_product_id": unified_ids[0],
                "store_id": store_id,
                "base_price": base_price,
                "in_stock": True,
                "promotions_json": promotions,
                "image_url": None,
            }
            for store_id, (base_price, promotions) in self._per_store.items()
        ]


def _flatten(monkeypatch, per_store, quantity):
    monkeypatch.setattr(flattener, "SmartCartDB", lambda: _FakeMultiStoreDB(per_store))
    return flattener.flatten_cart_prices([{"unified_id": "prod_x", "quantity": quantity}])["prod_x"]


# El costo esperado de un descuento por volumen: los grupos completos van al
# precio promocional y el resto a precio de lista. Escrito acá aparte para que el
# test no repita la implementación que está verificando.
def _expected_grouped_cost(q, req_qty, discount_price_per_unit, regular_price):
    return (q // req_qty) * (discount_price_per_unit * req_qty) + (q % req_qty) * regular_price


@pytest.mark.parametrize("q", [1, 2, 3, 4, 5, 6])
def test_volumen_fijo_cobra_el_resto_a_precio_de_lista(monkeypatch, q):
    """
    El bug: con q=3 el unitario se congelaba en 5430 (el de q=2) porque el costo
    se calculaba como discount_price_per_unit * q, o sea la 3ra unidad suelta
    también se llevaba el descuento. Cobraba 16290 en lugar de 18100.
    """
    flat = _flatten(monkeypatch, {"coto_online": (COTO_FLAT_BASE, COTO_FLAT_PROMO)}, q)["coto_online"]

    esperado = _expected_grouped_cost(q, 2, 5430.0, COTO_FLAT_BASE)
    assert flat["total_cost"] == pytest.approx(esperado)
    assert flat["effective_unit_price"] == pytest.approx(round(esperado / q, 2))


def test_volumen_fijo_no_se_congela_en_cantidades_impares(monkeypatch):
    """Versión explícita del caso de la captura, con los números a la vista."""
    dos = _flatten(monkeypatch, {"coto_online": (COTO_FLAT_BASE, COTO_FLAT_PROMO)}, 2)["coto_online"]
    tres = _flatten(monkeypatch, {"coto_online": (COTO_FLAT_BASE, COTO_FLAT_PROMO)}, 3)["coto_online"]

    assert dos["effective_unit_price"] == 5430.0
    assert tres["total_cost"] == 18100.0
    assert tres["effective_unit_price"] == 6033.33
    assert tres["effective_unit_price"] > dos["effective_unit_price"]


@pytest.mark.parametrize("q", [1, 2, 3, 4])
def test_descuento_directo_tiene_unitario_constante(monkeypatch, q):
    """
    Un descuento directo rige desde la primera unidad: el unitario no puede
    moverse con q. La card parecía duplicar el descuento al pasar de 1 a 2, pero
    era que a q=1 no se consultaba el precio y se mostraba el de lista.
    """
    flat = _flatten(monkeypatch, {"coto_online": (COTO_DIRECT_BASE, COTO_DIRECT_PROMO)}, q)["coto_online"]

    assert flat["effective_unit_price"] == 238.0
    assert flat["total_cost"] == pytest.approx(238.0 * q)
    assert flat["applied_promo_type"] == "direct_discount"


def test_la_promo_de_una_tienda_no_toca_la_base_de_la_otra(monkeypatch):
    """
    Cada tienda se evalúa con su propia base y sus propias promos. Coto acá no
    tiene promo, así que tiene que quedar en base * q aunque Día tenga una.
    """
    per_store = {
        "coto_online": (2809.0, []),
        "dia_online": (2805.0, [{
            "type": "conditional_discount",
            "promo_id": "dia_teaser_1",
            "description": "50% de descuento en la 2da unidad",
            "required_quantity": 2,
            "discount_percentage_on_next": 50.0,
            "requires_membership": None,
        }]),
    }
    flat = _flatten(monkeypatch, per_store, 2)

    assert flat["coto_online"]["total_cost"] == 5618.0
    assert flat["coto_online"]["applied_promo_id"] is None
    assert flat["dia_online"]["total_cost"] == 4207.5
    assert flat["dia_online"]["applied_promo_id"] == "dia_teaser_1"


def test_cada_tienda_reporta_su_propio_precio_de_lista(monkeypatch):
    """
    base_unit_price existe para que el frontend tache el precio previo de la
    misma tienda que ganó, en vez de elegir el mínimo entre todas.
    """
    per_store = {
        "coto_online": (6315.0, []),
        "dia_online": (5770.0, []),
    }
    flat = _flatten(monkeypatch, per_store, 2)

    assert flat["coto_online"]["base_unit_price"] == 6315.0
    assert flat["coto_online"]["base_total_cost"] == 12630.0
    assert flat["dia_online"]["base_unit_price"] == 5770.0
    assert flat["dia_online"]["base_total_cost"] == 11540.0


def test_la_cantidad_viaja_en_la_respuesta(monkeypatch):
    """
    El frontend descarta precios calculados para otra cantidad; sin este campo
    no podría distinguirlos y mostraba el unitario viejo con la cantidad nueva.
    """
    flat = _flatten(monkeypatch, {"coto_online": (COTO_FLAT_BASE, COTO_FLAT_PROMO)}, 3)["coto_online"]

    assert flat["quantity"] == 3


# --- Evaluación a q=1, la que usa la grilla del catálogo -------------------
#
# GET /search y GET /category llaman a evaluate_best_promo() con quantity=1 para
# poder mostrar el precio ya descontado en la card, antes de que el producto
# entre al carrito. La regla que tiene que cumplirse es una sola: a una unidad
# solo puede ganar una promo que rija desde la primera. Si una condicional se
# colara acá, la card anunciaría un precio que el usuario no va a pagar.


def test_a_una_unidad_gana_el_descuento_directo():
    best = flattener.evaluate_best_promo(COTO_DIRECT_BASE, COTO_DIRECT_PROMO, 1)

    assert best["total_cost"] == 238.0
    assert best["applied_promo_id"] == "coto_36642871"
    assert best["applied_promo_type"] == "direct_discount"
    assert best["promo_description"] == "50%Dto"


@pytest.mark.parametrize("promociones", [
    COTO_FLAT_PROMO,
    [{
        "type": "conditional_discount",
        "promo_id": "dia_teaser_1",
        "description": "50% de descuento en la 2da unidad",
        "required_quantity": 2,
        "discount_percentage_on_next": 50.0,
    }],
    [{
        "type": "multi_buy",
        "promo_id": "dia_teaser_2",
        "description": "Llevando 3 pagás 2",
        "required_quantity": 3,
        "free_quantity": 1,
    }],
])
def test_a_una_unidad_las_condicionales_no_aplican(promociones):
    best = flattener.evaluate_best_promo(COTO_FLAT_BASE, promociones, 1)

    assert best["total_cost"] == COTO_FLAT_BASE
    assert best["applied_promo_id"] is None
    assert best["applied_promo_type"] is None


def test_una_promo_con_membresia_no_puede_ser_el_precio_de_la_grilla():
    """
    La grilla se pinta anónima (user_memberships vacío). Una promo que exige
    tarjeta o club no puede anunciarse como el precio por defecto.
    """
    promo = [dict(COTO_DIRECT_PROMO[0], requires_membership="club_dia")]

    anonimo = flattener.evaluate_best_promo(COTO_DIRECT_BASE, promo, 1)
    assert anonimo["total_cost"] == COTO_DIRECT_BASE
    assert anonimo["applied_promo_id"] is None

    con_club = flattener.evaluate_best_promo(COTO_DIRECT_BASE, promo, 1, ["club_dia"])
    assert con_club["total_cost"] == 238.0


def test_sin_promociones_devuelve_precio_de_lista():
    for promociones in ([], None):
        best = flattener.evaluate_best_promo(1000.0, promociones, 1)
        assert best["total_cost"] == 1000.0
        assert best["applied_promo_id"] is None
        assert best["promo_description"] == "Precio base sin promociones"
