# src/scrapers/utils.py
import re

# =====================================================================
# 1. PARSEADOR DE PROMO COTO (Formato con takingText, discountPrice, etc.)
# =====================================================================
def parse_coto_promotion(raw_promo: dict) -> dict:
    """
    Normaliza el formato de las promociones de Coto Digital.
    """
    promo_id = raw_promo.get("id")
    # Limpiamos el texto para la descripción
    discount_txt = raw_promo.get("discountText") or ""
    taking_txt = raw_promo.get("takingText") or ""
    description = f"{discount_txt} {taking_txt}".strip()
    
    def clean_price(text_price):
        if not text_price:
            return None
        match = re.search(r'[\d.,]+', text_price)
        if match:
            # Reemplaza puntos de miles y estandariza coma decimal a punto flotante
            val = match.group(0).replace(".", "").replace(",", ".")
            return float(val)
        return None

    discount_price = clean_price(raw_promo.get("discountPrice"))
    regular_price = clean_price(raw_promo.get("regularPriceText"))

    required_qty = 1
    if taking_txt:
        qty_match = re.search(r'\d+', taking_txt)
        if qty_match:
            required_qty = int(qty_match.group(0))

    if required_qty > 1:
        # Ejemplo: Llevando 2 pagás $1985.11 c/u
        return {
            "promo_id": promo_id,
            "type": "conditional_discount_flat",
            "description": description,
            "required_quantity": required_qty,
            "discount_price_per_unit": discount_price,
            "regular_price": regular_price,
            "requires_membership": None
        }
    else:
        # Ejemplo: Descuento directo de 25% sin mínimos
        return {
            "promo_id": promo_id,
            "type": "direct_discount",
            "description": description,
            "required_quantity": 1,
            "discount_price_per_unit": discount_price,
            "regular_price": regular_price,
            "requires_membership": None
        }


# =====================================================================
# 2. PARSEADOR DE PROMO DÍA (Formato VTEX con Teasers)
# =====================================================================
def parse_dia_product_and_promos(raw_product: dict) -> dict:
    """
    Parsea un producto crudo del JSON de Día (VTEX) y unifica su 
    precio base y su lista de promociones normalizada.
    """
    items = raw_product.get("items", [])
    if not items:
        return {}

    first_item = items[0]
    ean = first_item.get("ean")
    sellers = first_item.get("sellers", [])
    if not sellers:
        return {}

    commertial_offer = sellers[0].get("commertialOffer", {})
    
    # Precios de VTEX en formato float directo
    list_price = float(commertial_offer.get("ListPrice", 0))
    selling_price = float(commertial_offer.get("Price", 0))
    
    # El base_price por defecto es el precio normal sin descuento de volumen
    base_price = list_price if list_price > 0 else selling_price
    parsed_promos = []

    # A. Procesar descuentos directos (ej. 25% Off fijo en puré de tomate)
    if selling_price < list_price and list_price > 0:
        discount_pct = round(((list_price - selling_price) / list_price) * 100, 2)
        parsed_promos.append({
            "promo_id": f"dia_direct_{raw_product.get('productId')}",
            "type": "direct_discount",
            "description": f"{int(discount_pct)}% Off Directo",
            "required_quantity": 1,
            "discount_price_per_unit": selling_price,
            "regular_price": list_price,
            "requires_membership": None
        })
        # Si no requiere volumen para que aplique, el nuevo precio de partida es el rebajado
        base_price = selling_price

    # B. Procesar promociones complejas (teasers como el 3x2 o el 2do al 50%)
    teasers = commertial_offer.get("teasers", [])
    for idx, teaser in enumerate(teasers):
        name = teaser.get("name", "").strip().lower()
        conditions = teaser.get("conditions", {})
        min_qty = conditions.get("minimumQuantity", 1)

        # Usamos expresiones regulares o búsquedas de texto plano para catalogar la promo
        if "3x2" in name:
            parsed_promos.append({
                "promo_id": f"dia_teaser_{raw_product.get('productId')}_{idx}",
                "type": "multi_buy",
                "description": "Llevando 3 pagás 2",
                "required_quantity": 3,
                "free_quantity": 1,
                "requires_membership": None
            })
        elif "2x1" in name:
            parsed_promos.append({
                "promo_id": f"dia_teaser_{raw_product.get('productId')}_{idx}",
                "type": "multi_buy",
                "description": "Llevando 2 pagás 1",
                "required_quantity": 2,
                "free_quantity": 1,
                "requires_membership": None
            })
        elif "2do al 50%" in name or "2da al 50%" in name:
            parsed_promos.append({
                "promo_id": f"dia_teaser_{raw_product.get('productId')}_{idx}",
                "type": "conditional_discount",
                "description": "50% de descuento en la 2da unidad",
                "required_quantity": 2,
                "discount_percentage_on_next": 50.0,
                "requires_membership": None
            })
        elif "2do al 70%" in name or "2da al 70%" in name:
            parsed_promos.append({
                "promo_id": f"dia_teaser_{raw_product.get('productId')}_{idx}",
                "type": "conditional_discount",
                "description": "70% de descuento en la 2da unidad",
                "required_quantity": 2,
                "discount_percentage_on_next": 70.0,
                "requires_membership": None
            })

    return {
        "ean": ean,
        "name": raw_product.get("productName"),
        "brand": raw_product.get("brand"),
        "unit_type": first_item.get("measurementUnit", "un"),
        "store_sku": first_item.get("itemId"),
        "url": raw_product.get("link"),
        "base_price": base_price,
        "in_stock": commertial_offer.get("AvailableQuantity", 0) > 0,
        "raw_promos": parsed_promos
    }