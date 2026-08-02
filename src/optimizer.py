# src/optimizer.py
from ortools.sat.python import cp_model
from src.flattener import flatten_cart_prices

# Cotas de los dominios enteros del modelo, en centavos.
#
# Se derivan de una sola constante en vez de hardcodearse por separado: la cota
# de `subtotal * pct` tiene que ser 100 veces la del subtotal, y tenerlas
# desacopladas hacía que un carrito grande diera "infeasible" por dominio y no
# por economía. Con el 20% de Galicia el corte caía en ~$500.000, un carrito
# perfectamente plausible, y el mensaje de error culpaba a los mínimos de compra.
MAX_SUBTOTAL_CENTS = 10**10  # $100.000.000
MAX_PCT = 100

# Valores por defecto cuando el llamador no los provee. Son constantes de módulo
# y no literales enterrados en la firma porque src/api.py necesita partir de
# ellos para pisar el envío de Coto con el valor real cuando el request no trae
# la tabla por zona del frontend.
#
# Sumar una tienda acá NO es un cambio aislado: `stores` sale de las claves de
# min_spend_limits y más abajo se indexa delivery_costs[j] sin default, así que
# la tabla por zona del frontend (frontend/src/utils/deliveryCosts.js) tiene que
# traer la clave nueva en el mismo commit o /optimize revienta con KeyError.
DEFAULT_MIN_SPEND_LIMITS = {"coto_online": 15000, "dia_online": 12000, "carrefour_online": 20000}
DEFAULT_DELIVERY_COSTS = {"coto_online": 3000, "dia_online": 3000, "carrefour_online": 3500}

