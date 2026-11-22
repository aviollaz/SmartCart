# src/store_comparison.py
"""
Comparación por supermercado: cuánto sale el carrito entero en cada súper.

Es el flujo principal; dividir la compra (src/optimizer.py) pasó a ser la
opción. Lo que un súper no vende se reemplaza obligatoriamente por el producto
comparable más parecido (`src/substitutions.py`), porque un total sin esos
productos premiaría al súper que menos tiene. Por defecto va el más PARECIDO y
no el más barato: elegir el más barato también abarataría al súper que más
reemplazos necesita. Las otras opciones viajan como alternativas.

Un producto sin ningún reemplazo aceptable queda "falta": fuera del total, y
ese súper no puede ser el más barato.

El total de cada súper lo calcula `optimize_cart` con ese súper solo: tope y
mínimo del descuento bancario y redondeo a centavos son los mismos que en el
split, así que el ahorro de dividir compara dos números de la misma aritmética.
"""
from src.flattener import flatten_cart_prices
from src.optimizer import DEFAULT_MIN_SPEND_LIMITS, optimize_cart
from src.substitutions import (
    comparable_candidates,
    equivalent_quantity,
    fetch_product_rows,
    format_size,
    weight_of,
)

# El reemplazo por defecto y hasta tres alternativas.
MAX_OPTIONS = 4

# Dividir la compra se ofrece sólo si ahorra al menos esto frente al súper
# completo más barato: cada súper de más es otro checkout, otro login y otro
# carrito que vaciar.
SPLIT_MIN_SAVING = 15000
SPLIT_MIN_SAVING_PCT = 0.20


def find_replacements(cur, cart_items, flat_prices, stores, user_memberships=None,
                      flatten=flatten_cart_prices) -> dict:
    """
    Opciones de reemplazo de lo que cada súper no vende:
    `{tienda: {uid faltante: [opción]}}`, cada lista ordenada por parecido.

    Cada opción se cotiza en ESE súper y a su cantidad equivalente (2 x 1 L ->
    1 x 2 L), porque las promos por cantidad dependen de ella.
    """
    quantities = {item["unified_id"]: item["quantity"] for item in cart_items}
    missing = {s: [u for u in quantities if s not in flat_prices.get(u, {})] for s in stores}
    anchor_rows = fetch_product_rows(cur, {u for uids in missing.values() for u in uids})

    viables = {}
    for store, uids in missing.items():
        rows = {u: anchor_rows[u] for u in uids if u in anchor_rows}
        for uid, cands in comparable_candidates(cur, rows, [store], exclude_uids=quantities).items():
            size = weight_of(rows[uid])
            for cand in cands:
                n = equivalent_quantity(size, quantities[uid], (cand["weight"], cand["unit"]))
                if n is not None:
                    viables.setdefault(store, {}).setdefault(uid, []).append({**cand, "quantity": n})

    # Una cotización por cantidad: el aplanador devuelve un dict por uid.
    by_quantity = {}
    for per_uid in viables.values():
        for cands in per_uid.values():
            for cand in cands:
                by_quantity.setdefault(cand["quantity"], set()).add(cand["uid"])
    prices = {
        q: flatten([{"unified_id": u, "quantity": q} for u in sorted(uids)], user_memberships or [])
        for q, uids in by_quantity.items()
    }

    options = {}
    for store, per_uid in viables.items():
        for uid, cands in per_uid.items():
            priced = [
                {
                    "unified_id": cand["uid"],
                    "name": cand["name"],
                    "size": format_size(cand["weight"], cand["unit"]),
                    "quantity": cand["quantity"],
                    "offer": prices[cand["quantity"]][cand["uid"]][store],
                }
                for cand in cands
                if store in prices[cand["quantity"]].get(cand["uid"], {})
            ]
            if priced:
                options.setdefault(store, {})[uid] = priced[:MAX_OPTIONS]
    return options


