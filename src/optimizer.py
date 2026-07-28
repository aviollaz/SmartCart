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

def optimize_cart(cart_items, user_memberships=None, user_cards=None, min_spend_limits=None, delivery_costs=None):
    if user_memberships is None: user_memberships = []
    if user_cards is None: user_cards = []
    if min_spend_limits is None: min_spend_limits = {"coto_online": 15000, "dia_online": 12000}
    if delivery_costs is None: delivery_costs = {"coto_online": 3000, "dia_online": 3000}

    bank_promos = {
        "coto_online": [{"card": "galicia", "discount_pct": 20, "cap": 5000, "description": "20% de ahorro con Galicia (Tope $5000)"}],
        "dia_online": [{"card": "macro", "discount_pct": 15, "cap": 3000, "description": "15% de ahorro con Macro (Tope $3000)"}]
    }

    flat_prices = flatten_cart_prices(cart_items, user_memberships)
    products = list(flat_prices.keys())
    stores = list(min_spend_limits.keys())

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
            "split": assigned_cart
        }
    
    return {"status": "infeasible", "message": "No se encontró una asignación que cumpla los mínimos requeridos."}