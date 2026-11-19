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

# Los descuentos reales salen de src/scrapers/bank_promos.json, que cambia cada
# vez que se corre el scraper, así que el oráculo de fuerza bruta no puede
# depender de él: se fija esta tabla, y el fixture de abajo se asegura de que el
# optimizador use ese mismo conjunto.
PROMOS_FIJAS = {
    COTO: [{"card": "galicia", "discount_pct": 20, "cap": 5000,
            "description": "20% de ahorro con Galicia (Tope $5000)"}],
    DIA: [{"card": "macro", "discount_pct": 15, "cap": 3000,
           "description": "15% de ahorro con Macro (Tope $3000)"}],
}


@pytest.fixture(autouse=True)
def _promos_bancarias_fijas(monkeypatch):
    """
    Fija los descuentos bancarios que ve el optimizador.

    Sin esto, estos tests leerían src/scrapers/bank_promos.json —que trae los
    descuentos reales, distintos según el día en que se corran— y el óptimo
    calculado por el oráculo dejaría de coincidir con el del solver.
    """
    monkeypatch.setattr(
        optimizer_module, "load_bank_promos",
        lambda *args, **kwargs: {store: list(promos)
                                 for store, promos in PROMOS_FIJAS.items()},
    )


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


def _brute_force_optimum(matrix, min_spend, delivery, user_cards, max_stores=None, promos=None):
    """
    Calcula el mínimo real enumerando todas las asignaciones posibles.

    Replica la aritmética entera en centavos del solver (incluida la división
    truncada del descuento bancario) para poder comparar de forma exacta.
    Devuelve (costo_óptimo_en_centavos, cantidad_de_tiendas_activas) o
    (None, None) si ninguna asignación es factible. `max_stores` descarta las
    asignaciones que abren más tiendas que el tope, igual que la restricción
    del solver. `promos` (default PROMOS_FIJAS) puede traer varias por tienda:
    se prueba cada una que el usuario tenga y cuyo mínimo se alcance.
    """
    promos = PROMOS_FIJAS if promos is None else promos
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
        if max_stores is not None and len(active) > max_stores:
            continue

        total = 0
        for store in min_spend:
            subtotal = subtotals[store]
            discount = max(
                [min((subtotal * p["discount_pct"]) // 100, int(p["cap"] * 100))
                 for p in promos.get(store, [])
                 if p["card"] in user_cards and subtotal >= int(p.get("min_purchase", 0) * 100)],
                default=0,
            )
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
# Tiendas excluidas (sin cobertura de entrega en la dirección del usuario)
# --------------------------------------------------------------------------

def test_una_tienda_excluida_no_recibe_productos(fake_prices):
    """Coto es más barata en todo, pero no entrega en la dirección."""
    fake_prices({
        "prod_a": {COTO: 5000, DIA: 9000},
        "prod_b": {COTO: 5000, DIA: 9000},
    })

    result = optimize_cart(
        _cart("prod_a", "prod_b"),
        min_spend_limits={COTO: 5000, DIA: 5000},
        delivery_costs={COTO: 3000, DIA: 3000},
        excluded_stores=[COTO],
    )

    assert result["status"] == "success"
    assert set(result["split"]) == {DIA}
    assert result["excluded_stores"] == [COTO]
    # $9.000 + $9.000 + envío de $3.000
    assert result["total_spent_net"] == pytest.approx(21000.0)


def test_producto_solo_en_la_tienda_excluida_explica_el_motivo_real(fake_prices):
    """
    La trampa que motiva la detección previa: sin ella el modelo devuelve
    infeasible y la API culpa a los mínimos de compra, mandando al usuario a
    agregar productos que no pueden arreglar nada.
    """
    fake_prices({
        "prod_a": {COTO: 9000, DIA: 9000},
        "prod_b": {COTO: 8000},
    })

    result = optimize_cart(
        _cart("prod_a", "prod_b"),
        min_spend_limits={COTO: 5000, DIA: 5000},
        delivery_costs={COTO: 3000, DIA: 3000},
        excluded_stores=[COTO],
    )

    assert result["status"] == "infeasible"
    assert result["unavailable_products"] == ["prod_b"]
    assert "mínimo" not in result["message"]
    assert "dirección" in result["message"]


def test_producto_solo_en_una_tienda_que_el_usuario_saco_no_culpa_a_la_direccion(fake_prices):
    """
    Misma trampa, otra causa: si el usuario deshabilitó Coto a mano, "elegí otra
    dirección de entrega" es un consejo que no puede arreglar nada.
    """
    fake_prices({
        "prod_a": {COTO: 9000, DIA: 9000},
        "prod_b": {COTO: 8000},
    })

    result = optimize_cart(
        _cart("prod_a", "prod_b"),
        min_spend_limits={COTO: 5000, DIA: 5000},
        delivery_costs={COTO: 3000, DIA: 3000},
        excluded_stores=[COTO],
        user_excluded_stores=[COTO],
    )

    assert result["status"] == "infeasible"
    assert result["unavailable_products"] == ["prod_b"]
    assert "dirección" not in result["message"]
    assert "habilit" in result["message"]


def test_excluir_la_tienda_mas_barata_cambia_el_optimo(fake_prices):
    """El usuario puede preferir pagar más con tal de no comprar en Coto."""
    fake_prices({
        "prod_a": {COTO: 5000, DIA: 9000},
        "prod_b": {COTO: 5000, DIA: 9000},
    })
    args = dict(min_spend_limits={COTO: 5000, DIA: 5000},
                delivery_costs={COTO: 3000, DIA: 3000})

    libre = optimize_cart(_cart("prod_a", "prod_b"), **args)
    sin_coto = optimize_cart(_cart("prod_a", "prod_b"), excluded_stores=[COTO],
                             user_excluded_stores=[COTO], **args)

    assert set(libre["split"]) == {COTO}
    assert set(sin_coto["split"]) == {DIA}
    assert sin_coto["total_spent_net"] > libre["total_spent_net"]


def test_sin_exclusiones_no_se_culpa_a_la_direccion(fake_prices):
    """
    Un producto sin ofertas en ninguna tienda configurada no tiene nada que ver
    con la dirección de entrega; el mensaje no debe inventar esa explicación.
    """
    fake_prices({"prod_a": {"makro_online": 9000}})

    result = optimize_cart(
        _cart("prod_a"),
        min_spend_limits={COTO: 5000, DIA: 5000},
        delivery_costs={COTO: 3000, DIA: 3000},
    )

    assert result["status"] == "infeasible"
    assert result["unavailable_products"] == ["prod_a"]
    assert "dirección" not in result["message"]


def test_excluir_una_tienda_sin_ofertas_no_cambia_nada(fake_prices):
    """Excluir Coto cuando el carrito ya se resolvía en Día es un no-op."""
    fake_prices({
        "prod_a": {DIA: 9000},
        "prod_b": {DIA: 9000},
    })

    result = optimize_cart(
        _cart("prod_a", "prod_b"),
        min_spend_limits={COTO: 5000, DIA: 5000},
        delivery_costs={COTO: 3000, DIA: 3000},
        excluded_stores=[COTO],
    )

    assert result["status"] == "success"
    assert set(result["split"]) == {DIA}


def test_sin_exclusiones_el_campo_viene_vacio(fake_prices):
    fake_prices({"prod_a": {COTO: 10000, DIA: 12000}})

    result = optimize_cart(
        _cart("prod_a"),
        min_spend_limits={COTO: 5000, DIA: 5000},
        delivery_costs={COTO: 3000, DIA: 3000},
    )

    assert result["excluded_stores"] == []


def test_una_tienda_desconocida_en_excluded_stores_se_ignora(fake_prices):
    """Defensa contra un store_id que no está en min_spend_limits."""
    fake_prices({"prod_a": {COTO: 10000, DIA: 12000}})

    result = optimize_cart(
        _cart("prod_a"),
        min_spend_limits={COTO: 5000, DIA: 5000},
        delivery_costs={COTO: 3000, DIA: 3000},
        excluded_stores=["makro_online"],
    )

    assert result["status"] == "success"
    assert result["excluded_stores"] == []


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


@pytest.mark.parametrize("max_stores", [None, 1])
@pytest.mark.parametrize("matrix,cards", ESCENARIOS)
def test_coincide_con_el_optimo_por_fuerza_bruta(fake_prices, matrix, cards, max_stores):
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
        max_stores=max_stores,
    )

    expected, expected_stores = _brute_force_optimum(matrix, min_spend, delivery, cards, max_stores)

    if expected is None:
        assert result["status"] == "infeasible"
        return

    assert result["status"] == "success"
    assert round(result["total_spent_net"] * 100) == expected, (
        f"el solver devolvió {result['total_spent_net']} pero el óptimo real es {expected / 100}"
    )
    assert len(result["split"]) == expected_stores


