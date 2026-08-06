"""
Tests de la heurística de cierre de tienda (src/strategic_swaps.py).

No tocan Postgres ni el modelo de embeddings: se parchea
`flatten_cart_prices` con matrices de precios fabricadas y se pasa un cursor
falso que devuelve vecinos inventados.

Lo que sí corre de verdad es `optimize_cart`: recibe la matriz por el parámetro
`flat_prices`, así que es determinista y no abre conexiones. Eso es deliberado —
el valor de esta heurística depende de que su simulación y el solver den el mismo
número, y un solver mockeado no probaría nada de eso.
"""
import pytest

from src import strategic_swaps as swaps_module
from src.optimizer import optimize_cart
from src.strategic_swaps import find_strategic_swaps

COTO = "coto_online"
DIA = "dia_online"
CARREFOUR = "carrefour_online"

DELIVERY = {COTO: 3000, DIA: 3000, CARREFOUR: 3500}


# --------------------------------------------------------------------------
# Dobles de prueba
# --------------------------------------------------------------------------

class FakeCursor:
    """
    Cursor mínimo con las dos queries que hace el módulo.

    Distingue una de otra por el SQL: la de anclas trae `FROM unified_products`
    a secas y la de vecinos hace `JOIN store_products`.
    """

    def __init__(self, products, neighbors_by_uid, raise_on_query=False):
        self.products = products              # uid -> fila de unified_products
        self.neighbors_by_uid = neighbors_by_uid   # uid ancla -> [filas vecinas]
        self.raise_on_query = raise_on_query
        self._result = []
        self.queries = []

    def execute(self, sql, params):
        if self.raise_on_query:
            raise RuntimeError("la base explotó")

        self.queries.append(sql)

        if "JOIN store_products" in sql:
            anchor_uid = params[2]
            self._result = list(self.neighbors_by_uid.get(anchor_uid, []))
        else:
            self._result = [self.products[uid] for uid in params[0] if uid in self.products]

    def fetchall(self):
        return self._result


def _product(uid, name, weight=1000.0, unit="g", tags=("almacen", "lacteos", "leches")):
    return {
        "id": uid,
        "name": name,
        "category": "Lácteos",
        "tags": list(tags),
        "total_volume_weight": weight,
        "unit_type": unit,
        "name_embedding": f"[emb-{uid}]",
    }


def _matrix(spec):
    """{uid: {store: costo}} -> la forma que devuelve flatten_cart_prices."""
    return {
        uid: {
            store: {
                "total_cost": cost,
                "effective_unit_price": cost,
                "applied_promo_id": None,
                "promo_description": "",
            }
            for store, cost in stores.items()
        }
        for uid, stores in spec.items()
    }


@pytest.fixture
def fake_flatten(monkeypatch):
    """Parchea flatten_cart_prices para que devuelva precios de una matriz fija."""

    calls = []

    def _install(spec):
        matrix = _matrix(spec)

        def _fake(items, memberships=None):
            calls.append(list(items))
            return {i["unified_id"]: matrix[i["unified_id"]]
                    for i in items if i["unified_id"] in matrix}

        monkeypatch.setattr(swaps_module, "flatten_cart_prices", _fake)
        return matrix

    _install.calls = calls
    return _install


def _cart(*pairs):
    return [{"unified_id": uid, "quantity": qty} for uid, qty in pairs]


# --------------------------------------------------------------------------
# Escenario base, compartido por casi todos los tests
# --------------------------------------------------------------------------
#
# Está calibrado para que el óptimo sea un split real de dos tiendas y para que
# Carrefour esté ahí sólo por sus productos exclusivos:
#
#   5 exclusivos de Carrefour x $4.200      = $21.000  (supera su mínimo de $20.000)
#   6 comunes, más baratos en Coto x $2.500 = $15.000  (justo el mínimo de Coto)
#
#   split     : Carrefour 21.000 + 3.500 + Coto 15.000 + 3.000 = $42.500  <- óptimo
#   todo CRF  : 21.000 + 6 x 4.000 + 3.500                     = $48.500
#   todo Día  : Carrefour 24.500 + (6 x 3.100 + 3.000)         = $46.100
#
# Con los reemplazos a $2.500 en Coto, cerrar Carrefour deja 11 productos en Coto:
#   11 x 2.500 + 3.000 = $30.500, o sea $12.000 de ahorro.

