"""
Tests de correctitud del optimizador (src/optimizer.py).

A diferencia de tests/test_optimizer.py, que corre contra la base real y por lo
tanto no puede afirmar nada sobre el resultado, acá se parchea
`flatten_cart_prices` con matrices de precios fabricadas. Eso hace los tests
deterministas, sin DB, y permite construir escenarios diseñados para hacer
equivocar al solver.

El caso central es la tensión entre ahorro por ítem y costo de envío: partir el
carrito entre dos supermercados duplica el envío, así que un ahorro chico por
producto no alcanza para justificarlo.
"""
import itertools

import pytest

from src import optimizer as optimizer_module
from src.optimizer import optimize_cart

COTO = "coto_online"
DIA = "dia_online"

# Mismos valores que hardcodea el optimizador; los tests los replican para
# poder calcular el óptimo de forma independiente.
BANK_PROMOS = {
    COTO: {"card": "galicia", "discount_pct": 20, "cap": 5000},
    DIA: {"card": "macro", "discount_pct": 15, "cap": 3000},
}


@pytest.fixture
def fake_prices(monkeypatch):
    """Reemplaza la consulta a la base por una matriz de precios fabricada.

    Se usa como: fake_prices({"prod_a": {COTO: 10000, DIA: 10200}})
    """

    def _install(matrix):
        flat = {
            uid: {
                store: {
                    "total_cost": cost,
                    "effective_unit_price": cost,
                    "applied_promo_id": None,
                    "promo_description": "",
                }
                for store, cost in stores.items()
            }
            for uid, stores in matrix.items()
        }
        monkeypatch.setattr(optimizer_module, "flatten_cart_prices", lambda *a, **k: flat)
        return flat

    return _install


def _cart(*uids, quantity=1):
    return [{"unified_id": uid, "quantity": quantity} for uid in uids]


