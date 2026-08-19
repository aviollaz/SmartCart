# src/strategic_swaps.py
"""
Heurística de "cierre de tienda": ¿conviene sacar una tienda entera del split
cambiando los productos que sólo ella vende?

`optimize_cart()` es óptimo, pero dentro de un espacio de búsqueda con una
frontera: los productos del carrito son inmutables. Si cinco productos existen
sólo en Carrefour, cada uno tiene una única variable booleana y su restricción
`sum(x[i,j]) == 1` fuerza `y["carrefour_online"] = 1`. Con la tienda activada, su
mínimo de compra de $20.000 pasa a ser obligatorio, y el solver arrastra
productos que estaban más baratos en otro lado sólo para alcanzarlo, más el envío
de una tienda extra. El resultado es óptimo y a la vez caro, y el usuario no
tiene forma de enterarse de por qué.

Este módulo hace la pregunta que el solver no puede hacerse, porque sustituir un
producto lo saca de su espacio de búsqueda: "¿y si cambiás esos cinco por
equivalentes de otra góndola y cerrás Carrefour del todo?".

Corolario que define el diseño y que conviene tener presente antes de tocar nada:
una tienda cuyos productos existen TODOS en otro lado no necesita analizarse.
Cerrarla ya era un punto factible que el solver evaluó y descartó, así que la
simulación no puede ganarle. La heurística sólo aporta valor cuando hay al menos
un producto ancla, y por eso ese es el primer filtro (y el más barato).

Dos decisiones que valen por todo el módulo:

1. La simulación reusa `optimize_cart()` en vez de recalcular el costo a mano.
   "Re-evaluar productos + envíos - promos bancarias" es literalmente lo que hace
   el solver, y escribirlo de nuevo significaría una cuarta copia de la tabla de
   `bank_promos` (ya duplicada en optimizer.py, api.py y
   tests/test_optimizer_correctness.py) más una segunda aritmética en paralelo a
   la entera en centavos del modelo, con su división truncada. Un ahorro
   calculado con otra aritmética que el total que se le mostró al usuario es un
   bug garantizado, y de los que nadie ve hasta que alguien paga de más.

2. Fail-open, como src/coto_logistics.py: `find_strategic_swaps()` no levanta
   nunca. Esto es una sugerencia opcional sobre un resultado que ya es correcto;
   que se caiga sólo puede costar la alerta, jamás la optimización.
"""
import logging

from dataclasses import dataclass, field, asdict

from src.flattener import flatten_cart_prices
from src.optimizer import optimize_cart
from src.substitutions import (
    comparable_candidates,
    fetch_product_rows,
    format_size,
    weight_of,
)

logger = logging.getLogger(__name__)

# Tope de productos a cambiar en una sugerencia. Una alerta que pide cambiar
# quince productos no es una recomendación, es un carrito nuevo: el usuario no la
# va a aplicar y el ruido le resta credibilidad a las que sí valen la pena.
MAX_ANCHOR_SWAPS = 8

# Umbral para emitir la sugerencia. Es relativo al total porque lo que hace que
# valga la pena molestar al usuario escala con el carrito, con un piso absoluto
# para que en un carrito chico un 3% no habilite un ahorro trivial.
MIN_SAVINGS_PCT = 0.03
MIN_SAVINGS_ABS = 500.0


@dataclass
class StrategicSwapSuggestion:
    """
    Propuesta de cerrar una tienda entera cambiando sus productos exclusivos.

    `swaps` son los cambios que el usuario tiene que aceptar; `relocated_count`
    son los ítems de la tienda cerrada que simplemente se mudan a otra sin
    cambiar de producto. Van separados porque para el usuario son dos cosas
    distintas: uno es una decisión, el otro es una consecuencia.
    """
    closed_store: str
    swaps: list = field(default_factory=list)
    relocated_count: int = 0
    original_total: float = 0.0
    simulated_total: float = 0.0
    projected_savings: float = 0.0
    message: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _find_anchor_uids(store, store_products, flat_prices, excluded_stores):
    """
    Productos asignados a `store` que no se consiguen en ninguna otra tienda
    disponible: los que obligan a que la tienda esté abierta.

    El criterio son las tiendas NO EXCLUIDAS, no las tiendas activas en el split.
    Al cerrar `store` el solver puede prender una tienda que hoy está apagada, así
    que un producto que también se vende ahí no necesita reemplazo: se muda solo.
    Mirar sólo las activas sobrecontaría anclas y descartaría cierres que sí
    convienen.
    """
    anchors = []
    for product in store_products:
        uid = product["unified_id"]
        alternatives = set(flat_prices.get(uid, {})) - {store} - set(excluded_stores)
        if not alternatives:
            anchors.append(uid)
    return anchors


