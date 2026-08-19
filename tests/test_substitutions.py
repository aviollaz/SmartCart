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
import pytest

from src.substitutions import (
    MAX_ALTERNATIVES_PER_PRODUCT,
    build_semantic_suggestions,
    comparable_candidates,
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
            anchor_uid = params[2]
            limit = params[4]
            self._result = list(self.neighbors_by_uid.get(anchor_uid, []))[:limit]
        else:
            self._result = [self.products[uid] for uid in params[0] if uid in self.products]

    def fetchall(self):
        return self._result


def _row(uid, name, weight=1000.0, unit="g", tags=("almacen", "lacteos", "leches")):
    return {
        "id": uid,
        "name": name,
        "category": "Lácteos",
        "tags": list(tags),
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
    assert comparable_candidates(cur, ancla, STORES) == []


def test_pack_igual_se_acepta():
    ancla = _row("prod_a", "Alfajor Block cofler x6 244 grs", 244.0, "g")
    otro = _row("prod_b", "Alfajor Guaymallen x6 250 g", 250.0, "g")

    cur = FakeCursor({}, {"prod_a": [otro]})
    [cand] = comparable_candidates(cur, ancla, STORES)
    assert cand["uid"] == "prod_b"


def test_tamano_fuera_de_banda_se_descarta():
    ancla = _row("prod_a", "Leche La Serenísima 1 Lt", 1000.0, "ml")
    gigante = _row("prod_b", "Leche La Serenísima 3 Lt", 3000.0, "ml")

    cur = FakeCursor({}, {"prod_a": [gigante]})
    assert comparable_candidates(cur, ancla, STORES) == []


def test_candidato_ya_en_el_carrito_se_descarta():
    """
    Un UID repetido rompe el cálculo en silencio: `flatten_cart_prices` resuelve
    la cantidad con la última aparición y `optimize_cart` con la primera.
    """
    ancla = _row("prod_a", "Leche Entera 1 Lt", 1000.0, "ml")
    vecino = _row("prod_b", "Leche Descremada 1 Lt", 1000.0, "ml")

    cur = FakeCursor({}, {"prod_a": [vecino]})
    assert comparable_candidates(cur, ancla, STORES, exclude_uids={"prod_b"}) == []


def test_la_query_de_vecinos_filtra_por_stock_y_tienda():
    """
    El filtro en SQL no es cosmético: `get_market_prices_for_cart` filtra
    `in_stock`, así que un candidato sin stock desaparecía solo pero recién
    después de haber ocupado un lugar del LIMIT.
    """
    ancla = _row("prod_a", "Leche Entera 1 Lt", 1000.0, "ml")
    cur = FakeCursor({}, {"prod_a": []})
    comparable_candidates(cur, ancla, STORES)

    [sql] = cur.queries
    assert "sp.in_stock = TRUE" in sql
    assert "sp.store_id = ANY(%s)" in sql


# --------------------------------------------------------------------------
# build_semantic_suggestions
# --------------------------------------------------------------------------

def test_sugerencia_basica_con_prorrateo():
    """900 ml a $900 contra 1000 ml a $500 -> el prorrateado sale $450."""
    ancla = _row("prod_a", "Aceite Girasol Marca A 900 Ml", 900.0, "ml")
    barato = _row("prod_b", "Aceite Girasol Marca B 1 Lt", 1000.0, "ml")

    cur = FakeCursor({"prod_a": ancla}, {"prod_a": [barato]})
    grupos = build_semantic_suggestions(
        cur, _cart(("prod_a", 1)),
        target_stores=STORES,
        flatten=_flatten_from({"prod_a": 900.0, "prod_b": 500.0}),
    )

    [grupo] = grupos
    assert grupo["original_uid"] == "prod_a"
    [alt] = grupo["alternatives"]
    assert alt["suggested_uid"] == "prod_b"
    assert alt["savings"] == pytest.approx(900.0 - 450.0)
    assert alt["metric_info"] == "a igual cantidad de 900 ml"


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


def test_candidatos_se_cotizan_a_la_cantidad_del_ancla():
    """
    Las promos condicionales (3x2, 2da al 50%) recién se activan por encima de su
    umbral, así que un candidato cotizado a q=1 cuando el usuario lleva 3 se
    valora con un precio que no es el que va a pagar.
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