# --------------------------------------------------------------------------
# Tope de supermercados (`max_stores`)
# --------------------------------------------------------------------------

def test_tope_de_una_tienda_compra_todo_en_la_mas_barata_para_el_carrito(fake_prices):
    """
    Sin tope conviene partir (el ahorro por producto supera el segundo envío);
    con tope 1 el carrito entero va a una sola tienda y se paga la diferencia.
    """
    fake_prices({
        "prod_a": {COTO: 10000, DIA: 30000},
        "prod_b": {COTO: 30000, DIA: 12000},
    })
    kwargs = dict(min_spend_limits={COTO: 5000, DIA: 5000},
                  delivery_costs={COTO: 3000, DIA: 3000})

    libre = optimize_cart(_cart("prod_a", "prod_b"), **kwargs)
    assert len(libre["split"]) == 2
    assert libre["total_spent_net"] == pytest.approx(28000.0)

    topeado = optimize_cart(_cart("prod_a", "prod_b"), max_stores=1, **kwargs)
    assert topeado["status"] == "success"
    # Coto: 10.000 + 30.000 + 3.000 = 43.000 contra Día: 30.000 + 12.000 + 3.000 = 45.000
    assert list(topeado["split"]) == [COTO]
    assert topeado["total_spent_net"] == pytest.approx(43000.0)