def _collect_candidates(cur, anchor_rows, target_stores, cart_uids):
    """
    Candidatos comparables por ancla: misma góndola, mismo formato de pack,
    unidad compatible y tamaño dentro de la banda.

    Los cuatro criterios viven en src/substitutions.py, compartidos con las
    sugerencias de api.py. Acá sólo queda el descarte de los que ya están en el
    carrito, que es propio de esta heurística: un UID repetido rompe la
    simulación en silencio, porque `flatten_cart_prices` arma su `quantity_map`
    con el último que ve y `optimize_cart` resuelve la cantidad con el primero,
    así que el costo simulado no correspondería a ningún carrito real.
    """
    per_anchor = {}

    for uid, anchor_row in anchor_rows.items():
        if not anchor_row.get("name_embedding"):
            continue

        viables = comparable_candidates(cur, anchor_row, target_stores, exclude_uids=cart_uids)
        if viables:
            per_anchor[uid] = viables

    return per_anchor


def _best_offer(price_row, target_stores, prefer_availability=False):
    """
    (costo, tienda) elegido de un producto entre las tiendas candidatas, más la
    clave con la que se comparó contra los demás candidatos del ancla.

    Con `prefer_availability` la clave antepone en cuántas tiendas se consigue el
    producto. Ver `_resolve_swaps` para por qué existe ese criterio; acá alcanza
    con notar que apagado ordena sólo por precio, que es el comportamiento
    histórico.
    """
    offers = [(price_row[s]["total_cost"], s) for s in price_row if s in target_stores]
    if not offers:
        return None

    cost, store = min(offers)
    rank = (-len(offers), cost) if prefer_availability else (cost,)
    return cost, store, rank