EXCLUSIVOS = {f"prod_crf_{n}": {CARREFOUR: 4200} for n in range(5)}
COMUNES = {f"prod_com_{n}": {COTO: 2500, DIA: 3100, CARREFOUR: 4000} for n in range(6)}
REEMPLAZOS = {f"prod_rep_{n}": {COTO: 2500, DIA: 2600} for n in range(5)}


def _escenario_base(spec_extra=None, neighbors_override=None):
    """
    Devuelve (spec, cart, cursor) del escenario base.

    `neighbors_override` reemplaza la lista de vecinos de un ancla puntual, que es
    la palanca que usan los tests para forzar un caso raro.
    """
    spec = {**EXCLUSIVOS, **COMUNES, **REEMPLAZOS, **(spec_extra or {})}
    cart = _cart(*[(uid, 1) for uid in list(EXCLUSIVOS) + list(COMUNES)])

    products, neighbors = {}, {}
    for n in range(5):
        anchor, rep = f"prod_crf_{n}", f"prod_rep_{n}"
        products[anchor] = _product(anchor, f"Leche Carrefour {n} 1L", 1000.0, "ml")
        neighbors[anchor] = [_product(rep, f"Leche Alternativa {n} 1L", 1000.0, "ml")]

    for anchor, vecinos in (neighbors_override or {}).items():
        neighbors[anchor] = vecinos

    return spec, cart, FakeCursor(products, neighbors)


def _run(matrix_spec, cart, cursor, excluded=None, cards=None):
    """
    Corre el optimizador de verdad sobre `matrix_spec` y le pasa el resultado a la
    heurística, que es exactamente lo que hace src/api.py.
    """
    matrix = _matrix(matrix_spec)
    cart_matrix = {i["unified_id"]: matrix[i["unified_id"]] for i in cart}

    result = optimize_cart(
        cart_items=cart,
        user_cards=cards or [],
        delivery_costs=DELIVERY,
        excluded_stores=excluded or [],
        flat_prices=cart_matrix,
    )
    assert result["status"] == "success", result.get("message")

    suggestions = find_strategic_swaps(
        result=result,
        cart_items=cart,
        flat_prices=cart_matrix,
        user_memberships=[],
        user_cards=cards or [],
        delivery_costs=DELIVERY,
        excluded_stores=excluded or [],
        cur=cursor,
    )
    return result, suggestions


# --------------------------------------------------------------------------
# 1. El caso motivador: Carrefour arrastrado por sus productos exclusivos
# --------------------------------------------------------------------------

def test_cierra_carrefour_cuando_sus_exclusivos_tienen_reemplazo_mas_barato(fake_flatten):
    """
    Cinco productos existen sólo en Carrefour y obligan a abrir la tienda, con su
    mínimo de $20.000 y su envío propio. Cambiándolos por equivalentes de la misma
    góndola, todo el carrito entra en Coto y sale bastante más barato.
    """
    spec, cart, cursor = _escenario_base()
    fake_flatten(spec)

    result, suggestions = _run(spec, cart, cursor)

    assert set(result["split"]) == {COTO, CARREFOUR}, "el escenario tiene que dar un split real"
    assert len(suggestions) == 1

    s = suggestions[0]
    assert s["closed_store"] == CARREFOUR
    assert len(s["swaps"]) == 5
    assert {sw["original_uid"] for sw in s["swaps"]} == set(EXCLUSIVOS)
    assert {sw["replacement_uid"] for sw in s["swaps"]} == set(REEMPLAZOS)

    # El ahorro es exactamente la diferencia entre los dos totales, y los dos
    # totales salen del mismo solver.
    assert s["original_total"] == result["total_spent_net"] == 42500
    assert s["simulated_total"] == 30500
    assert s["projected_savings"] == 12000

    # Cada reemplazo se cotiza en la tienda donde realmente sale más barato.
    for sw in s["swaps"]:
        assert sw["replacement_store"] == COTO
        assert sw["replacement_cost"] == 2500
        assert sw["original_cost"] == 4200
        assert sw["quantity"] == 1
        assert sw["original_size"] == sw["replacement_size"] == "1 L"

    assert "5" in s["message"] and "Carrefour" in s["message"]