def _brute_force_optimum(matrix, min_spend, delivery, user_cards):
    """
    Calcula el mínimo real enumerando todas las asignaciones posibles.

    Replica la aritmética entera en centavos del solver (incluida la división
    truncada del descuento bancario) para poder comparar de forma exacta.
    Devuelve (costo_óptimo_en_centavos, cantidad_de_tiendas_activas) o
    (None, None) si ninguna asignación es factible.
    """
    uids = list(matrix)
    options = [[s for s in matrix[uid]] for uid in uids]
    best = None
    best_stores = None

    for assignment in itertools.product(*options):
        subtotals = {store: 0 for store in min_spend}
        for uid, store in zip(uids, assignment):
            subtotals[store] += int(round(matrix[uid][store] * 100))

        active = {s for s in subtotals if subtotals[s] > 0}
        if any(subtotals[s] < int(min_spend[s] * 100) for s in active):
            continue  # no llega al mínimo de compra

        total = 0
        for store in min_spend:
            subtotal = subtotals[store]
            promo = BANK_PROMOS.get(store)
            discount = 0
            if promo and promo["card"] in user_cards:
                discount = min((subtotal * promo["discount_pct"]) // 100, int(promo["cap"] * 100))
            delivery_cents = int(delivery[store] * 100) if store in active else 0
            total += subtotal + delivery_cents - discount

        if best is None or total < best:
            best = total
            best_stores = len(active)

    return best, best_stores


# --------------------------------------------------------------------------
# El caso que motiva estos tests: ahorro por ítem vs. costo del segundo envío
# --------------------------------------------------------------------------

def test_no_divide_cuando_el_segundo_envio_se_come_el_ahorro(fake_prices):
    """
    Cada tienda es más barata en un producto distinto, así que partir el
    carrito parece atractivo mirando solo los precios: ahorra $400 en total.
    Pero abrir la segunda tienda cuesta $3000 de envío extra.
    """
    fake_prices({
        "prod_a": {COTO: 10000, DIA: 10200},
        "prod_b": {COTO: 10200, DIA: 10000},
    })

    result = optimize_cart(
        _cart("prod_a", "prod_b"),
        min_spend_limits={COTO: 5000, DIA: 5000},
        delivery_costs={COTO: 3000, DIA: 3000},
    )

    assert result["status"] == "success"
    assert len(result["split"]) == 1, (
        f"partió el carrito en {len(result['split'])} tiendas: ahorra $400 en productos "
        f"pero paga $3000 de envío extra"
    )
    # Una sola tienda: $20.200 de productos + $3.000 de envío
    assert result["total_spent_net"] == pytest.approx(23200.0)


def test_si_divide_cuando_el_ahorro_supera_el_envio(fake_prices):
    """
    Contraparte del test anterior: si el ahorro justifica el segundo envío, el
    optimizador SÍ tiene que partir. Sin este test, "no partir nunca" pasaría.
    """
    fake_prices({
        "prod_a": {COTO: 10000, DIA: 30000},
        "prod_b": {COTO: 30000, DIA: 10000},
    })

    result = optimize_cart(
        _cart("prod_a", "prod_b"),
        min_spend_limits={COTO: 5000, DIA: 5000},
        delivery_costs={COTO: 3000, DIA: 3000},
    )

    assert result["status"] == "success"
    assert len(result["split"]) == 2
    # $10.000 + $10.000 + dos envíos de $3.000
    assert result["total_spent_net"] == pytest.approx(26000.0)


def test_el_envio_gratis_hace_que_convenga_dividir(fake_prices):
    """Mismo carrito que el primer test, pero sin costo de envío: sin esa
    fricción, el ahorro por ítem manda y conviene partir."""
    fake_prices({
        "prod_a": {COTO: 10000, DIA: 10200},
        "prod_b": {COTO: 10200, DIA: 10000},
    })

    result = optimize_cart(
        _cart("prod_a", "prod_b"),
        min_spend_limits={COTO: 5000, DIA: 5000},
        delivery_costs={COTO: 0, DIA: 0},
    )

    assert result["status"] == "success"
    assert len(result["split"]) == 2
    assert result["total_spent_net"] == pytest.approx(20000.0)


# --------------------------------------------------------------------------
# Mínimos de compra
# --------------------------------------------------------------------------

def test_no_activa_una_tienda_que_no_alcanza_el_minimo(fake_prices):
    """Día es muchísimo más barata, pero el carrito no llega a su mínimo."""
    fake_prices({
        "prod_a": {COTO: 6000, DIA: 1000},
        "prod_b": {COTO: 6000, DIA: 1000},
    })

    result = optimize_cart(
        _cart("prod_a", "prod_b"),
        min_spend_limits={COTO: 5000, DIA: 20000},
        delivery_costs={COTO: 3000, DIA: 3000},
    )

    assert result["status"] == "success"
    assert set(result["split"]) == {COTO}


def test_infeasible_cuando_ninguna_tienda_alcanza_el_minimo(fake_prices):
    fake_prices({"prod_a": {COTO: 1000, DIA: 1000}})

    result = optimize_cart(
        _cart("prod_a"),
        min_spend_limits={COTO: 50000, DIA: 50000},
        delivery_costs={COTO: 3000, DIA: 3000},
    )

    assert result["status"] == "infeasible"


def test_producto_disponible_en_una_sola_tienda_arrastra_el_carrito(fake_prices):
    """
    prod_b solo existe en Día, así que Día se activa sí o sí. Una vez pagado
    ese envío, mover prod_a a Coto exigiría un segundo envío que no se justifica.
    """
    fake_prices({
        "prod_a": {COTO: 9000, DIA: 9500},
        "prod_b": {DIA: 8000},
    })

    result = optimize_cart(
        _cart("prod_a", "prod_b"),
        min_spend_limits={COTO: 5000, DIA: 5000},
        delivery_costs={COTO: 3000, DIA: 3000},
    )

    assert result["status"] == "success"
    assert set(result["split"]) == {DIA}
    assert result["total_spent_net"] == pytest.approx(20500.0)


# --------------------------------------------------------------------------
# Descuentos bancarios
# --------------------------------------------------------------------------

def test_el_tope_del_descuento_bancario_se_respeta(fake_prices):
    """20% de $100.000 son $20.000, pero el tope de Galicia es $5.000."""
    fake_prices({"prod_a": {COTO: 100000}})

    result = optimize_cart(
        _cart("prod_a"),
        user_cards=["galicia"],
        min_spend_limits={COTO: 5000, DIA: 5000},
        delivery_costs={COTO: 3000, DIA: 3000},
    )

    assert result["status"] == "success"
    assert result["split"][COTO]["bank_discount"]["amount"] == pytest.approx(5000.0)
    assert result["total_spent_net"] == pytest.approx(98000.0)


def test_descuento_bancario_por_debajo_del_tope(fake_prices):
    """20% de $10.000 son $2.000, por debajo del tope de $5.000."""
    fake_prices({"prod_a": {COTO: 10000}})

    result = optimize_cart(
        _cart("prod_a"),
        user_cards=["galicia"],
        min_spend_limits={COTO: 5000, DIA: 5000},
        delivery_costs={COTO: 3000, DIA: 3000},
    )

    assert result["split"][COTO]["bank_discount"]["amount"] == pytest.approx(2000.0)
    assert result["total_spent_net"] == pytest.approx(11000.0)


def test_sin_la_tarjeta_no_hay_descuento(fake_prices):
    fake_prices({"prod_a": {COTO: 100000}})

    result = optimize_cart(
        _cart("prod_a"),
        user_cards=[],
        min_spend_limits={COTO: 5000, DIA: 5000},
        delivery_costs={COTO: 3000, DIA: 3000},
    )

    assert result["split"][COTO]["bank_discount"] is None
    assert result["total_spent_net"] == pytest.approx(103000.0)


def test_el_descuento_bancario_puede_justificar_dividir(fake_prices):
    """
    Con dos tarjetas, cada tienda aporta su propio tope de descuento. Partir
    desbloquea los dos topes a la vez, lo que puede compensar el segundo envío.
    """
    matrix = {
        "prod_a": {COTO: 30000, DIA: 30000},
        "prod_b": {COTO: 30000, DIA: 30000},
    }
    fake_prices(matrix)

    min_spend = {COTO: 5000, DIA: 5000}
    delivery = {COTO: 1000, DIA: 1000}
    cards = ["galicia", "macro"]

    result = optimize_cart(
        _cart("prod_a", "prod_b"),
        user_cards=cards,
        min_spend_limits=min_spend,
        delivery_costs=delivery,
    )

    expected, expected_stores = _brute_force_optimum(matrix, min_spend, delivery, cards)
    assert result["status"] == "success"
    assert round(result["total_spent_net"] * 100) == expected
    assert len(result["split"]) == expected_stores


@pytest.mark.parametrize("monto", [100_000, 500_000, 1_000_000, 5_000_000])
def test_un_carrito_grande_con_tarjeta_no_se_vuelve_infeasible(fake_prices, monto):
    """
    Regresión: los dominios de las variables enteras estaban hardcodeados por
    separado, y `subtotal * pct` desbordaba su cota a partir de ~$500.000 con el
    20% de Galicia. El modelo devolvía "infeasible" culpando a los mínimos de
    compra, cuando en realidad el carrito era perfectamente resoluble.
    """
    fake_prices({"prod_a": {COTO: monto}})

    result = optimize_cart(
        _cart("prod_a"),
        user_cards=["galicia"],
        min_spend_limits={COTO: 5000, DIA: 5000},
        delivery_costs={COTO: 3000, DIA: 3000},
    )

    assert result["status"] == "success", f"carrito de ${monto:,} dio infeasible"
    esperado = monto + 3000 - min(monto * 0.20, 5000)
    assert result["total_spent_net"] == pytest.approx(esperado)


# --------------------------------------------------------------------------
# Invariantes estructurales
# --------------------------------------------------------------------------

def test_cada_producto_se_asigna_exactamente_una_vez(fake_prices):
    fake_prices({
        "prod_a": {COTO: 9000, DIA: 9500},
        "prod_b": {COTO: 8000, DIA: 7000},
        "prod_c": {COTO: 5000, DIA: 5000},
    })

    result = optimize_cart(
        _cart("prod_a", "prod_b", "prod_c"),
        min_spend_limits={COTO: 1000, DIA: 1000},
        delivery_costs={COTO: 3000, DIA: 3000},
    )

    assigned = [p["unified_id"] for store in result["split"].values() for p in store["products"]]
    assert sorted(assigned) == ["prod_a", "prod_b", "prod_c"]
    assert len(assigned) == len(set(assigned))


def test_el_total_reportado_coincide_con_la_suma_del_split(fake_prices):
    fake_prices({
        "prod_a": {COTO: 12000, DIA: 30000},
        "prod_b": {COTO: 30000, DIA: 12000},
    })

    result = optimize_cart(
        _cart("prod_a", "prod_b"),
        user_cards=["galicia", "macro"],
        min_spend_limits={COTO: 5000, DIA: 5000},
        delivery_costs={COTO: 3000, DIA: 3000},
    )

    suma = sum(store["store_total"] for store in result["split"].values())
    assert result["total_spent_net"] == pytest.approx(suma)


def test_el_subtotal_por_tienda_coincide_con_sus_productos(fake_prices):
    fake_prices({
        "prod_a": {COTO: 12000, DIA: 30000},
        "prod_b": {COTO: 30000, DIA: 12000},
    })

    result = optimize_cart(
        _cart("prod_a", "prod_b"),
        min_spend_limits={COTO: 5000, DIA: 5000},
        delivery_costs={COTO: 3000, DIA: 3000},
    )

    for store in result["split"].values():
        assert store["subtotal_products"] == pytest.approx(
            sum(p["total_cost"] for p in store["products"])
        )


# --------------------------------------------------------------------------
# Verificación exhaustiva contra fuerza bruta
# --------------------------------------------------------------------------

ESCENARIOS = [
    pytest.param(
        {"prod_a": {COTO: 10000, DIA: 10200}, "prod_b": {COTO: 10200, DIA: 10000}},
        [], id="ahorro-chico-no-justifica-envio",
    ),
    pytest.param(
        {"prod_a": {COTO: 10000, DIA: 30000}, "prod_b": {COTO: 30000, DIA: 10000}},
        [], id="ahorro-grande-justifica-envio",
    ),
    pytest.param(
        {"prod_a": {COTO: 7000, DIA: 6800}, "prod_b": {COTO: 6900, DIA: 7100},
         "prod_c": {COTO: 8000, DIA: 7900}},
        [], id="tres-productos-diferencias-chicas",
    ),
    pytest.param(
        {"prod_a": {COTO: 40000, DIA: 41000}, "prod_b": {COTO: 41000, DIA: 40000}},
        ["galicia", "macro"], id="dos-tarjetas-con-topes",
    ),
    pytest.param(
        {"prod_a": {COTO: 25000, DIA: 24000}, "prod_b": {DIA: 9000},
         "prod_c": {COTO: 11000, DIA: 12000}},
        ["galicia"], id="producto-exclusivo-mas-tarjeta",
    ),
    pytest.param(
        {"prod_a": {COTO: 5000, DIA: 5000}, "prod_b": {COTO: 5000, DIA: 5000},
         "prod_c": {COTO: 5000, DIA: 5000}, "prod_d": {COTO: 5000, DIA: 5000}},
        [], id="empate-total",
    ),
]


@pytest.mark.parametrize("matrix,cards", ESCENARIOS)
def test_coincide_con_el_optimo_por_fuerza_bruta(fake_prices, matrix, cards):
    """
    Enumera todas las asignaciones posibles y verifica que el solver haya
    encontrado exactamente el mínimo, no solo una solución razonable.
    """
    fake_prices(matrix)
    min_spend = {COTO: 5000, DIA: 5000}
    delivery = {COTO: 3000, DIA: 3000}

    result = optimize_cart(
        _cart(*matrix),
        user_cards=cards,
        min_spend_limits=min_spend,
        delivery_costs=delivery,
    )

    expected, expected_stores = _brute_force_optimum(matrix, min_spend, delivery, cards)

    if expected is None:
        assert result["status"] == "infeasible"
        return

    assert result["status"] == "success"
    assert round(result["total_spent_net"] * 100) == expected, (
        f"el solver devolvió {result['total_spent_net']} pero el óptimo real es {expected / 100}"
    )
    assert len(result["split"]) == expected_stores