def _resolve_swaps(closing_store, anchors, anchor_rows, candidates, prices_by_qty, flat_prices,
                   target_stores, quantities, taken_uids, prefer_availability=False):
    """
    Elige un reemplazo concreto por ancla entre los comparables.

    Devuelve `(swaps, filas_de_precio)` o None en cuanto un ancla se queda sin
    reemplazo. Es todo o nada: si queda un solo producto que sólo vende la tienda
    a cerrar, la tienda no se puede cerrar y cualquier ahorro parcial sería
    mentira.

    El criterio de elección es un parámetro porque elegir por ancla, aislado del
    resto del carrito, no alcanza: quien sabe si el conjunto cierra es el solver,
    y no se le puede pedir que elija entre varios candidatos (cada línea del
    carrito tiene exactamente un producto). El más barato puede ser exclusivo de
    una tienda apagada, y entonces el reemplazo la obliga a abrir con su mínimo
    de compra a cuestas: el caso real fue una harina de $915 que sólo vende Día,
    cuyo mínimo de $12.000 volvía infactible toda la simulación y tiraba abajo un
    cierre que con otra harina de $1.039 —vendida en las tres tiendas— ahorraba
    plata. Con `prefer_availability` se prioriza justamente eso: un reemplazo que
    está en todos lados no obliga a abrir ninguna tienda. El llamador arma los dos
    planes y deja que el solver decida cuál conviene.

    Cada candidato se cotiza con la cantidad del ancla que reemplaza (de ahí que
    `prices_by_qty` esté indexado por cantidad), y la fila elegida viaja al
    llamador para que la simulación use exactamente el precio que se usó acá.
    """
    swaps = []
    price_rows = {}

    for uid in anchors:
        anchor_row = anchor_rows[uid]
        anchor_weight, anchor_unit = weight_of(anchor_row)
        qty = quantities[uid]
        priced_at_qty = prices_by_qty.get(qty, {})
        best = None

        for cand in candidates.get(uid, []):
            # Dos anclas no pueden mapear al mismo reemplazo: el carrito simulado
            # tendría el UID repetido (ver _collect_candidates).
            if cand["uid"] in taken_uids:
                continue
            price_row = priced_at_qty.get(cand["uid"], {})
            offer = _best_offer(price_row, target_stores, prefer_availability)
            if offer is None:
                continue
            cost, store, rank = offer
            if best is None or rank < best[0]:
                best = (rank, cost, store, cand, price_row)

        if best is None:
            return None

        _rank, cost, store, cand, price_row = best
        taken_uids.add(cand["uid"])
        price_rows[cand["uid"]] = price_row

        # El costo original es el de la tienda que se va a cerrar, que es donde el
        # usuario lo tiene asignado hoy: es el número contra el que va a comparar.
        original_cost = flat_prices.get(uid, {}).get(closing_store, {}).get("total_cost")

        swaps.append({
            "original_uid": uid,
            "original_name": anchor_row["name"],
            "original_cost": round(original_cost, 2) if original_cost is not None else None,
            "original_size": format_size(anchor_weight, anchor_unit),
            "replacement_uid": cand["uid"],
            "replacement_name": cand["name"],
            "replacement_store": store,
            "replacement_cost": round(cost, 2),
            "replacement_size": format_size(cand["weight"], cand["unit"]),
            "quantity": qty,
        })

    return swaps, price_rows


def _simulate_closure(store, swaps, price_rows, cart_items, flat_prices, excluded_stores,
                      user_memberships, user_cards, delivery_costs):
    """
    Corre el solver de verdad sobre el carrito con los reemplazos aplicados y la
    tienda excluida. Devuelve el resultado de `optimize_cart` o None si cerrarla
    deja al resto sin llegar a los mínimos (que es una respuesta legítima: esa
    tienda no se puede cerrar).
    """
    replacement_by_uid = {s["original_uid"]: s["replacement_uid"] for s in swaps}

    simulated_cart = [
        {"unified_id": replacement_by_uid.get(item["unified_id"], item["unified_id"]),
         "quantity": item["quantity"]}
        for item in cart_items
    ]

    # La matriz se arma sólo con los UIDs del carrito simulado: `optimize_cart`
    # deriva sus productos de las claves que recibe, así que dejar adentro los
    # candidatos descartados los convertiría en productos fantasma con restricción
    # `== 1`. Los productos que siguen igual salen de la matriz del carrito y los
    # reemplazos de la fila que ya se eligió, cotizada a la cantidad correcta.
    simulated_prices = {}
    for item in simulated_cart:
        uid = item["unified_id"]
        row = price_rows.get(uid) or flat_prices.get(uid)
        if not row:
            return None
        simulated_prices[uid] = row

    result = optimize_cart(
        cart_items=simulated_cart,
        user_memberships=user_memberships,
        user_cards=user_cards,
        delivery_costs=delivery_costs,
        excluded_stores=list(excluded_stores) + [store],
        flat_prices=simulated_prices,
    )

    if result.get("status") != "success":
        return None
    # Imposible por construcción, pero la aserción es gratis y el día que alguien
    # toque el manejo de excluded_stores esto lo va a atajar antes que el usuario.
    if store in result.get("split", {}):
        return None

    return result


def _build_message(store, swaps, savings):
    store_label = {
        "coto_online": "Coto",
        "dia_online": "Día",
        "carrefour_online": "Carrefour",
    }.get(store, store)

    n = len(swaps)
    productos = "producto" if n == 1 else "productos"
    cambia = "Cambiá este" if n == 1 else f"Cambiá estos {n}"
    return (
        f"{cambia} {productos} por sus alternativas y ahorrá "
        f"${savings:,.0f} sacando {store_label} del pedido."
    ).replace(",", ".")