def test_el_total_simulado_coincide_con_reoptimizar_el_carrito_sustituido(fake_flatten):
    """
    El número que se le promete al usuario tiene que ser el que el solver devuelve
    para el carrito ya sustituido. Es la garantía que justifica reusar
    optimize_cart en vez de recalcular el costo a mano.
    """
    spec, cart, cursor = _escenario_base()
    matrix = fake_flatten(spec)

    _, suggestions = _run(spec, cart, cursor)
    s = suggestions[0]

    reemplazo_por_uid = {sw["original_uid"]: sw["replacement_uid"] for sw in s["swaps"]}
    carrito_sustituido = [
        {"unified_id": reemplazo_por_uid.get(i["unified_id"], i["unified_id"]),
         "quantity": i["quantity"]}
        for i in cart
    ]
    recheck = optimize_cart(
        cart_items=carrito_sustituido,
        delivery_costs=DELIVERY,
        excluded_stores=[CARREFOUR],
        flat_prices={i["unified_id"]: matrix[i["unified_id"]] for i in carrito_sustituido},
    )

    assert recheck["status"] == "success"
    assert recheck["total_spent_net"] == s["simulated_total"]


# --------------------------------------------------------------------------
# 2. Sin anclas no hay nada que analizar
# --------------------------------------------------------------------------

def test_sin_anclas_no_sugiere_nada_ni_consulta_la_base(fake_flatten):
    """
    Si todos los productos de una tienda existen en otra, cerrarla ya era un punto
    factible del modelo y el solver lo descartó: la simulación no puede ganarle.
    Se corta antes de la primera query.
    """
    spec = {
        f"prod_{n}": {COTO: 3000, DIA: 3050, CARREFOUR: 3100}
        for n in range(12)
    }
    fake_flatten(spec)
    cart = _cart(*[(uid, 1) for uid in spec])

    cursor = FakeCursor({}, {})
    _, suggestions = _run(spec, cart, cursor)

    assert suggestions == []
    assert cursor.queries == [], "no debería haber consultado la base"


def test_split_de_una_sola_tienda_sin_anclas_no_consulta_la_base(fake_flatten):
    """
    Una sola tienda ya no se saltea de entrada, pero el fast path de "sin anclas"
    sigue aplicando: si todo el carrito se consigue en otro lado, cerrar esa
    tienda era un punto que el solver ya evaluó.
    """
    spec = {f"prod_{n}": {COTO: 4000, DIA: 4200} for n in range(5)}
    fake_flatten(spec)
    cart = _cart(*[(uid, 1) for uid in spec])

    cursor = FakeCursor({}, {})
    result, suggestions = _run(spec, cart, cursor)

    assert list(result["split"]) == [COTO]
    assert suggestions == []
    assert cursor.queries == []


def test_una_sola_tienda_con_anclas_irremplazables_no_sugiere_nada(fake_flatten):
    """Todo el carrito es exclusivo de una tienda y no hay sustitutos: no hay salida."""
    spec = {f"prod_{n}": {COTO: 4000} for n in range(5)}
    fake_flatten(spec)
    cart = _cart(*[(uid, 1) for uid in spec])

    # El cursor no devuelve vecinos para ninguna de las 5 anclas.
    _, suggestions = _run(spec, cart, FakeCursor({}, {}))
    assert suggestions == []


