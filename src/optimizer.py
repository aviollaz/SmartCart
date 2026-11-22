# src/optimizer.py
from ortools.sat.python import cp_model
from src.bank_promos import load_bank_promos
from src.flattener import flatten_cart_prices
from src.stores import STORES

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
# Salen del registro de src/stores.py. `stores` sale de las claves de
# min_spend_limits y más abajo se indexa delivery_costs[j] sin default, así que
# la tabla por zona del frontend (frontend/src/utils/deliveryCosts.js) tiene que
# traer todas las tiendas: tests/test_stores.py lo exige.
DEFAULT_MIN_SPEND_LIMITS = {s.id: s.min_spend for s in STORES}
DEFAULT_DELIVERY_COSTS = {s.id: s.delivery_cost for s in STORES}

# Las tiendas sin carrito armado por URL (hoy Coto): el usuario agrega cada
# producto a mano desde una lista de links. Por eso un producto que ahí sale
# hasta MANUAL_CHECKOUT_MARGIN pesos menos va a otro súper, y si sólo aportaba
# casi-empates la tienda no se abre. Las cadenas se ajustan a centavos o un
# peso de la competencia, así que los empates son comunes. El margen sólo entra
# en lo que el solver minimiza: el total informado es siempre el real.
MANUAL_CHECKOUT_MARGIN = 5
MANUAL_CHECKOUT_STORES = frozenset(s.id for s in STORES if s.checkout_domain is None)

# Tope de tiempo del solver. Con seis súper, un carrito de 76 productos y varias
# promos por tienda, demostrar el óptimo tardaba más de 5 minutos y /compare no
# contestaba nunca (nov 2026). Cortado, el solver devuelve la mejor asignación
# que encontró: puede dejar algún ahorro sin encontrar (errar caro), pero el
# total que se informa es siempre el de esa asignación (ver _descuento_real).
SOLVER_TIME_LIMIT_SECONDS = 3.0