def find_strategic_swaps(*, result, cart_items, flat_prices, user_memberships, user_cards,
                         delivery_costs, excluded_stores, cur):
    """
    Evalúa cerrar cada tienda activa del split y devuelve las sugerencias que
    ahorran plata, ordenadas por ahorro descendente.

    `cur` es un cursor ya abierto (el módulo no abre conexiones propias) y
    `flat_prices` es la matriz del carrito original: tiene que ser la del carrito,
    no una enriquecida con candidatos de otras features, porque de ahí sale el
    cálculo de anclas.

    Nunca levanta: ante cualquier error devuelve [].
    """
    try:
        return _find_strategic_swaps(
            result=result, cart_items=cart_items, flat_prices=flat_prices,
            user_memberships=user_memberships, user_cards=user_cards,
            delivery_costs=delivery_costs, excluded_stores=excluded_stores, cur=cur,
        )
    except Exception as e:
        logger.error(f"Error en la heurística de cierre de tienda: {e}")
        return []


def _find_strategic_swaps(*, result, cart_items, flat_prices, user_memberships, user_cards,
                          delivery_costs, excluded_stores, cur):
    split = result.get("split") or {}
    original_total = result.get("total_spent_net")

    # Un split de UNA sola tienda no se saltea. Parece que no hubiera nada que
    # cerrar, pero es justo el caso más caro: un solo producto exclusivo obliga a
    # abrir su tienda, el mínimo de compra arrastra ahí todo el resto del carrito,
    # y el usuario termina comprando entero en la tienda equivocada. El caso real
    # que lo destapó: un vinagre de $1.550 que sólo vende Carrefour arrastró 15
    # alfajores a $2.125 para llegar al mínimo de $20.000, cuando en Coto estaban
    # a $1.062,50 con promo — $36.925 contra $15.750.
    #
    # Quién puede cerrarse lo decide el análisis de anclas de más abajo, que ya
    # contempla el caso de que no quede ninguna tienda viable (la simulación
    # vuelve infeasible y se descarta).
    if original_total is None or not split:
        return []

    excluded_stores = list(excluded_stores or [])
    quantities = {item["unified_id"]: item["quantity"] for item in cart_items}

    # Paso 1: anclas por tienda. Es el filtro más barato y el que descarta la
    # mayoría de los casos, así que va antes de cualquier query.
    anchors_by_store = {}
    for store, store_result in split.items():
        anchors = _find_anchor_uids(store, store_result["products"], flat_prices, excluded_stores)
        if not anchors:
            continue  # el solver ya evaluó y descartó cerrarla (ver docstring del módulo)
        if len(anchors) > MAX_ANCHOR_SWAPS:
            logger.info(
                f"{store} tiene {len(anchors)} productos exclusivos, más que el tope de "
                f"{MAX_ANCHOR_SWAPS}: no se evalúa cerrarla."
            )
            continue
        anchors_by_store[store] = anchors

    if not anchors_by_store:
        return []

    # Paso 2: candidatos a reemplazo, con una query por ancla.
    cart_uids = set(quantities)
    all_anchor_uids = {uid for anchors in anchors_by_store.values() for uid in anchors}
    anchor_rows = fetch_product_rows(cur, all_anchor_uids)

    candidates_by_store = {}
    for store, anchors in anchors_by_store.items():
        target_stores = [s for s in delivery_costs if s != store and s not in excluded_stores]
        if not target_stores:
            continue
        rows = {uid: anchor_rows[uid] for uid in anchors if uid in anchor_rows}
        candidates = _collect_candidates(cur, rows, target_stores, cart_uids)
        # Si algún ancla no tiene ni un candidato comparable, la tienda no es
        # cerrable y no tiene sentido cotizar el resto.
        if len(candidates) == len(anchors):
            candidates_by_store[store] = (candidates, target_stores)

    if not candidates_by_store:
        return []

    # Paso 3: precios de los candidatos, en tandas. flatten_cart_prices abre una
    # conexión por llamada, así que se cotizan todos juntos en vez de uno por uno.
    #
    # Cada candidato se cotiza con la cantidad del ancla que reemplazaría, no con
    # 1: las promos condicionales (3x2, 2da unidad al 50%) recién se activan a
    # partir de cierta cantidad, así que cotizar a 1 un candidato que el usuario
    # va a llevar de a 3 lo muestra más caro de lo que es y puede descartar un
    # cierre que convenía.
    #
    # Un mismo candidato puede servir para dos anclas con cantidades distintas, y
    # la matriz de `flatten_cart_prices` se indexa sólo por UID: quedarse con una
    # sola cantidad haría que el precio no corresponda al carrito simulado. Por
    # eso se agrupa por cantidad y se cotiza cada grupo por separado. Los carritos
    # reales tienen pocas cantidades distintas, así que suele ser una sola llamada.
    #
    # El carrito no se re-cotiza: `flat_prices` ya es su matriz, con sus cantidades.
    uids_by_qty = {}
    for candidates, _ in candidates_by_store.values():
        for anchor_uid, viables in candidates.items():
            qty = quantities.get(anchor_uid, 1)
            for cand in viables:
                if cand["uid"] not in cart_uids:
                    uids_by_qty.setdefault(qty, set()).add(cand["uid"])

    prices_by_qty = {
        qty: flatten_cart_prices(
            [{"unified_id": uid, "quantity": qty} for uid in uids], user_memberships
        )
        for qty, uids in uids_by_qty.items()
    }

    # Paso 4: elegir reemplazos, simular y quedarse con lo que ahorra.
    #
    # Se arman DOS planes por tienda y se simulan los dos, porque el criterio
    # para elegir un reemplazo no es evidente desde el ancla sola (ver
    # `_resolve_swaps`): el más barato puede ser exclusivo de una tienda apagada
    # y arrastrar su mínimo de compra. Los planes se deduplican —lo habitual es
    # que coincidan y se simule una sola vez— y gana el de menor total, que es la
    # única comparación que corresponde: los dos números salen del mismo solver.
    suggestions = []
    for store, (candidates, target_stores) in candidates_by_store.items():
        anchors = anchors_by_store[store]

        plans = []
        for prefer_availability in (False, True):
            resolved = _resolve_swaps(
                store, anchors, anchor_rows, candidates, prices_by_qty, flat_prices,
                target_stores, quantities, set(cart_uids),
                prefer_availability=prefer_availability,
            )
            if resolved is None:
                continue
            swaps, price_rows = resolved
            fingerprint = tuple((s["original_uid"], s["replacement_uid"]) for s in swaps)
            if any(fingerprint == seen for seen, _, _ in plans):
                continue
            plans.append((fingerprint, swaps, price_rows))

        best_simulation = None
        for _fingerprint, swaps, price_rows in plans:
            simulated = _simulate_closure(
                store, swaps, price_rows, cart_items, flat_prices, excluded_stores,
                user_memberships, user_cards, delivery_costs,
            )
            if simulated is None:
                continue
            if best_simulation is None or simulated["total_spent_net"] < best_simulation[0]["total_spent_net"]:
                best_simulation = (simulated, swaps)

        if best_simulation is None:
            continue

        simulated, swaps = best_simulation
        simulated_total = simulated["total_spent_net"]
        savings = round(original_total - simulated_total, 2)

        if savings < max(original_total * MIN_SAVINGS_PCT, MIN_SAVINGS_ABS):
            continue

        swapped_uids = {s["original_uid"] for s in swaps}
        relocated = len([p for p in split[store]["products"] if p["unified_id"] not in swapped_uids])

        suggestions.append(StrategicSwapSuggestion(
            closed_store=store,
            swaps=swaps,
            relocated_count=relocated,
            original_total=original_total,
            simulated_total=simulated_total,
            projected_savings=savings,
            message=_build_message(store, swaps, savings),
        ).to_dict())

    suggestions.sort(key=lambda s: s["projected_savings"], reverse=True)
    return suggestions