def test_un_solo_exclusivo_arrastra_el_carrito_entero_a_su_tienda(fake_flatten):
    """
    El caso que destapó el bug del guard `len(split) < 2`, reportado desde la app:
    un producto barato que sólo vende una tienda la obliga a abrir, su mínimo de
    compra arrastra TODO el resto del carrito, y el split queda con una sola
    tienda. Saltear ese caso por "tener una sola tienda no hay nada que cerrar"
    era exactamente al revés: es el más caro de todos.

        original : Carrefour (2.000 + 8 x 2.400 + 3.500)  = 24.700
        simulado : Coto      (1.500 + 8 x 1.900 + 3.000)  = 19.700
    """
    exclusivo = {"prod_crf_solo": {CARREFOUR: 2000}}
    comunes = {f"prod_com_{n}": {COTO: 1900, CARREFOUR: 2400} for n in range(8)}
    reemplazo = {"prod_rep_solo": {COTO: 1500}}
    spec = {**exclusivo, **comunes, **reemplazo}
    fake_flatten(spec)

    cart = _cart(*[(uid, 1) for uid in list(exclusivo) + list(comunes)])
    products = {"prod_crf_solo": _product("prod_crf_solo", "Vinagre exclusivo 500 cc.", 500.0, "ml")}
    neighbors = {"prod_crf_solo": [_product("prod_rep_solo", "Vinagre alternativo 500 cc.", 500.0, "ml")]}

    result, suggestions = _run(spec, cart, FakeCursor(products, neighbors))

    # El óptimo mete todo en Carrefour: sacar comunes de ahí lo deja bajo su
    # mínimo de $20.000, y los que sobran no llegan al de Coto.
    assert list(result["split"]) == [CARREFOUR]
    assert result["total_spent_net"] == 24700

    assert len(suggestions) == 1
    s = suggestions[0]
    assert s["closed_store"] == CARREFOUR
    assert [sw["original_uid"] for sw in s["swaps"]] == ["prod_crf_solo"]
    assert s["relocated_count"] == 8
    assert s["simulated_total"] == 19700
    assert s["projected_savings"] == 5000


# --------------------------------------------------------------------------
# 3. Reemplazos que no son comparables
# --------------------------------------------------------------------------

@pytest.mark.parametrize("vecino, motivo", [
    (_product("prod_rep_x", "Leche Alternativa 300ml", weight=300.0, unit="ml"),
     "el tamaño queda fuera de la banda 0.5x-2x"),
    (_product("prod_rep_x", "Leche en polvo x1", weight=1.0, unit="un"),
     "un producto sin tamaño parseado no se compara contra uno con peso real"),
])
def test_un_ancla_sin_reemplazo_comparable_bloquea_el_cierre(fake_flatten, vecino, motivo):
    """
    Es todo o nada: si queda un solo producto que sólo vende la tienda a cerrar,
    la tienda no se puede cerrar y un ahorro parcial sería mentira.

    El vecino no comparable es baratísimo a propósito: lo único que lo descarta es
    el filtro de comparabilidad.
    """
    spec, cart, cursor = _escenario_base(
        spec_extra={"prod_rep_x": {COTO: 500, DIA: 500}},
        neighbors_override={"prod_crf_0": [vecino]},
    )
    fake_flatten(spec)

    _, suggestions = _run(spec, cart, cursor)
    assert suggestions == [], motivo