def _descuento_real(subtotal_cents, promo):
    """Lo que la promo descuenta sobre ese subtotal, en centavos: el porcentaje
    truncado, con su tope y sólo si se llega al mínimo. Es la misma aritmética
    que el oráculo de tests/test_optimizer_correctness.py."""
    if subtotal_cents < int(promo.get("min_purchase", 0) * 100):
        return 0
    return min(subtotal_cents * promo["discount_pct"] // 100, int(promo["cap"] * 100))

def optimize_cart(cart_items, user_memberships=None, user_cards=None, min_spend_limits=None, delivery_costs=None, excluded_stores=None, flat_prices=None, bank_promos=None, user_excluded_stores=None, max_stores=None):
    """
    `flat_prices` es un escape hatch para quien ya tiene la matriz de precios y
    no quiere pagarla de nuevo: flatten_cart_prices() abre una conexión nueva por
    llamada, y src/strategic_swaps.py simula un cierre de tienda por cada tienda
    activa. Omitirlo mantiene el comportamiento de siempre.

    Quien lo pase tiene que pasarlo YA FILTRADO a los unified_id de `cart_items`:
    `products` sale de sus claves (abajo), así que un UID de más se convierte en
    un producto fantasma con su propia restricción `== 1` y puede volver
    infactible un carrito que no lo es.

    `max_stores` limita cuántas tiendas puede abrir el split. Existe porque
    cada tienda de más es un checkout más que el usuario hace a mano (elegir
    franja, confirmar el pago), y ese costo no está en el objetivo: el usuario
    lo decide mirando `fewer_stores_options` en la respuesta de /optimize.
    `None` es sin límite, el comportamiento de siempre.
    """
    if user_memberships is None: user_memberships = []
    if user_cards is None: user_cards = []
    if min_spend_limits is None: min_spend_limits = dict(DEFAULT_MIN_SPEND_LIMITS)
    if delivery_costs is None: delivery_costs = dict(DEFAULT_DELIVERY_COSTS)
    if excluded_stores is None: excluded_stores = []

    # Los descuentos bancarios salen de src/scrapers/bank_promos.json, que genera
    # `python -m src.scrapers.get_bank_promos`. Ya vienen filtrados al día de hoy;
    # cuál usa cada tienda lo decide el modelo de más abajo.
    #
    # Carrefour antes quedaba afuera a propósito: sus descuentos son de días
    # puntuales y este modelo no tiene noción de día, así que cargarlos habría
    # prometido un martes un ahorro que no existe. Con el filtro por día del
    # loader eso ya no pasa y Carrefour entra sin caso especial.
    #
    # Sin el archivo, load_bank_promos() devuelve la tabla que estaba acá
    # hardcodeada, así que un repo recién clonado se comporta igual que antes.
    if bank_promos is None:
        bank_promos = load_bank_promos()

    if flat_prices is None:
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
        #
        # Y dentro de las excluidas, la causa cambia el consejo: a una tienda que
        # el usuario sacó a mano (`user_excluded_stores`, sólo informativo acá —
        # la exclusión real ya viene en `excluded_stores`) no se le puede echar la
        # culpa de la dirección, y "elegí otra dirección" no arreglaría nada.
        elegidas = [s for s in excluded_stores if s in (user_excluded_stores or [])]
        sin_cobertura = [s for s in excluded_stores if s not in elegidas]
        if sin_cobertura and not elegidas:
            motivo = (
                f"sólo están disponibles en {', '.join(sin_cobertura)}, que no puede "
                f"entregar en tu dirección. Sacalos del carrito o elegí otra dirección "
                f"de entrega."
            )
        elif elegidas:
            motivo = (
                f"sólo están disponibles en {', '.join(excluded_stores)}, que "
                f"{'no están habilitados' if len(excluded_stores) > 1 else 'no está habilitado'} "
                f"para esta compra. Sacalos del carrito o volvé a habilitar "
                f"{'esos supermercados' if len(elegidas) > 1 else 'ese supermercado'}."
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
    compra = {(i, j): model.NewBoolVar(f'x_{i}_{j}') for i in products for j in stores if j in flat_prices[i]}
    activa = {j: model.NewBoolVar(f'active_store_{j}') for j in stores}

    # Restricciones
    for i in products:
        model.Add(sum(compra[i, j] for j in stores if (i, j) in compra) == 1)
    
    for (i, j), var_x in compra.items():
        model.Add(var_x <= activa[j])

    for j in stores:
        costs = [compra[i, j] * int(round(flat_prices[i][j]["total_cost"] * 100)) for i in products if (i, j) in compra]
        if costs: model.Add(sum(costs) >= activa[j] * int(min_spend_limits[j] * 100))

    if max_stores is not None:
        model.Add(sum(activa.values()) <= max_stores)

    subtotal_vars = {}
    discount_vars = {}
    store_final_costs_cents = {}
    promo_vars = {}

    for j in stores:
        subtotal_vars[j] = model.NewIntVar(0, MAX_SUBTOTAL_CENTS, f'subtotal_{j}')
        costs = [compra[i, j] * int(round(flat_prices[i][j]["total_cost"] * 100)) for i in products if (i, j) in compra]
        model.Add(subtotal_vars[j] == sum(costs))

        discount_vars[j] = model.NewIntVar(0, MAX_SUBTOTAL_CENTS, f'discount_{j}')
        # Todas las promos del usuario en esta tienda compiten, y el solver usa a
        # lo sumo una: cuál ahorra más depende del subtotal (un 30% con tope chico
        # pierde contra un 20% sin tope, y una con mínimo no rige si no se llega).
        # `is_membership` decide contra qué eje del perfil se compara: "Comunidad
        # Coto" o "Mi Carrefour" no son tarjetas bancarias y el usuario las declara
        # en user_memberships, así que buscarlas en user_cards no las encontraría.
        promos_del_usuario = [
            p for p in bank_promos.get(j, [])
            if p["card"] in (user_memberships if p.get("is_membership") else user_cards)
        ]
        aplicados = []
        for k, promo in enumerate(promos_del_usuario):
            usa = model.NewBoolVar(f'usa_promo_{j}_{k}')
            # Cotas lineales en vez de división y mínimo exactos: el descuento no
            # puede pasar del porcentaje (truncado: 100 * d <= subtotal * pct) ni
            # del tope, y como el objetivo lo quiere lo más grande posible, en el
            # óptimo vale justo min(truncado, tope). La división y el mínimo
            # explícitos hacían que un carrito grande no terminara nunca.
            aplicado = model.NewIntVar(0, MAX_SUBTOTAL_CENTS, f'applied_discount_{j}_{k}')
            model.Add(100 * aplicado <= subtotal_vars[j] * promo["discount_pct"])
            model.Add(aplicado <= usa * int(promo["cap"] * 100))
            # Redundante en enteros (sin compras no hay subtotal que descontar),
            # pero sin esto la relajación lineal cobra el tope de cada súper
            # abriéndolo "un poquito": la cota quedaba 40% abajo y el solver no
            # podía demostrar el óptimo.
            model.Add(usa <= activa[j])
            # El mínimo se mide contra los productos, sin el envío: si el súper
            # también cuenta el envío, el error queda del lado de cotizar de más.
            # Lineal y no `OnlyEnforceIf`: equivalente (el subtotal nunca es
            # negativo) y la relajación lineal lo ve entero.
            model.Add(subtotal_vars[j] >= int(promo.get("min_purchase", 0) * 100) * usa)
            promo_vars[j, k] = (usa, promo)
            aplicados.append(aplicado)
        model.Add(sum(usa for (tienda, _), (usa, _) in promo_vars.items() if tienda == j) <= 1)
        model.Add(discount_vars[j] == sum(aplicados))

        # x2 porque al subtotal se le suma el envío antes de restar el descuento.
        final_cost = model.NewIntVar(0, MAX_SUBTOTAL_CENTS * 2, f'final_cost_{j}')
        model.Add(final_cost == subtotal_vars[j] + (activa[j] * int(delivery_costs[j] * 100)) - discount_vars[j])
        store_final_costs_cents[j] = final_cost

    margen = int(MANUAL_CHECKOUT_MARGIN * 100)
    model.Minimize(sum(store_final_costs_cents.values())
                   + sum(margen * x for (i, j), x in compra.items() if j in MANUAL_CHECKOUT_STORES))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = SOLVER_TIME_LIMIT_SECONDS
    # Un solo worker con la relajación lineal completa: Cloud Run da 1 CPU, y ahí
    # el portfolio por defecto reparte el tiempo entre workers que no usan la
    # relajación y quedaba 3-4% arriba del óptimo al tope; éste llega al óptimo
    # en un carrito realista de 76 productos (medido con taskset a un núcleo).
    # Además es determinístico.
    solver.parameters.num_workers = 1
    solver.parameters.linearization_level = 2

    if solver.Solve(model) in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        assigned_cart = {}
        total_spent = 0.0

        for j in stores:
            if solver.Value(activa[j]) == 1:
                sub_cents = solver.Value(subtotal_vars[j])
                sub = sub_cents / 100.0
                # El descuento se recalcula de la promo elegida y no se lee del
                # modelo: si el solver cortó por tiempo, su variable puede haber
                # quedado por debajo de lo que la promo da de verdad.
                promo = next((p for (tienda, _), (usa, p) in promo_vars.items()
                              if tienda == j and solver.Value(usa)), None)
                disc = _descuento_real(sub_cents, promo) / 100.0 if promo else 0.0
                promo = promo if disc > 0 else None
                total = sub + delivery_costs[j] - disc
                total_spent += total
                
                assigned_cart[j] = {
                    "products": [{"unified_id": i, "quantity": next(item["quantity"] for item in cart_items if item["unified_id"] == i),
                                  "total_cost": flat_prices[i][j]["total_cost"]} for i in products if (i, j) in compra and solver.Value(compra[i, j]) == 1],
                    "subtotal_products": round(sub, 2),
                    "delivery_cost": delivery_costs[j],
                    # La `description` viaja hasta el frontend: sin ella el desglose
                    # solo puede mostrar un genérico "Descuento bancario aplicado",
                    # sin decir qué tarjeta se usó ni cuál era el tope.
                    "bank_discount": {
                        "card": promo["card"],
                        "amount": round(disc, 2),
                        "description": promo.get("description"),
                        "title": promo.get("title"),
                        "conditions": promo.get("conditions"),
                        # Qué día rige, cuando src/api.py le pasa las promos de
                        # varios días juntas (rango de compra); si no, None.
                        "date": promo.get("date"),
                    } if promo else None,
                    "store_total": round(total, 2)
                }

        return {
            "status": "success",
            "total_spent_net": round(total_spent, 2),
            "split": assigned_cart,
            "excluded_stores": excluded_stores
        }

    # Con un límite de tiendas la causa más probable deja de ser "te falta
    # carrito": el mismo carrito puede ser factible sin límite. Decirlo evita
    # mandar al usuario a agregar productos cuando lo que resuelve es aflojar
    # el límite.
    message = "No se encontró una asignación que cumpla los mínimos requeridos."
    if max_stores is not None:
        message = (
            f"Comprando en como máximo {max_stores} "
            f"{'supermercado' if max_stores == 1 else 'supermercados'} no se llega "
            f"al mínimo de compra con este carrito. Probá sin límite de supermercados."
        )
    return {
        "status": "infeasible",
        "message": message,
        "excluded_stores": excluded_stores
    }