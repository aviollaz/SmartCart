"""
Comparación por supermercado (src/store_comparison.py y POST /compare).

Puro Python: los precios, los reemplazos y la logística se fabrican, y
`optimize_cart` corre de verdad, porque el total de cada súper tiene que salir
de la misma aritmética que el split.
"""
from contextlib import contextmanager
from datetime import date

import pytest

import src.api as api
from src.optimizer import DEFAULT_DELIVERY_COSTS, DEFAULT_MIN_SPEND_LIMITS
from src.store_comparison import compare_stores, find_replacements

COTO, DIA = "coto_online", "dia_online"
ENVIO = DEFAULT_DELIVERY_COSTS
SIN_PROMOS = [(f"2026-11-{23 + d}", {}) for d in range(7)]


def _cell(cost):
    return {"total_cost": cost, "effective_unit_price": cost,
            "applied_promo_id": None, "promo_description": ""}


def _flat(spec):
    """{uid: {tienda: costo}} -> la forma de flatten_cart_prices."""
    return {uid: {store: _cell(cost) for store, cost in stores.items()} for uid, stores in spec.items()}


def _cart(*uids, quantity=1):
    return [{"unified_id": uid, "quantity": quantity} for uid in uids]


def _option(uid, cost, quantity=1):
    return {"unified_id": uid, "name": f"Producto {uid}", "size": "1 L",
            "quantity": quantity, "offer": _cell(cost)}


def _compare(cart, flat, replacements=None, stores=(COTO,), promos=SIN_PROMOS,
             cards=(), choices=None):
    return compare_stores(
        cart, flat, replacements or {},
        stores=list(stores), delivery_costs=ENVIO,
        user_cards=list(cards), user_memberships=[],
        promos_by_day=promos, replacement_choices=choices,
    )


def _store(result, store_id):
    return next(s for s in result["stores"] if s["store_id"] == store_id)


def _line(store, uid):
    return next(line for line in store["lines"] if line["unified_id"] == uid)


# --------------------------------------------------------------------------
# compare_stores
# --------------------------------------------------------------------------

def test_super_con_todo_el_carrito_cuenta_todo_como_igual():
    # preparar
    flat = _flat({"a": {COTO: 1000}, "b": {COTO: 2000}, "c": {COTO: 3000}})

    # ejecutar
    coto = _store(_compare(_cart("a", "b", "c"), flat), COTO)

    # verificar
    assert (coto["exact"], coto["replaced"], coto["missing"]) == (3, 0, 0)
    assert coto["total"] == 6000 + ENVIO[COTO]


def test_faltante_se_reemplaza_por_el_mas_parecido_aunque_haya_uno_mas_barato():
    # preparar: "x" es el más parecido (primero), "y" el más barato
    flat = _flat({"a": {DIA: 1000}})
    replacements = {DIA: {"b": [_option("x", 2500), _option("y", 1500)]}}

    # ejecutar
    dia = _store(_compare(_cart("a", "b"), flat, replacements, stores=[DIA]), DIA)

    # verificar
    assert _line(dia, "b")["replacement"]["unified_id"] == "x"
    assert dia["total"] == 1000 + 2500 + ENVIO[DIA]


def test_faltante_sin_reemplazo_queda_afuera_del_total_y_se_cuenta():
    # preparar
    flat = _flat({"a": {COTO: 1000}})

    # ejecutar
    coto = _store(_compare(_cart("a", "b"), flat), COTO)

    # verificar
    assert _line(coto, "b")["status"] == "falta"
    assert coto["missing"] == 1
    assert coto["total"] == 1000 + ENVIO[COTO]


def test_super_con_faltantes_no_es_el_mas_barato():
    # preparar: Día sale más barato pero no tiene "b"
    flat = _flat({"a": {COTO: 5000, DIA: 1000}, "b": {COTO: 5000}})

    # ejecutar
    result = _compare(_cart("a", "b"), flat, stores=[COTO, DIA])

    # verificar
    assert result["cheapest"] == COTO