def test_no_cambia_un_pack_por_una_unidad_suelta(fake_flatten):
    """
    El tamaño que guarda la base es el que figura en el nombre, y en un pack ese
    número tanto puede ser el total como el de cada unidad. Sin este guard, un
    "x6 45 g." (seis alfajores) entra en la banda de tamaño contra un alfajor
    suelto de 60 g y se ofrece el cambio.
    """
    spec, cart, cursor = _escenario_base(
        spec_extra={"prod_rep_suelto": {COTO: 400, DIA: 450}},
        neighbors_override={"prod_crf_0": [
            # Baratísimo, misma góndola y tamaño "comparable": lo único que lo
            # descarta es que el ancla es un pack de 6 y este viene suelto.
            _product("prod_rep_suelto", "Alfajor suelto 60 g.", 60.0, "g"),
        ]},
    )
    # El ancla 0 pasa a ser un pack de seis.
    cursor.products["prod_crf_0"] = _product(
        "prod_crf_0", "Alfajor de chocolate negro Entre Dos x6 45 g.", 45.0, "g"
    )
    fake_flatten(spec)

    _, suggestions = _run(spec, cart, cursor)
    assert suggestions == []


def test_dos_packs_del_mismo_tamano_si_son_intercambiables(fake_flatten):
    """El guard compara formatos, no los prohíbe: dos x6 sí se pueden cambiar."""
    spec, cart, cursor = _escenario_base(
        spec_extra={"prod_rep_pack": {COTO: 1500, DIA: 1600}},
        neighbors_override={"prod_crf_0": [
            _product("prod_rep_pack", "Alfajor Carrefour classic x6 50 g.", 50.0, "g"),
        ]},
    )
    cursor.products["prod_crf_0"] = _product(
        "prod_crf_0", "Alfajor de chocolate negro Entre Dos x6 45 g.", 45.0, "g"
    )
    fake_flatten(spec)

    _, suggestions = _run(spec, cart, cursor)

    assert len(suggestions) == 1
    swap = next(s for s in suggestions[0]["swaps"] if s["original_uid"] == "prod_crf_0")
    assert swap["replacement_uid"] == "prod_rep_pack"


def test_ancla_sin_ningun_vecino_bloquea_el_cierre(fake_flatten):
    """La góndola no devolvió nada para una de las anclas."""
    spec, cart, cursor = _escenario_base(neighbors_override={"prod_crf_3": []})
    fake_flatten(spec)

    _, suggestions = _run(spec, cart, cursor)
    assert suggestions == []


def test_demasiados_anclas_no_se_evalua(fake_flatten, monkeypatch):
    """Una alerta que pide cambiar más productos que el tope es ruido, no consejo."""
    monkeypatch.setattr(swaps_module, "MAX_ANCHOR_SWAPS", 3)

    spec, cart, cursor = _escenario_base()
    fake_flatten(spec)

    _, suggestions = _run(spec, cart, cursor)

    assert suggestions == []
    assert cursor.queries == [], "el tope se chequea antes de consultar la base"


# --------------------------------------------------------------------------
# 4/5. El cierre es posible pero no conviene
# --------------------------------------------------------------------------

def test_no_sugiere_cuando_cerrar_sale_mas_caro(fake_flatten):
    """Los reemplazos son carísimos: cerrar es factible pero peor."""
    caros = {f"prod_rep_{n}": {COTO: 9000, DIA: 9500} for n in range(5)}
    spec, cart, cursor = _escenario_base(spec_extra=caros)
    fake_flatten(spec)

    _, suggestions = _run(spec, cart, cursor)
    assert suggestions == []


def test_no_sugiere_cuando_el_ahorro_no_llega_al_umbral(fake_flatten, monkeypatch):
    """
    Un ahorro positivo pero chico no justifica pedirle al usuario que cambie cinco
    productos. Se fuerza el umbral por encima del ahorro del escenario base para
    aislar exactamente esa decisión: es el mismo caso que sí se emite arriba.
    """
    spec, cart, cursor = _escenario_base()
    fake_flatten(spec)

    monkeypatch.setattr(swaps_module, "MIN_SAVINGS_PCT", 0.95)
    _, suggestions = _run(spec, cart, cursor)
    assert suggestions == []


