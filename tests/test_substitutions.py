"""
Tests de src/substitutions.py — el motor de reemplazos comparables.

Puros: no tocan Postgres ni cargan el modelo de embeddings. El cursor es un
doble que devuelve filas inventadas y `flatten_cart_prices` entra por el
parámetro `flatten=` de `build_semantic_suggestions`.

El caso que da razón de ser al módulo es `test_pack_incompatible_*`: antes de
unificar, las sugerencias de api.py no consultaban el formato de pack y
prorrateaban el precio por el peso del nombre. Sobre el catálogo real eso emitía
36 sugerencias que invitaban a cambiar un pack de seis por una unidad suelta
anunciando hasta un 83% de ahorro.
"""
import time

import pytest

from src.substitutions import (
    MAX_ALTERNATIVES_PER_PRODUCT,
    build_semantic_suggestions,
    comparable_candidates,
    equivalent_quantity,
    format_size,
    is_comparable,
    same_pack_format,
    weight_of,
)

COTO = "coto_online"
DIA = "dia_online"
STORES = [COTO, DIA]


# --------------------------------------------------------------------------
# Dobles de prueba
# --------------------------------------------------------------------------

class FakeCursor:
    """
    Cursor con las dos queries del módulo, distinguidas por el SQL: la de filas
    del carrito trae `FROM unified_products` a secas y la de vecinos hace
    `JOIN store_products`. Mismo criterio que el doble de test_strategic_swaps.
    """

    def __init__(self, products, neighbors_by_uid=None):
        self.products = products
        self.neighbors_by_uid = neighbors_by_uid or {}
        self._result = []
        self.queries = []

    def execute(self, sql, params):
        self.queries.append(sql)
        if "JOIN store_products" in sql:
            # Una sola query para todas las anclas: (tiendas, limit, anclas).
            _, limit, anchor_uids = params
            self._result = [
                {**row, "anchor_id": uid}
                for uid in anchor_uids
                for row in self.neighbors_by_uid.get(uid, [])[:limit]
            ]
        else:
            self._result = [self.products[uid] for uid in params[0] if uid in self.products]

    def fetchall(self):
        return self._result


def _row(uid, name, weight=1000.0, unit="g", shelf="leches"):
    return {
        "id": uid,
        "name": name,
        "shelf": shelf,
        "total_volume_weight": weight,
        "unit_type": unit,
        "name_embedding": f"[emb-{uid}]",
    }


def _flatten_from(prices):
    """{uid: costo unitario} -> un `flatten` que cotiza lineal por cantidad."""

    def _fake(items, memberships=None):
        out = {}
        for item in items:
            uid = item["unified_id"]
            if uid not in prices:
                continue
            total = prices[uid] * item["quantity"]
            out[uid] = {
                COTO: {
                    "total_cost": total,
                    "effective_unit_price": prices[uid],
                    "applied_promo_id": None,
                    "promo_description": "",
                }
            }
        return out

    return _fake


def _cart(*pairs):
    return [{"unified_id": uid, "quantity": qty} for uid, qty in pairs]


# --------------------------------------------------------------------------
# Helpers puros (venían de test_strategic_swaps.py, con el código que testean)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("orig, cand, esperado", [
    ((1000.0, "g"), (1000.0, "g"), True),
    ((1000.0, "g"), (900.0, "ml"), True),      # g y ml son intercambiables
    ((1000.0, "ml"), (500.0, "ml"), True),     # el borde inferior entra
    ((1000.0, "ml"), (2000.0, "ml"), True),    # el borde superior entra
    ((1000.0, "ml"), (499.0, "ml"), False),    # media botella no es lo mismo
    ((1000.0, "ml"), (2001.0, "ml"), False),
    ((1.0, "un"), (1.0, "un"), True),          # dos productos por unidad
    ((1000.0, "g"), (1.0, "un"), False),       # peso real vs. tamaño no parseado
    ((1.0, "un"), (1000.0, "g"), False),
])
def test_comparabilidad_de_tamanos(orig, cand, esperado):
    assert is_comparable(orig, cand) is esperado


@pytest.mark.parametrize("weight, unit, esperado", [
    (1000.0, "g", "1 Kg"),
    (1500.0, "ml", "1.5 L"),
    (500.0, "g", "500 g"),
    (900.0, "ml", "900 ml"),
    (1.0, "un", "1 unidad"),
])
def test_formato_de_tamano(weight, unit, esperado):
    assert format_size(weight, unit) == esperado


def test_weight_of_usa_el_fallback_del_parser():
    assert weight_of({"total_volume_weight": None, "unit_type": None}) == (1.0, "un")
    assert weight_of({"total_volume_weight": 0, "unit_type": "g"}) == (1.0, "g")
    assert weight_of({"total_volume_weight": "500.00", "unit_type": "ml"}) == (500.0, "ml")