def test_supers_incompletos_van_despues_y_primero_al_que_le_falta_menos():
    # preparar: Coto tiene todo; a Día le falta uno; a Vea dos, pero es el más barato
    VEA = "vea_online"
    flat = _flat({"a": {COTO: 9000, DIA: 5000, VEA: 1000}, "b": {COTO: 9000, DIA: 5000}, "c": {COTO: 9000}})

    # ejecutar
    result = _compare(_cart("a", "b", "c"), flat, stores=[VEA, DIA, COTO])

    # verificar
    assert [s["store_id"] for s in result["stores"]] == [COTO, DIA, VEA]


def test_reemplazo_elegido_por_el_usuario_pisa_el_por_defecto():
    # preparar
    flat = _flat({"a": {DIA: 1000}})
    replacements = {DIA: {"b": [_option("x", 2500), _option("y", 1500)]}}

    # ejecutar
    dia = _store(_compare(_cart("a", "b"), flat, replacements, stores=[DIA],
                          choices={DIA: {"b": "y"}}), DIA)

    # verificar
    assert _line(dia, "b")["replacement"]["unified_id"] == "y"
    assert dia["total"] == 1000 + 1500 + ENVIO[DIA]


def test_elegir_ningun_reemplazo_deja_el_producto_afuera_del_total():
    # preparar: "" es "ninguno"
    flat = _flat({"a": {DIA: 1000}})
    replacements = {DIA: {"b": [_option("x", 2500)]}}

    # ejecutar
    dia = _store(_compare(_cart("a", "b"), flat, replacements, stores=[DIA],
                          choices={DIA: {"b": ""}}), DIA)

    # verificar
    assert _line(dia, "b")["status"] == "falta"
    assert dia["missing"] == 1
    assert dia["total"] == 1000 + ENVIO[DIA]


def test_sin_reemplazo_elegido_las_opciones_siguen_disponibles():
    # preparar
    flat = _flat({"a": {DIA: 1000}})
    replacements = {DIA: {"b": [_option("x", 2500), _option("y", 1500)]}}

    # ejecutar
    dia = _store(_compare(_cart("a", "b"), flat, replacements, stores=[DIA],
                          choices={DIA: {"b": ""}}), DIA)

    # verificar
    assert [o["unified_id"] for o in _line(dia, "b")["alternatives"]] == ["x", "y"]


def test_producto_que_ya_esta_en_el_carrito_no_es_reemplazo():
    # preparar: el candidato más parecido para "b" es "a", que ya está
    flat = _flat({"a": {DIA: 1000}})
    replacements = {DIA: {"b": [_option("a", 1000), _option("x", 2500)]}}

    # ejecutar
    dia = _store(_compare(_cart("a", "b"), flat, replacements, stores=[DIA]), DIA)

    # verificar
    assert _line(dia, "b")["replacement"]["unified_id"] == "x"


def test_un_mismo_reemplazo_no_cubre_dos_faltantes():
    # preparar
    flat = _flat({})
    replacements = {DIA: {"b": [_option("x", 2000), _option("z", 3000)],
                          "c": [_option("x", 2000), _option("z", 3000)]}}

    # ejecutar
    dia = _store(_compare(_cart("b", "c"), flat, replacements, stores=[DIA]), DIA)

    # verificar
    assert _line(dia, "b")["replacement"]["unified_id"] == "x"
    assert _line(dia, "c")["replacement"]["unified_id"] == "z"


def test_carrito_bajo_el_minimo_muestra_cuanto_falta():
    # preparar
    flat = _flat({"a": {COTO: 6000}})

    # ejecutar
    coto = _store(_compare(_cart("a"), flat), COTO)

    # verificar
    assert coto["total"] == 6000 + ENVIO[COTO]
    assert coto["missing_for_min"] == DEFAULT_MIN_SPEND_LIMITS[COTO] - 6000


def test_descuento_bancario_del_usuario_entra_en_el_total_del_super():
    # preparar: 10% con Galicia, tope $500, sobre $10.000 de productos
    galicia = {"card": "galicia", "discount_pct": 10, "cap": 500, "description": "10% Galicia"}
    promos = [("2026-11-23", {COTO: [galicia]})] + SIN_PROMOS[1:]
    flat = _flat({"a": {COTO: 10000}})

    # ejecutar
    coto = _store(_compare(_cart("a"), flat, promos=promos, cards=["galicia"]), COTO)

    # verificar
    assert coto["bank_discount"]["amount"] == 500
    assert coto["total"] == 10000 + ENVIO[COTO] - 500