def test_no_elige_el_reemplazo_mas_barato_si_obliga_a_abrir_una_tienda(fake_flatten):
    """
    Elegir por ancla, aislado del resto del carrito, no alcanza: el reemplazo más
    barato puede ser exclusivo de una tienda apagada, y entonces arrastra su
    mínimo de compra y vuelve infactible toda la simulación.

    Caso real que lo destapó, con un carrito de la base: una harina exclusiva de
    Carrefour a $789 con todo el carrito arrastrado a Carrefour por su mínimo. El
    vecino más barato era una harina de $915 que sólo vende Día, cuyo mínimo de
    $12.000 no se alcanzaba con un solo producto -> infeasible -> se descartaba el
    cierre entero. La Chacabuco a $1.039, vendida en las tres tiendas, cerraba
    Carrefour y ahorraba $2.411.

        original : Carrefour (789 + 11.940 + 10.370 + 3.500)  = 26.599
        con DIA  : Coto (19.750 + 3.000) + Día (915 + 3.000) -> Día no llega a su mínimo
        con COTO : Coto (9.872 + 9.878 + 1.039 + 3.000)       = 23.789
    """
    exclusivo = {"prod_harina_crf": {CARREFOUR: 789}}
    comunes = {
        "prod_alfajor": {COTO: 9872, CARREFOUR: 11940},
        "prod_aceite": {COTO: 9878, CARREFOUR: 10370},
    }
    # El de Día es más barato pero está en una sola tienda; el de Coto sale un
    # poco más y se consigue en las tres.
    reemplazos = {
        "prod_harina_dia": {DIA: 915},
        "prod_harina_comun": {COTO: 1039, DIA: 1039, CARREFOUR: 1039},
    }
    spec = {**exclusivo, **comunes, **reemplazos}
    fake_flatten(spec)

    cart = _cart(("prod_harina_crf", 1), ("prod_alfajor", 1), ("prod_aceite", 1))
    products = {"prod_harina_crf": _product("prod_harina_crf", "Harina Bulnez 000 1 kg", 1000.0, "g")}
    neighbors = {"prod_harina_crf": [
        _product("prod_harina_dia", "Harina DIA 000 1 kg", 1000.0, "g"),
        _product("prod_harina_comun", "Harina Chacabuco 000 1 kg", 1000.0, "g"),
    ]}

    result, suggestions = _run(spec, cart, FakeCursor(products, neighbors))

    assert list(result["split"]) == [CARREFOUR]

    assert len(suggestions) == 1, "el plan por disponibilidad tiene que rescatar el cierre"
    s = suggestions[0]
    assert s["swaps"][0]["replacement_uid"] == "prod_harina_comun"
    assert s["swaps"][0]["replacement_store"] == COTO
    assert s["original_total"] == 26599
    assert s["simulated_total"] == 23789
    assert s["projected_savings"] == 2810


def test_con_todos_los_reemplazos_disponibles_gana_el_mas_barato(fake_flatten):
    """
    El plan por disponibilidad no puede volverse el criterio: cuando ninguno de
    los dos obliga a abrir nada, el que tiene que ganar es el más barato, porque
    los dos planes se simulan y se compara el total del solver.
    """
    spec, cart, cursor = _escenario_base(
        spec_extra={"prod_rep_caro": {COTO: 3500, DIA: 3500, CARREFOUR: 3500}},
        neighbors_override={"prod_crf_0": [
            # El caro está en las tres tiendas; el barato en dos, pero las dos
            # siguen abiertas, así que elegirlo no cuesta nada.
            _product("prod_rep_caro", "Leche Cara 1L", 1000.0, "ml"),
            _product("prod_rep_0", "Leche Alternativa 0 1L", 1000.0, "ml"),
        ]},
    )
    fake_flatten(spec)

    _, suggestions = _run(spec, cart, cursor)

    assert len(suggestions) == 1
    swap = next(s for s in suggestions[0]["swaps"] if s["original_uid"] == "prod_crf_0")
    assert swap["replacement_uid"] == "prod_rep_0"
    assert swap["replacement_cost"] == 2500