def test_tope_inviable_lo_dice_en_vez_de_pedir_mas_productos(fake_prices):
    """
    Un producto exclusivo de cada tienda obliga a abrir las dos: con tope 1 no
    hay solución, y el mensaje tiene que apuntar al tope, no al mínimo.
    """
    fake_prices({
        "prod_a": {COTO: 10000},
        "prod_b": {DIA: 10000},
    })
    result = optimize_cart(
        _cart("prod_a", "prod_b"),
        min_spend_limits={COTO: 5000, DIA: 5000},
        delivery_costs={COTO: 3000, DIA: 3000},
        max_stores=1,
    )
    assert result["status"] == "infeasible"
    assert "como máximo 1 supermercado" in result["message"]


# --------------------------------------------------------------------------
# Promos con monto mínimo ("20% con MODO en compras de $100.000 o más") y
# elección entre varias tarjetas del usuario en la misma tienda
# --------------------------------------------------------------------------

def _promo(card, pct, cap, minimo=0):
    return {"card": card, "discount_pct": pct, "cap": cap, "min_purchase": minimo,
            "description": f"{pct}% con {card}"}


MODO_CON_MINIMO = _promo("modo", 20, 25000, minimo=100000)


def test_promo_con_minimo_no_aplica_si_el_subtotal_no_llega(fake_prices):
    # preparar
    fake_prices({"prod_a": {COTO: 80000}})

    # ejecutar
    result = optimize_cart(
        _cart("prod_a"), user_cards=["modo"], bank_promos={COTO: [MODO_CON_MINIMO]},
        min_spend_limits={COTO: 5000, DIA: 5000}, delivery_costs={COTO: 3000, DIA: 3000},
    )

    # verificar
    assert result["total_spent_net"] == 83000
    assert result["split"][COTO]["bank_discount"] is None


def test_promo_con_minimo_aplica_al_llegar(fake_prices):
    # preparar
    fake_prices({"prod_a": {COTO: 120000}})

    # ejecutar
    result = optimize_cart(
        _cart("prod_a"), user_cards=["modo"], bank_promos={COTO: [MODO_CON_MINIMO]},
        min_spend_limits={COTO: 5000, DIA: 5000}, delivery_costs={COTO: 3000, DIA: 3000},
    )

    # verificar: 20% de $120.000 = $24.000, bajo el tope de $25.000
    assert result["total_spent_net"] == 120000 + 3000 - 24000
    assert result["split"][COTO]["bank_discount"]["amount"] == 24000