def compare_stores(cart_items, flat_prices, replacements, *, stores, delivery_costs,
                   user_cards, user_memberships, promos_by_day, replacement_choices=None) -> dict:
    """
    Una tarjeta por súper y cuál es el más barato entre los completos.

    `promos_by_day` es `[(fecha ISO, promos de ese día)]` empezando por hoy:
    el total es el de hoy, y `best_day` aparece sólo si otro día sale más barato.
    `replacement_choices` es `{tienda: {uid faltante: uid elegido}}`.
    """
    results = [
        _compare_store(store, cart_items, flat_prices, replacements.get(store, {}),
                       (replacement_choices or {}).get(store, {}), delivery_costs,
                       user_cards, user_memberships, promos_by_day)
        for store in stores
    ]
    complete = [r for r in results if r["missing"] == 0 and r["total"] is not None]
    # Los incompletos por cuánto les falta y no por total: por total, el que
    # menos tiene saldría primero.
    results.sort(key=lambda r: (r["missing"], r["total"] is None, r["total"] or 0))
    return {
        "stores": results,
        "cheapest": min(complete, key=lambda r: r["total"])["store_id"] if complete else None,
    }


def _public(option) -> dict:
    return {k: option[k] for k in ("unified_id", "name", "size", "quantity")} | {
        "total_cost": option["offer"]["total_cost"]}


def _compare_store(store, cart_items, flat_prices, options_by_uid, choices, delivery_costs,
                   user_cards, user_memberships, promos_by_day) -> dict:
    in_cart = {item["unified_id"] for item in cart_items}
    used = set()
    lines = {}
    items, store_flat = [], {}

    # Las elecciones del usuario primero: el reemplazo por defecto de otra línea
    # no puede quedarse con el producto que el usuario eligió.
    for item in sorted(cart_items, key=lambda i: i["unified_id"] not in choices):
        uid, q = item["unified_id"], item["quantity"]
        offer = flat_prices.get(uid, {}).get(store)
        if offer:
            lines[uid] = {"unified_id": uid, "quantity": q, "status": "igual",
                          "total_cost": offer["total_cost"]}
            items.append({"unified_id": uid, "quantity": q})
            store_flat[uid] = {store: offer}
            continue

        options = [o for o in options_by_uid.get(uid, [])
                   if o["unified_id"] not in in_cart and o["unified_id"] not in used]
        if not options:
            lines[uid] = {"unified_id": uid, "quantity": q, "status": "falta"}
            continue
        # "" es "ninguno": queda afuera del total como un faltante, pero con
        # sus opciones para poder volver a elegir una.
        if choices.get(uid) == "":
            lines[uid] = {"unified_id": uid, "quantity": q, "status": "falta",
                          "alternatives": [_public(o) for o in options]}
            continue
        chosen = next((o for o in options if o["unified_id"] == choices.get(uid)), options[0])
        used.add(chosen["unified_id"])
        lines[uid] = {"unified_id": uid, "quantity": q, "status": "reemplazo",
                      "total_cost": chosen["offer"]["total_cost"],
                      "replacement": _public(chosen),
                      "alternatives": [_public(o) for o in options]}
        items.append({"unified_id": chosen["unified_id"], "quantity": chosen["quantity"]})
        store_flat[chosen["unified_id"]] = {store: chosen["offer"]}

    ordered = [lines[item["unified_id"]] for item in cart_items]
    result = {
        "store_id": store,
        "lines": ordered,
        "exact": sum(line["status"] == "igual" for line in ordered),
        "replaced": sum(line["status"] == "reemplazo" for line in ordered),
        "missing": sum(line["status"] == "falta" for line in ordered),
        "products": items,
        "total": None,
        "subtotal_products": None,
        "delivery_cost": delivery_costs[store],
        "bank_discount": None,
        "missing_for_min": None,
        "best_day": None,
    }
    if not items:
        return result

    # Mínimo 0: un carrito bajo el mínimo igual muestra su precio, y cuánto le
    # falta se informa aparte.
    def run(promos):
        solved = optimize_cart(
            cart_items=items, user_memberships=user_memberships, user_cards=user_cards,
            min_spend_limits={store: 0}, delivery_costs=delivery_costs,
            flat_prices=store_flat, bank_promos=promos,
        )
        return solved["split"][store]

    today = run(promos_by_day[0][1])
    week = run({store: [{**p, "date": day} for day, promos in promos_by_day
                        for p in promos.get(store, [])]})

    result.update(
        total=today["store_total"],
        subtotal_products=today["subtotal_products"],
        bank_discount=today["bank_discount"],
        missing_for_min=max(0, round(DEFAULT_MIN_SPEND_LIMITS[store] - today["subtotal_products"], 2)) or None,
    )
    if week["store_total"] < today["store_total"]:
        result["best_day"] = {"date": week["bank_discount"]["date"], "total": week["store_total"]}
    return result