def test_no_sugiere_cuando_el_cierre_deja_al_resto_infactible(fake_flatten):
    """
    Sacar Carrefour deja un carrito que no llega al mínimo de ninguna otra tienda.
    La simulación vuelve infeasible y la respuesta honesta es no sugerir nada.
    """
    exclusivos = {"prod_crf_0": {CARREFOUR: 21000}}
    baratos = {"prod_com_0": {COTO: 900, DIA: 950, CARREFOUR: 920}}
    reemplazos = {"prod_rep_0": {COTO: 800, DIA: 850}}
    spec = {**exclusivos, **baratos, **reemplazos}
    fake_flatten(spec)
    cart = _cart(("prod_crf_0", 1), ("prod_com_0", 1))

    products = {"prod_crf_0": _product("prod_crf_0", "Aceite Carrefour 1L", 1000.0, "ml")}
    neighbors = {"prod_crf_0": [_product("prod_rep_0", "Aceite Alternativo 1L", 1000.0, "ml")]}

    result, suggestions = _run(spec, cart, FakeCursor(products, neighbors))

    # El carrito original sí es factible (Carrefour supera su mínimo de $20.000).
    assert CARREFOUR in result["split"]
    # Pero con los reemplazos, $1.700 no alcanzan el mínimo de Coto ni el de Día.
    assert suggestions == []


# --------------------------------------------------------------------------
# 6. Colisiones de UID
# --------------------------------------------------------------------------

def test_descarta_el_candidato_que_ya_esta_en_el_carrito(fake_flatten):
    """
    Un reemplazo que el usuario ya lleva duplicaría el UID en el carrito simulado.
    `flatten_cart_prices` resuelve la cantidad con el último que ve y
    `optimize_cart` con el primero, así que el costo simulado no correspondería a
    ningún carrito real. Se salta al siguiente candidato.
    """
    # prod_rep_0 se encarece para que, si el guard fallara, el candidato que ya
    # está en el carrito (prod_com_0, a $2.500 en Coto) fuera el elegido.
    spec, cart, cursor = _escenario_base(
        spec_extra={"prod_rep_0": {COTO: 2900, DIA: 3000}},
        neighbors_override={"prod_crf_0": [
            _product("prod_com_0", "Leche que ya está en el carrito 1L", 1000.0, "ml"),
            _product("prod_rep_0", "Leche Alternativa 0 1L", 1000.0, "ml"),
        ]},
    )
    fake_flatten(spec)

    _, suggestions = _run(spec, cart, cursor)

    assert len(suggestions) == 1
    usados = [sw["replacement_uid"] for sw in suggestions[0]["swaps"]]
    assert "prod_com_0" not in usados
    assert "prod_rep_0" in usados


def test_dos_anclas_no_comparten_el_mismo_reemplazo(fake_flatten):
    """
    Mismo problema de UID duplicado, pero por el otro lado: dos anclas cuyo mejor
    vecino es el mismo producto.
    """
    compartido = _product("prod_rep_compartido", "Leche Compartida 1L", 1000.0, "ml")
    # El compartido es el más barato, así que las dos primeras anclas lo querrían.
    spec, cart, cursor = _escenario_base(
        spec_extra={"prod_rep_compartido": {COTO: 1000, DIA: 1100}},
        neighbors_override={
            "prod_crf_0": [compartido, _product("prod_rep_0", "Leche Alternativa 0 1L", 1000.0, "ml")],
            "prod_crf_1": [compartido, _product("prod_rep_1", "Leche Alternativa 1 1L", 1000.0, "ml")],
        },
    )
    fake_flatten(spec)

    _, suggestions = _run(spec, cart, cursor)

    assert len(suggestions) == 1
    usados = [sw["replacement_uid"] for sw in suggestions[0]["swaps"]]
    assert len(usados) == len(set(usados)), "no puede repetirse un reemplazo"
    assert usados.count("prod_rep_compartido") == 1