def test_mueve_productos_para_destrabar_una_promo_con_minimo(fake_prices):
    """
    El caso real (Día + Jumbo, nov 2026): Día ya está en su tope, así que
    sacarle un producto no le cuesta descuento, y llevarlo a la otra tienda la
    pasa de los $100.000 y destraba su 20%.
    """
    # preparar: prod_b es $8.000 más barato en Día. Sin el mínimo en juego
    # (20% de $38.000 = $7.600) no conviene moverlo; destrabando los $100.000, sí.
    matrix = {
        "prod_a": {COTO: 70000},
        "prod_b": {DIA: 30000, COTO: 38000},
        "prod_c": {DIA: 200000},
    }
    fake_prices(matrix)
    promos = {COTO: [MODO_CON_MINIMO], DIA: [_promo("modo", 20, 20000)]}
    min_spend, delivery = {COTO: 5000, DIA: 5000}, {COTO: 3000, DIA: 3000}

    # ejecutar
    result = optimize_cart(_cart("prod_a", "prod_b", "prod_c"), user_cards=["modo"], bank_promos=promos,
                           min_spend_limits=min_spend, delivery_costs=delivery)

    # verificar: prod_b se va a Coto; Coto $108.000 - $21.600, Día $200.000 - $20.000
    assert "prod_b" in [p["unified_id"] for p in result["split"][COTO]["products"]]
    assert result["total_spent_net"] == (108000 + 3000 - 21600) + (200000 + 3000 - 20000)


def test_si_no_llega_al_minimo_usa_otra_tarjeta_sin_minimo(fake_prices):
    # preparar: el loader pone MODO primero (mismo %, tope más alto)
    fake_prices({"prod_a": {COTO: 50000}})
    promos = {COTO: [MODO_CON_MINIMO, _promo("naranja_x", 20, 3000)]}

    # ejecutar
    result = optimize_cart(
        _cart("prod_a"), user_cards=["modo", "naranja_x"], bank_promos=promos,
        min_spend_limits={COTO: 5000, DIA: 5000}, delivery_costs={COTO: 3000, DIA: 3000},
    )

    # verificar
    assert result["split"][COTO]["bank_discount"]["card"] == "naranja_x"
    assert result["total_spent_net"] == 50000 + 3000 - 3000


def test_elige_la_promo_que_mas_ahorra_y_no_la_primera(fake_prices):
    # preparar: 30% con tope de $2.000 contra 20% sin tope, en ese orden
    fake_prices({"prod_a": {COTO: 50000}})
    promos = {COTO: [_promo("icbc", 30, 2000), _promo("galicia", 20, 100_000_000)]}

    # ejecutar
    result = optimize_cart(
        _cart("prod_a"), user_cards=["icbc", "galicia"], bank_promos=promos,
        min_spend_limits={COTO: 5000, DIA: 5000}, delivery_costs={COTO: 3000, DIA: 3000},
    )

    # verificar
    assert result["split"][COTO]["bank_discount"]["card"] == "galicia"
    assert result["total_spent_net"] == 50000 + 3000 - 10000


@pytest.mark.parametrize("matrix", [
    {"a": {COTO: 60000, DIA: 58000}, "b": {COTO: 45000, DIA: 47000}, "c": {COTO: 9000, DIA: 8000}},
    {"a": {COTO: 30000}, "b": {DIA: 25000}, "c": {COTO: 12000, DIA: 11000}},
    {"a": {COTO: 70000, DIA: 72000}, "b": {DIA: 30000, COTO: 36000}, "c": {DIA: 5000, COTO: 5500}},
])
def test_coincide_con_la_fuerza_bruta_con_promos_con_minimo(fake_prices, matrix):
    # preparar
    fake_prices(matrix)
    promos = {
        COTO: [MODO_CON_MINIMO, _promo("naranja_x", 20, 3000)],
        DIA: [_promo("modo", 15, 15000, minimo=35000), _promo("icbc", 30, 4000)],
    }
    cards = ["modo", "naranja_x", "icbc"]
    min_spend, delivery = {COTO: 5000, DIA: 5000}, {COTO: 3000, DIA: 2500}

    # ejecutar
    result = optimize_cart(_cart(*matrix), user_cards=cards, bank_promos=promos,
                           min_spend_limits=min_spend, delivery_costs=delivery)

    # verificar
    expected, expected_stores = _brute_force_optimum(matrix, min_spend, delivery, cards, promos=promos)
    assert round(result["total_spent_net"] * 100) == expected
    assert len(result["split"]) == expected_stores