def optimize_cart(cart_items, user_memberships=None, user_cards=None, min_spend_limits=None, delivery_costs=None, excluded_stores=None):
    if user_memberships is None: user_memberships = []
    if user_cards is None: user_cards = []
    if min_spend_limits is None: min_spend_limits = dict(DEFAULT_MIN_SPEND_LIMITS)
    if delivery_costs is None: delivery_costs = dict(DEFAULT_DELIVERY_COSTS)
    if excluded_stores is None: excluded_stores = []

    # Carrefour queda sin entrada a propósito, no por olvido: sus descuentos
    # conocidos son de la Tarjeta Carrefour los fines de semana, y este modelo es
    # un porcentaje con tope que se aplica siempre, sin noción de día. Cargarlo
    # acá haría que el optimizador prometa un martes un ahorro que no existe y
    # elija Carrefour por una razón falsa. `bank_promos.get(j, [])` ya devuelve []
    # para las tiendas ausentes. Pendiente: relevar los términos reales.
    bank_promos = {
        "coto_online": [{"card": "galicia", "discount_pct": 20, "cap": 5000, "description": "20% de ahorro con Galicia (Tope $5000)"}],
        "dia_online": [{"card": "macro", "discount_pct": 15, "cap": 3000, "description": "15% de ahorro con Macro (Tope $3000)"}]
    }

    flat_prices = flatten_cart_prices(cart_items, user_memberships)
    products = list(flat_prices.keys())

    # Las tiendas excluidas (ej. Coto cuando no tiene cobertura en la dirección
    # del usuario) se sacan del modelo en vez de encarecerse: no es que salgan
    # caras, es que no pueden entregar.
    excluded_stores = [s for s in excluded_stores if s in min_spend_limits]
    stores = [s for s in min_spend_limits if s not in excluded_stores]

    # Un producto que sólo existía en la tienda excluida se queda sin ninguna
    # variable, y su restricción de asignación pasa a ser `sum([]) == 1`. Eso da
    # infeasible con el mensaje genérico de "no alcanzás el mínimo de compra",
    # que es falso y manda al usuario a agregar productos que no van a arreglar
    # nada. Se detecta antes de armar el modelo para poder explicar el motivo real.
    unavailable = [i for i in products if not any(j in flat_prices[i] for j in stores)]
    if unavailable:
        # El motivo sólo se puede atribuir a la entrega si efectivamente se
        # excluyó alguna tienda; si no, el producto quedó sin ofertas por otra
        # razón y culpar a la dirección sería inventar una explicación.
        if excluded_stores:
            motivo = (
                f"sólo están disponibles en {', '.join(excluded_stores)}, que no puede "
                f"entregar en tu dirección. Sacalos del carrito o elegí otra dirección "
                f"de entrega."
            )
        else:
            motivo = "no están disponibles en ninguna de las tiendas consultadas."

        return {
            "status": "infeasible",
            "message": f"{len(unavailable)} producto(s) del carrito {motivo}",
            "unavailable_products": unavailable,
            "excluded_stores": excluded_stores,
        }

    model = cp_model.CpModel()

    # Variables de Decisión
    x = {(i, j): model.NewBoolVar(f'x_{i}_{j}') for i in products for j in stores if j in flat_prices[i]}
    y = {j: model.NewBoolVar(f'active_store_{j}') for j in stores}

    # Restricciones
    for i in products:
        model.Add(sum(x[i, j] for j in stores if (i, j) in x) == 1)
    
    for (i, j), var_x in x.items():
        model.Add(var_x <= y[j])

    for j in stores:
        costs = [x[i, j] * int(round(flat_prices[i][j]["total_cost"] * 100)) for i in products if (i, j) in x]
        if costs: model.Add(sum(costs) >= y[j] * int(min_spend_limits[j] * 100))

    subtotal_vars = {}
    discount_vars = {}
    store_final_costs_cents = {}
    applied_bank_discounts_info = {}

    for j in stores:
        subtotal_vars[j] = model.NewIntVar(0, MAX_SUBTOTAL_CENTS, f'subtotal_{j}')
        costs = [x[i, j] * int(round(flat_prices[i][j]["total_cost"] * 100)) for i in products if (i, j) in x]
        model.Add(subtotal_vars[j] == sum(costs))

        discount_vars[j] = model.NewIntVar(0, MAX_SUBTOTAL_CENTS, f'discount_{j}')
        best_promo = next((p for p in bank_promos.get(j, []) if p["card"] in user_cards), None)

        if best_promo:
            subtotal_times_pct = model.NewIntVar(0, MAX_SUBTOTAL_CENTS * MAX_PCT, f'subtotal_times_pct_{j}')
            model.Add(subtotal_times_pct == subtotal_vars[j] * best_promo["discount_pct"])
            raw_discount = model.NewIntVar(0, MAX_SUBTOTAL_CENTS, f'raw_discount_{j}')
            model.AddDivisionEquality(raw_discount, subtotal_times_pct, 100)
            model.AddMinEquality(discount_vars[j], [raw_discount, model.NewConstant(int(best_promo["cap"] * 100))])
            applied_bank_discounts_info[j] = best_promo
        else:
            model.Add(discount_vars[j] == 0)

        # x2 porque al subtotal se le suma el envío antes de restar el descuento.
        final_cost = model.NewIntVar(0, MAX_SUBTOTAL_CENTS * 2, f'final_cost_{j}')
        model.Add(final_cost == subtotal_vars[j] + (y[j] * int(delivery_costs[j] * 100)) - discount_vars[j])
        store_final_costs_cents[j] = final_cost

    model.Minimize(sum(store_final_costs_cents.values()))
    solver = cp_model.CpSolver()
    
    if solver.Solve(model) in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        assigned_cart = {}
        total_spent = 0.0

        for j in stores:
            if solver.Value(y[j]) == 1:
                sub = solver.Value(subtotal_vars[j]) / 100.0
                disc = solver.Value(discount_vars[j]) / 100.0
                total = sub + delivery_costs[j] - disc
                total_spent += total
                
                assigned_cart[j] = {
                    "products": [{"unified_id": i, "quantity": next(item["quantity"] for item in cart_items if item["unified_id"] == i),
                                  "total_cost": flat_prices[i][j]["total_cost"]} for i in products if (i, j) in x and solver.Value(x[i, j]) == 1],
                    "subtotal_products": round(sub, 2),
                    "delivery_cost": delivery_costs[j],
                    # La `description` viaja hasta el frontend: sin ella el desglose
                    # solo puede mostrar un genérico "Descuento bancario aplicado",
                    # sin decir qué tarjeta se usó ni cuál era el tope.
                    "bank_discount": {
                        "card": applied_bank_discounts_info[j]["card"],
                        "amount": round(disc, 2),
                        "description": applied_bank_discounts_info[j].get("description")
                    } if j in applied_bank_discounts_info else None,
                    "store_total": round(total, 2)
                }

        return {
            "status": "success",
            "total_spent_net": round(total_spent, 2),
            "split": assigned_cart,
            "excluded_stores": excluded_stores
        }

    return {
        "status": "infeasible",
        "message": "No se encontró una asignación que cumpla los mínimos requeridos.",
        "excluded_stores": excluded_stores
    }