# --------------------------------------------------------------------------
# 7. Anclas vs. productos que sólo se mudan
# --------------------------------------------------------------------------

def test_un_producto_disponible_en_una_tienda_apagada_no_es_ancla(fake_flatten):
    """
    Al cerrar la tienda el solver puede prender una que hoy está apagada, así que
    un producto que también se vende ahí se muda solo. Contarlo como ancla pediría
    un cambio innecesario; acá se verifica que cae en `relocated_count`.
    """
    # Escenario propio: Día queda APAGADA en el óptimo, y prod_mov (que Carrefour y
    # Día comparten) es lo que la puede prender cuando Carrefour se cierra.
    #
    #   óptimo   : Carrefour (4 x 4.200 + 7.600 + 3.500) + Coto (15.000 + 3.000) = 45.900
    #   simulado : Coto (4 x 2.500 + 15.000 + 3.000) + Día (12.500 + 3.000)      = 43.500
    exclusivos = {f"prod_crf_{n}": {CARREFOUR: 4200} for n in range(4)}
    movible = {"prod_mov": {CARREFOUR: 7600, DIA: 12500}}
    comunes = {f"prod_com_{n}": {COTO: 2500, DIA: 3100, CARREFOUR: 4000} for n in range(6)}
    reemplazos = {f"prod_rep_{n}": {COTO: 2500, DIA: 2600} for n in range(4)}

    spec = {**exclusivos, **movible, **comunes, **reemplazos}
    fake_flatten(spec)
    cart = _cart(*[(uid, 1) for uid in list(exclusivos) + list(movible) + list(comunes)])

    products, neighbors = {}, {}
    for n in range(4):
        anchor, rep = f"prod_crf_{n}", f"prod_rep_{n}"
        products[anchor] = _product(anchor, f"Leche Carrefour {n} 1L", 1000.0, "ml")
        neighbors[anchor] = [_product(rep, f"Leche Alternativa {n} 1L", 1000.0, "ml")]

    result, suggestions = _run(spec, cart, FakeCursor(products, neighbors))

    assert set(result["split"]) == {COTO, CARREFOUR}, "Día tiene que estar apagada"
    assert "prod_mov" in {p["unified_id"] for p in result["split"][CARREFOUR]["products"]}

    assert len(suggestions) == 1
    s = suggestions[0]
    assert len(s["swaps"]) == 4
    assert "prod_mov" not in {sw["original_uid"] for sw in s["swaps"]}
    # prod_mov no se cambia: se muda solo a Día, que la simulación prende.
    assert s["relocated_count"] == 1
    assert s["simulated_total"] == 43500


# --------------------------------------------------------------------------
# 8. Fail-open
# --------------------------------------------------------------------------

def test_un_error_de_base_devuelve_lista_vacia_sin_propagar(fake_flatten):
    """
    Esto es una sugerencia opcional sobre un resultado que ya es correcto: que se
    caiga puede costar la alerta, nunca la optimización.
    """
    spec, cart, _ = _escenario_base()
    fake_flatten(spec)

    cursor = FakeCursor({}, {}, raise_on_query=True)
    _, suggestions = _run(spec, cart, cursor)

    assert suggestions == []


# --------------------------------------------------------------------------
# Helpers puros
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
    assert swaps_module._is_comparable(orig, cand) is esperado


@pytest.mark.parametrize("weight, unit, esperado", [
    (1000.0, "g", "1 Kg"),
    (1500.0, "ml", "1.5 L"),
    (500.0, "g", "500 g"),
    (900.0, "ml", "900 ml"),
    (1.0, "un", "1 unidad"),
])
def test_formato_de_tamano(weight, unit, esperado):
    assert swaps_module._format_size(weight, unit) == esperado