@pytest.mark.parametrize("a, b, esperado", [
    ("Alfajor Milka Simple Mousse 42 Gr.", "Alfajor Jorgito Negro 40 g", True),
    ("Alfajor MILKA Simple Mousse 42g Display X 6 Un.", "Alfajor Milka Simple Mousse 42 Gr.", False),
    ("Mini Alfajores SHOT Con Maní 19g X 6 Unidades", "Alfajor Con Maní Shot Triple 60 Gr.", False),
    ("Alfajor Block cofler x6 244 grs", "Alfajor Guaymallen x6 300 g", True),
    # Un número seguido de una unidad de magnitud es un tamaño, no un pack.
    ("Harina Caserita x 1 kg", "Harina Pureza 1 Kg", True),
])
def test_formato_de_pack(a, b, esperado):
    assert same_pack_format(a, b) is esperado


# --------------------------------------------------------------------------
# Selección de candidatos
# --------------------------------------------------------------------------

def test_pack_incompatible_se_descarta():
    """
    El caso que motiva el módulo. El display trae seis alfajores y guarda 42 g
    porque es lo que dice el nombre — que es el tamaño de CADA uno, no el total.
    Sin esta guarda el candidato entra, se prorratea contra 42 g y sale un 83%
    de ahorro que no existe.
    """
    ancla = _row("prod_display", "Alfajor MILKA Simple Mousse 42g Display X 6 Un.", 42.0, "g")
    suelto = _row("prod_suelto", "Alfajor Milka Simple Mousse 42 Gr.", 42.0, "g")

    cur = FakeCursor({}, {"prod_display": [suelto]})
    assert comparable_candidates(cur, {ancla["id"]: ancla}, STORES) == {}


def test_pack_igual_se_acepta():
    ancla = _row("prod_a", "Alfajor Block cofler x6 244 grs", 244.0, "g")
    otro = _row("prod_b", "Alfajor Guaymallen x6 250 g", 250.0, "g")

    cur = FakeCursor({}, {"prod_a": [otro]})
    [cand] = comparable_candidates(cur, {ancla["id"]: ancla}, STORES)[ancla["id"]]
    assert cand["uid"] == "prod_b"


def test_tamano_fuera_de_banda_se_descarta():
    ancla = _row("prod_a", "Leche La Serenísima 1 Lt", 1000.0, "ml")
    gigante = _row("prod_b", "Leche La Serenísima 3 Lt", 3000.0, "ml")

    cur = FakeCursor({}, {"prod_a": [gigante]})
    assert comparable_candidates(cur, {ancla["id"]: ancla}, STORES) == {}


def test_candidato_ya_en_el_carrito_se_descarta():
    """
    Un UID repetido rompe el cálculo en silencio: `flatten_cart_prices` resuelve
    la cantidad con la última aparición y `optimize_cart` con la primera.
    """
    ancla = _row("prod_a", "Leche Entera 1 Lt", 1000.0, "ml")
    vecino = _row("prod_b", "Leche Descremada 1 Lt", 1000.0, "ml")

    cur = FakeCursor({}, {"prod_a": [vecino]})
    assert comparable_candidates(cur, {ancla["id"]: ancla}, STORES, exclude_uids={"prod_b"}) == {}


def test_la_query_de_vecinos_filtra_por_stock_y_tienda():
    """
    El filtro en SQL no es cosmético: `get_market_prices_for_cart` filtra
    `in_stock`, así que un candidato sin stock desaparecía solo pero recién
    después de haber ocupado un lugar del LIMIT.
    """
    ancla = _row("prod_a", "Leche Entera 1 Lt", 1000.0, "ml")
    cur = FakeCursor({}, {"prod_a": []})
    comparable_candidates(cur, {ancla["id"]: ancla}, STORES)

    [sql] = cur.queries
    assert "sp.in_stock = TRUE" in sql
    assert "sp.store_id = ANY(%s)" in sql


# --------------------------------------------------------------------------
# build_semantic_suggestions
# --------------------------------------------------------------------------

def test_sugerencia_basica_ahorro_real():
    """1 x 950 ml a $900 contra 1 x 1 L a $500: el ahorro es la diferencia real."""
    ancla = _row("prod_a", "Aceite Girasol Marca A 950 Ml", 950.0, "ml")
    barato = _row("prod_b", "Aceite Girasol Marca B 1 Lt", 1000.0, "ml")

    cur = FakeCursor({"prod_a": ancla}, {"prod_a": [barato]})
    grupos = build_semantic_suggestions(
        cur, _cart(("prod_a", 1)),
        target_stores=STORES,
        flatten=_flatten_from({"prod_a": 900.0, "prod_b": 500.0}),
    )

    [grupo] = grupos
    assert grupo["original_uid"] == "prod_a"
    assert grupo["original_quantity"] == 1
    assert grupo["original_size"] == "950 ml"
    [alt] = grupo["alternatives"]
    assert alt["suggested_uid"] == "prod_b"
    assert alt["suggested_quantity"] == 1
    assert alt["suggested_size"] == "1 L"
    assert alt["savings"] == pytest.approx(400.0)


