# src/flattener.py
import json
from src.database import SmartCartDB


def parse_promotions_json(raw_promos) -> list:
    """
    Deserializa store_products.promotions_json de forma defensiva.

    La columna es de tipo jsonb, así que psycopg ya devuelve una lista de Python:
    pasarla por json.loads() tiraba TypeError y el except lo convertía en "este
    producto no tiene promociones". El efecto era que NINGUNA promoción se
    aplicaba en ningún lado (optimizador, baselines y sugerencias incluidos), en
    silencio. Se sigue tolerando el str por si alguna fila vieja quedó guardada
    como texto, y el doble json.loads porque las hay doblemente serializadas.
    """
    if isinstance(raw_promos, str):
        try:
            raw_promos = json.loads(raw_promos)
            if isinstance(raw_promos, str):
                raw_promos = json.loads(raw_promos)
        except Exception:
            raw_promos = []
    return raw_promos if isinstance(raw_promos, list) else []


def evaluate_best_promo(base_price: float, promotions: list, quantity: int,
                        user_memberships: list = None) -> dict:
    """
    Evalúa todas las promociones de una oferta para una cantidad dada y devuelve
    la que más le haga ahorrar dinero al usuario.

    Es la única implementación de esta matemática en el proyecto: la usan el
    aplanado del carrito (flatten_cart_prices, que alimenta al optimizador) y
    los endpoints de catálogo, que la llaman con quantity=1 para poder mostrar
    en la grilla el precio ya descontado. Evaluar a q=1 no necesita ninguna rama
    especial: direct_discount rige desde la primera unidad, y los otros tres
    tipos tienen su propia guarda `q >= required_quantity`, así que devuelven
    precio de lista solos.

    :return: {total_cost, applied_promo_id, promo_description, applied_promo_type}
             con applied_promo_id en None cuando ninguna promo mejoró el precio.
    """
    if user_memberships is None:
        user_memberships = []

    q = quantity

    # Escenario por defecto: precio regular
    best_total_cost = base_price * q
    applied_promo_id = None
    promo_description = "Precio base sin promociones"
    applied_promo_type = None

    for promo in promotions or []:
        # Validar si el usuario posee la membresía/tarjeta necesaria para la promo
        req_member = promo.get("requires_membership") or promo.get("requires_card")
        if req_member and req_member not in user_memberships:
            continue

        promo_type = promo.get("type")
        current_promo_cost = best_total_cost

        # Caso A: Descuento directo sobre precio regular (ej. 25% Off directo de Coto o Día)
        if promo_type == "direct_discount":
            discount_price = promo.get("discount_price_per_unit")
            if discount_price:
                current_promo_cost = discount_price * q

        # Caso B: Descuento condicionado por volumen fijo (ej. Llevando 2, te queda c/u a X)
        #
        # `discount_price_per_unit` de Coto NO es "cada unidad sale X": es el
        # promedio por unidad llevando exactamente `required_quantity`. Para
        # "50% 2da Llevando 2" sobre una base de 7240, Coto manda 5430, que es
        # (7240 + 3620) / 2. Multiplicarlo linealmente por q regalaba el
        # descuento a las unidades sueltas: q=3 daba 16290 en vez de 18100 y el
        # unitario se congelaba en 5430 para siempre. Se razona por grupos y el
        # resto va a precio de lista, igual que los otros dos condicionales.
        elif promo_type == "conditional_discount_flat":
            req_qty = promo.get("required_quantity", 1)
            discount_price = promo.get("discount_price_per_unit")
            regular_price = promo.get("regular_price") or base_price

            if q >= req_qty and discount_price and req_qty > 0:
                num_groups = q // req_qty
                remainder = q % req_qty
                current_promo_cost = (
                    (num_groups * discount_price * req_qty) +
                    (remainder * regular_price)
                )
            else:
                current_promo_cost = regular_price * q

        # Caso C: Descuento porcentual condicionado en la segunda unidad (ej. 2da al 50%)
        elif promo_type == "conditional_discount":
            req_qty = promo.get("required_quantity", 2)
            discount_pct = promo.get("discount_percentage_on_next", 0.0) / 100.0

            if q >= req_qty:
                num_groups = q // req_qty
                remainder = q % req_qty
                # Costo por grupo: 1 unidad entera + 1 unidad con descuento (para req_qty=2)
                cost_per_group = (req_qty - 1) * base_price + (base_price * (1.0 - discount_pct))
                current_promo_cost = (num_groups * cost_per_group) + (remainder * base_price)

        # Caso D: Promociones múltiples clásicas (3x2, 2x1)
        elif promo_type == "multi_buy":
            req_qty = promo.get("required_quantity", 1)
            free_qty = promo.get("free_quantity", 0)

            if req_qty > 0 and q >= req_qty:
                num_groups = q // req_qty
                remainder = q % req_qty
                paid_per_group = req_qty - free_qty
                current_promo_cost = (
                    (num_groups * paid_per_group * base_price) +
                    (remainder * base_price)
                )

        # Nos quedamos con la promoción que más le haga ahorrar dinero al usuario
        if current_promo_cost < best_total_cost:
            best_total_cost = current_promo_cost
            applied_promo_id = promo.get("promo_id") or promo.get("id")
            promo_description = promo.get("description", "Promoción aplicada")
            applied_promo_type = promo_type

    return {
        "total_cost": best_total_cost,
        "applied_promo_id": applied_promo_id,
        "promo_description": promo_description,
        "applied_promo_type": applied_promo_type,
    }