def test_mejor_dia_aparece_solo_si_es_mas_barato_que_hoy():
    # preparar: Galicia rige el jueves 26, no hoy
    galicia = {"card": "galicia", "discount_pct": 10, "cap": 5000, "description": "10% Galicia"}
    promos = [(d, {COTO: [galicia]} if d == "2026-11-26" else {}) for d, _ in SIN_PROMOS]
    flat = _flat({"a": {COTO: 20000}})

    # ejecutar
    con_tarjeta = _store(_compare(_cart("a"), flat, promos=promos, cards=["galicia"]), COTO)
    sin_tarjeta = _store(_compare(_cart("a"), flat, promos=promos), COTO)

    # verificar
    assert con_tarjeta["best_day"] == {"date": "2026-11-26", "total": 20000 + ENVIO[COTO] - 2000}
    assert sin_tarjeta["best_day"] is None


# --------------------------------------------------------------------------
# find_replacements
# --------------------------------------------------------------------------

class CandidatesCursor:
    """Las dos queries de src/substitutions.py: filas de productos y vecinos."""

    def __init__(self, products, neighbors):
        self.products, self.neighbors = products, neighbors
        self._result = []

    def execute(self, sql, params):
        if "JOIN store_products" in sql:
            _, _, anchors = params
            self._result = [{**row, "anchor_id": uid} for uid in anchors for row in self.neighbors.get(uid, [])]
        else:
            self._result = [self.products[uid] for uid in params[0] if uid in self.products]

    def fetchall(self):
        return self._result


def test_el_reemplazo_se_cotiza_a_su_cantidad_equivalente():
    # preparar: 2 x Leche 1 L, Día sólo tiene la de 2 L
    leche_1l = {"id": "leche_1l", "name": "Leche 1 L", "shelf": "leches",
                "total_volume_weight": 1000.0, "unit_type": "ml", "name_embedding": "[1]"}
    leche_2l = {"id": "leche_2l", "name": "Leche 2 L", "total_volume_weight": 2000.0,
                "unit_type": "ml", "distance": 0.1}
    cur = CandidatesCursor({"leche_1l": leche_1l}, {"leche_1l": [leche_2l]})
    cotizado = []

    def flatten(items, memberships):
        cotizado.extend(items)
        return {"leche_2l": {DIA: _cell(1800 * items[0]["quantity"])}}

    # ejecutar
    options = find_replacements(cur, _cart("leche_1l", quantity=2), {}, [DIA], flatten=flatten)

    # verificar
    assert cotizado == [{"unified_id": "leche_2l", "quantity": 1}]
    assert options[DIA]["leche_1l"][0]["quantity"] == 1
    assert options[DIA]["leche_1l"][0]["offer"]["total_cost"] == 1800


# --------------------------------------------------------------------------
# POST /compare
# --------------------------------------------------------------------------

class LinksCursor:
    """Las queries de links: product_url y store_item_id por tienda."""

    def __init__(self, item_rows=None):
        self.item_rows = item_rows or {}
        self._result = []

    def execute(self, sql, params):
        store_id, uids = params
        if "store_item_id" in sql:
            self._result = [{"unified_product_id": u, "store_item_id": self.item_rows[(store_id, u)]}
                            for u in uids if (store_id, u) in self.item_rows]
        else:
            self._result = []

    def fetchall(self):
        return self._result

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _cubierto(lat, lng, fallback_delivery_cost):
    return {"covered": True, "delivery_cost": fallback_delivery_cost, "source": "fallback"}