def test_cambia_la_cantidad_para_llevar_lo_mismo():
    """3 x 1 L -> 2 x 1,5 L: misma cantidad total, cotizado a 2 unidades."""
    ancla = _row("prod_a", "Gaseosa Cola 1 Lt", 1000.0, "ml")
    grande = _row("prod_b", "Gaseosa Cola 1.5 Lt", 1500.0, "ml")

    cur = FakeCursor({"prod_a": ancla}, {"prod_a": [grande]})
    [grupo] = build_semantic_suggestions(
        cur, _cart(("prod_a", 3)),
        target_stores=STORES,
        flatten=_flatten_from({"prod_a": 2000.0, "prod_b": 2000.0}),
    )

    [alt] = grupo["alternatives"]
    assert alt["suggested_quantity"] == 2
    assert alt["savings"] == pytest.approx(3 * 2000.0 - 2 * 2000.0)


@pytest.mark.parametrize("peso_cand", [1500.0, 700.0])
def test_sin_cantidad_equivalente_no_sugiere(peso_cand):
    """
    1 x 1 L contra 1,5 L (o 700 ml): más barato por litro, pero no hay una
    cantidad entera que lleve lo mismo, así que el ticket cambiaría.
    """
    ancla = _row("prod_a", "Gaseosa Cola 1 Lt", 1000.0, "ml")
    otro = _row("prod_b", "Gaseosa Cola Otra", peso_cand, "ml")

    cur = FakeCursor({"prod_a": ancla}, {"prod_a": [otro]})
    grupos = build_semantic_suggestions(
        cur, _cart(("prod_a", 1)),
        target_stores=STORES,
        flatten=_flatten_from({"prod_a": 5000.0, "prod_b": 100.0}),
    )

    assert grupos == []


@pytest.mark.parametrize("orig, qty, cand, esperado", [
    ((1000.0, "ml"), 3, (1500.0, "ml"), 2),
    ((1000.0, "ml"), 3, (500.0, "ml"), 6),
    ((1000.0, "ml"), 1, (1500.0, "ml"), None),
    ((1000.0, "ml"), 1, (950.0, "ml"), 1),     # 5%: dentro de la tolerancia
    ((1.0, "un"), 4, (1.0, "un"), 4),          # sin tamaño: misma cantidad
])
def test_cantidad_equivalente(orig, qty, cand, esperado):
    assert equivalent_quantity(orig, qty, cand) == esperado


def test_pack_incompatible_no_llega_a_sugerencia():
    """El mismo caso del display, ahora end-to-end."""
    ancla = _row("prod_display", "Alfajor MILKA Simple Mousse 42g Display X 6 Un.", 42.0, "g")
    suelto = _row("prod_suelto", "Alfajor Milka Simple Mousse 42 Gr.", 42.0, "g")

    cur = FakeCursor({"prod_display": ancla}, {"prod_display": [suelto]})
    grupos = build_semantic_suggestions(
        cur, _cart(("prod_display", 1)),
        target_stores=STORES,
        flatten=_flatten_from({"prod_display": 8743.0, "prod_suelto": 1510.0}),
    )

    assert grupos == []


def test_ahorro_por_debajo_del_umbral_no_sugiere():
    ancla = _row("prod_a", "Aceite Marca A 1 Lt", 1000.0, "ml")
    apenas = _row("prod_b", "Aceite Marca B 1 Lt", 1000.0, "ml")

    cur = FakeCursor({"prod_a": ancla}, {"prod_a": [apenas]})
    grupos = build_semantic_suggestions(
        cur, _cart(("prod_a", 1)),
        target_stores=STORES,
        flatten=_flatten_from({"prod_a": 1000.0, "prod_b": 900.0}),   # 10%
    )

    assert grupos == []


def test_tope_de_alternativas_por_producto():
    ancla = _row("prod_a", "Aceite Marca A 1 Lt", 1000.0, "ml")
    vecinos = [_row(f"prod_{i}", f"Aceite Marca {i} 1 Lt", 1000.0, "ml") for i in range(5)]

    cur = FakeCursor({"prod_a": ancla}, {"prod_a": vecinos})
    precios = {"prod_a": 1000.0}
    precios.update({f"prod_{i}": 500.0 - i for i in range(5)})

    [grupo] = build_semantic_suggestions(
        cur, _cart(("prod_a", 1)),
        target_stores=STORES,
        flatten=_flatten_from(precios),
    )

    alts = grupo["alternatives"]
    assert len(alts) == MAX_ALTERNATIVES_PER_PRODUCT
    assert [a["savings"] for a in alts] == sorted((a["savings"] for a in alts), reverse=True)
    assert len({a["suggested_uid"] for a in alts}) == len(alts)