def flatten_cart_prices(cart_items: list, user_memberships: list = None) -> dict:
    """
    Recibe los productos seleccionados en el carrito y calcula el costo total real
    y óptimo por supermercado, considerando la cantidad y promociones vigentes.

    :param cart_items: lista de diccionarios, ej: [{"unified_id": "prod_7790000000123", "quantity": 3}]
    :param user_memberships: lista de membresías del usuario, ej: ["club_dia"]
    :return: Diccionario plano de costos netos por producto y sucursal.
    """
    if user_memberships is None:
        user_memberships = []

    db = SmartCartDB()

    # 1. Mapeamos la cantidad pedida por cada unified_id para rápido acceso
    quantity_map = {item["unified_id"]: item["quantity"] for item in cart_items}
    unified_ids = list(quantity_map.keys())

    # 2. Obtenemos de la DB los precios y JSONs de promociones estructurados
    raw_store_data = db.get_market_prices_for_cart(unified_ids)

    # Estructura de salida
    flat_matrix = {}

    for row in raw_store_data:
        unified_id = row["unified_product_id"]
        store_id = row["store_id"]
        base_price = float(row["base_price"])
        q = quantity_map[unified_id]

        promotions = parse_promotions_json(row["promotions_json"])

        best = evaluate_best_promo(base_price, promotions, q, user_memberships)
        best_total_cost = best["total_cost"]

        effective_unit_price = best_total_cost / q if q > 0 else base_price

        if unified_id not in flat_matrix:
            flat_matrix[unified_id] = {}

        flat_matrix[unified_id][store_id] = {
            "total_cost": round(best_total_cost, 2),
            "effective_unit_price": round(effective_unit_price, 2),
            "applied_promo_id": best["applied_promo_id"],
            "promo_description": best["promo_description"],
            # Precio de lista DE ESTA tienda. Va en la respuesta para que el
            # frontend pueda tachar el precio previo sin tener que elegirlo él:
            # comparaba contra el mínimo de base_price entre todas las tiendas y
            # podía terminar mostrando el precio de una al lado del de otra.
            "base_unit_price": round(base_price, 2),
            "base_total_cost": round(base_price * q, 2),
            # Permite distinguir una promo que depende de la cantidad de una que
            # no: un direct_discount rige desde la primera unidad, así que
            # anunciarlo como "c/u llevando N" es engañoso.
            "applied_promo_type": best["applied_promo_type"],
            "quantity": q
        }

    return flat_matrix
