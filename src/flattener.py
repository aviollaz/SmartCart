# src/flattener.py
import json
from database import SmartCartDB

def flatten_cart_prices(cart_items: list, user_memberships: list = None) -> dict:
    """
    Recibe los productos agregados al carrito de compras y calcula el costo plano óptimo
    por supermercado basándose estrictamente en las cantidades solicitadas y promos vigentes.
    """
    if user_memberships is None:
        user_memberships = []

    db = SmartCartDB()
    
    # 1. Mapa EAN -> Cantidad seleccionada
    quantity_map = {item["unified_id"]: item["quantity"] for item in cart_items}
    unified_ids = list(quantity_map.keys())
    
    # 2. Obtenemos datos crudos de las tiendas
    raw_store_data = db.get_market_prices_for_cart(unified_ids)
    
    flat_matrix = {}

    for row in raw_store_data:
        unified_id = row["unified_product_id"]
        store_id = row["store_id"]
        base_price = float(row["base_price"])
        q = quantity_map[unified_id]
        
        # Deserializar promotions_json
        promotions = []
        if row["promotions_json"]:
            try:
                promotions = json.loads(row["promotions_json"])
                if isinstance(promotions, str):
                    promotions = json.loads(promotions)
            except Exception:
                promotions = []

        # Valores base de costo (por si no aplica ninguna promo)
        best_total_cost = base_price * q
        applied_promo_id = None
        promo_description = "Precio base sin promociones"

        # Iterar sobre las promociones para encontrar la que nos dé el menor costo total
        for promo in promotions:
            # Validar fidelización
            req_member = promo.get("requires_membership") or promo.get("requires_card")
            if req_member and req_member not in user_memberships:
                continue

            promo_type = promo.get("type")
            current_promo_cost = best_total_cost

            # Tipo A: Descuento directo sobre precio regular (ej. 25% Off directo)
            if promo_type == "direct_discount":
                discount_price = promo.get("discount_price_per_unit")
                if discount_price:
                    current_promo_cost = discount_price * q

            # Tipo B: Descuento condicionado por volumen fijo (ej. Llevando 2, te queda c/u a X)
            elif promo_type == "conditional_discount_flat":
                req_qty = promo.get("required_quantity", 1)
                discount_price = promo.get("discount_price_per_unit")
                regular_price = promo.get("regular_price") or base_price
                
                if q >= req_qty and discount_price:
                    current_promo_cost = discount_price * q
                else:
                    current_promo_cost = regular_price * q

            # Tipo C: Descuento porcentual condicionado en la segunda unidad (ej. 2da al 50%)
            elif promo_type == "conditional_discount":
                req_qty = promo.get("required_quantity", 2)
                discount_pct = promo.get("discount_percentage_on_next", 0.0) / 100.0
                
                if q >= req_qty:
                    num_groups = q // req_qty
                    remainder = q % req_qty
                    # En un grupo de 2, uno se paga entero y el otro con el % de descuento
                    cost_per_group = (req_qty - 1) * base_price + (base_price * (1.0 - discount_pct))
                    current_promo_cost = (num_groups * cost_per_group) + (remainder * base_price)

            # Tipo D: Promos múltiples clásicas (3x2, 2x1)
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

            # Conservar la promoción que minimiza el gasto
            if current_promo_cost < best_total_cost:
                best_total_cost = current_promo_cost
                applied_promo_id = promo.get("promo_id") or promo.get("id")
                promo_description = promo.get("description", "Promoción aplicada")

        effective_unit_price = best_total_cost / q if q > 0 else base_price

        # Insertar en la matriz que procesará el optimizador
        if unified_id not in flat_matrix:
            flat_matrix[unified_id] = {}

        flat_matrix[unified_id][store_id] = {
            "total_cost": round(best_total_cost, 2),
            "effective_unit_price": round(effective_unit_price, 2),
            "applied_promo_id": applied_promo_id,
            "promo_description": promo_description
        }

    return flat_matrix