def test_los_grupos_salen_ordenados_por_su_mejor_ahorro():
    caro = _row("prod_caro", "Aceite Caro 1 Lt", 1000.0, "ml")
    barato = _row("prod_barato", "Leche Cara 1 Lt", 1000.0, "ml")
    alt_caro = _row("prod_alt1", "Aceite Barato 1 Lt", 1000.0, "ml")
    alt_barato = _row("prod_alt2", "Leche Barata 1 Lt", 1000.0, "ml")

    cur = FakeCursor(
        {"prod_caro": caro, "prod_barato": barato},
        {"prod_caro": [alt_caro], "prod_barato": [alt_barato]},
    )
    grupos = build_semantic_suggestions(
        cur, _cart(("prod_barato", 1), ("prod_caro", 1)),
        target_stores=STORES,
        flatten=_flatten_from({
            "prod_caro": 10000.0, "prod_alt1": 5000.0,     # ahorra 5000
            "prod_barato": 1000.0, "prod_alt2": 500.0,     # ahorra 500
        }),
    )

    assert [g["original_uid"] for g in grupos] == ["prod_caro", "prod_barato"]


def test_candidatos_se_cotizan_a_su_cantidad_equivalente():
    """
    Las promos condicionales (3x2, 2da al 50%) recién se activan por encima de su
    umbral, así que un candidato cotizado a q=1 cuando el usuario lleva 3 se
    valora con un precio que no es el que va a pagar. Mismo tamaño: misma
    cantidad.
    """
    ancla = _row("prod_a", "Aceite Marca A 1 Lt", 1000.0, "ml")
    vecino = _row("prod_b", "Aceite Marca B 1 Lt", 1000.0, "ml")

    vistos = []

    def _flatten(items, memberships=None):
        vistos.extend(items)
        return _flatten_from({"prod_a": 1000.0, "prod_b": 400.0})(items, memberships)

    cur = FakeCursor({"prod_a": ancla}, {"prod_a": [vecino]})
    build_semantic_suggestions(
        cur, _cart(("prod_a", 3)), target_stores=STORES, flatten=_flatten,
    )

    assert {"unified_id": "prod_b", "quantity": 3} in vistos


def test_carrito_vacio_no_consulta_nada():
    cur = FakeCursor({}, {})
    assert build_semantic_suggestions(cur, [], target_stores=STORES) == []
    assert cur.queries == []


def test_producto_sin_embedding_se_saltea():
    sin_emb = _row("prod_a", "Aceite Marca A 1 Lt", 1000.0, "ml")
    sin_emb["name_embedding"] = None

    cur = FakeCursor({"prod_a": sin_emb}, {})
    assert build_semantic_suggestions(cur, _cart(("prod_a", 1)), target_stores=STORES) == []


def test_los_precios_de_cada_cantidad_se_piden_a_la_vez():
    # preparar: dos productos cuyas alternativas se cotizan a cantidades distintas
    # (1 x 950 ml -> 1 x 1 L, y 3 x 1 L -> 2 x 1,5 L), así que hay dos consultas de precios
    aceite = _row("prod_a", "Aceite Girasol Marca A 950 Ml", 950.0, "ml")
    aceite_barato = _row("prod_b", "Aceite Girasol Marca B 1 Lt", 1000.0, "ml")
    gaseosa = _row("prod_c", "Gaseosa Cola 1 Lt", 1000.0, "ml")
    gaseosa_grande = _row("prod_d", "Gaseosa Cola 1.5 Lt", 1500.0, "ml")
    cur = FakeCursor({"prod_a": aceite, "prod_c": gaseosa},
                     {"prod_a": [aceite_barato], "prod_c": [gaseosa_grande]})
    precios = _flatten_from({"prod_a": 900.0, "prod_b": 500.0, "prod_c": 2000.0, "prod_d": 1000.0})
    carrito = _cart(("prod_a", 1), ("prod_c", 3))

    def precios_lentos(items, memberships=None):
        time.sleep(0.3)
        return precios(items, memberships)

    # ejecutar
    inicio = time.perf_counter()
    build_semantic_suggestions(cur, carrito, target_stores=STORES, flatten=precios_lentos,
                               cart_prices=precios(carrito))
    duracion = time.perf_counter() - inicio

    # verificar: en fila serían 0,6 s; a la vez, ~0,3 s
    assert duracion < 0.5