@pytest.fixture
def mundo(monkeypatch):
    """Instala precios, reemplazos y cursor; todas las tiendas cubren."""
    for name in ("coto", "dia", "carrefour", "vea", "changomas", "jumbo"):
        monkeypatch.setattr(api, f"resolve_{name}_logistics", _cubierto)
    monkeypatch.setattr(api, "_today_ar", lambda: date(2026, 11, 23))
    monkeypatch.setattr(api, "load_bank_promos", lambda day=None: {})

    def install(flat, replacements=None, item_rows=None):
        monkeypatch.setattr(api, "flatten_cart_prices", lambda *a, **k: flat)
        monkeypatch.setattr(api, "find_replacements", lambda *a, **k: replacements or {})
        cursor = LinksCursor(item_rows)

        @contextmanager
        def fake_connection(conn_string):
            class Conn:
                def cursor(self):
                    return cursor
            yield Conn()

        monkeypatch.setattr(api, "pooled_connection", fake_connection)

    return install


def _post(cart, **kwargs):
    return api.compare_supermarkets(api.CompareRequest(cart=cart, **kwargs))


def test_super_sin_cobertura_o_deshabilitado_no_se_compara(mundo, monkeypatch):
    # preparar
    mundo(_flat({"a": {COTO: 20000, DIA: 20000}}))
    monkeypatch.setattr(api, "resolve_coto_logistics",
                        lambda lat, lng, fallback_delivery_cost: {"covered": False, "delivery_cost": None})

    # ejecutar
    result = _post(_cart("a"), user_excluded_stores=[DIA])

    # verificar
    compared = {s["store_id"] for s in result["stores"]}
    assert COTO not in compared and DIA not in compared


def test_envio_de_dia_por_peso_entra_en_su_total(mundo, monkeypatch):
    # preparar: la cotización por peso da $7.000 contra $3.000 de la zona
    mundo(_flat({"a": {DIA: 20000}}))
    monkeypatch.setattr(api, "resolve_dia_logistics", lambda lat, lng, fallback_delivery_cost: {
        "covered": True, "delivery_cost": 3000, "source": "live", "sucursal": "s1"})
    monkeypatch.setattr(api, "_quote_dia_split", lambda request, sucursal, products: 7000.0)

    # ejecutar
    result = _post(_cart("a"), lat=-34.6, lng=-58.4)

    # verificar
    assert _store(result, DIA)["total"] == 20000 + 7000


def test_link_de_carrito_incluye_los_reemplazos(mundo):
    # preparar
    mundo(_flat({"a": {DIA: 20000}}),
          replacements={DIA: {"b": [_option("x", 2000)]}},
          item_rows={(DIA, "a"): "111", (DIA, "x"): "999"})

    # ejecutar
    result = _post(_cart("a", "b"))

    # verificar
    url = _store(result, DIA)["checkout_url"]
    assert "sku=111" in url and "sku=999" in url


def test_dividir_se_ofrece_si_ahorra_mas_que_el_umbral(mundo):
    # preparar: cada súper es caro en un producto; dividir ahorra ~$37.000
    mundo(_flat({"a": {COTO: 20000, DIA: 60000}, "b": {COTO: 60000, DIA: 20000}}))

    # ejecutar
    offer = _post(_cart("a", "b"))["split_offer"]

    # verificar
    assert set(offer["stores"]) == {COTO, DIA}
    assert offer["saving"] == (80000 + ENVIO[COTO]) - (40000 + ENVIO[COTO] + ENVIO[DIA])


def test_dividir_no_se_ofrece_si_el_ahorro_es_chico(mundo):
    # preparar: dividir ahorra $2.000, bajo el umbral de $15.000
    mundo(_flat({"a": {COTO: 20000, DIA: 25000}, "b": {COTO: 25000, DIA: 20000}}))

    # ejecutar
    offer = _post(_cart("a", "b"))["split_offer"]

    # verificar
    assert offer is None


def test_sin_super_completo_dividir_se_ofrece_sin_ahorro(mundo):
    # preparar: "a" sólo en Coto, "b" sólo en Día, sin reemplazos
    mundo(_flat({"a": {COTO: 20000}, "b": {DIA: 20000}}))

    # ejecutar
    offer = _post(_cart("a", "b"))["split_offer"]

    # verificar
    assert set(offer["stores"]) == {COTO, DIA}
    assert offer["saving"] is None
