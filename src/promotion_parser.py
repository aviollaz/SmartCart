# src/transformers.py
import re

class PromoTransformer:
    @staticmethod
    def coto(raw_discounts: list) -> list:
        """
        Traduce el formato de descuentos crudos de Coto al estándar único.
        """
        parsed_promos = []
        if not raw_discounts:
            return parsed_promos

        for raw_promo in raw_discounts:
            promo_id = raw_promo.get("id")
            discount_txt = raw_promo.get("discountText") or ""
            taking_txt = raw_promo.get("takingText") or ""
            description = f"{discount_txt} {taking_txt}".strip()

            def clean_price(text_price):
                if not text_price:
                    return None
                match = re.search(r'[\d.,]+', text_price)
                if match:
                    val = match.group(0)
                    # Si tiene coma y punto, asumimos que el punto es de miles y la coma es decimal (ej: 2.248,95)
                    if "," in val and "." in val:
                        val = val.replace(".", "").replace(",", ".")
                    # Si solo tiene coma, es el decimal (ej: 2248,95)
                    elif "," in val:
                        val = val.replace(",", ".")
                    # Si tiene punto pero no tiene coma, verificamos si actúa como decimal (ej: 2248.95)
                    # Si tiene un punto seguido de exactamente dos dígitos al final, es decimal.
                    elif "." in val:
                        parts = val.split(".")
                        if len(parts[-1]) != 2:  # Ej: "2.248" -> el punto es de miles
                            val = val.replace(".", "")
                    
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
                parsed_promos.append({
                    "promo_id": f"coto_{promo_id}",
                    "type": "conditional_discount_flat",
                    "description": description,
                    "required_quantity": required_qty,
                    "discount_price_per_unit": discount_price,
                    "regular_price": regular_price,
                    "requires_membership": None
                })
            else:
                parsed_promos.append({
                    "promo_id": f"coto_{promo_id}",
                    "type": "direct_discount",
                    "description": description,
                    "required_quantity": 1,
                    "discount_price_per_unit": discount_price,
                    "regular_price": regular_price,
                    "requires_membership": None
                })
        return parsed_promos

    @staticmethod
    def dia(raw_commertial_offer: dict, product_id: str) -> tuple[float, list]:
        """
        Traduce la oferta comercial y teasers de Día (VTEX) al estándar único.
        Retorna una tupla: (base_price_calculado, lista_promos_estandarizadas)
        """
        list_price = float(raw_commertial_offer.get("ListPrice", 0.0))
        selling_price = float(raw_commertial_offer.get("Price", 0.0))
        
        # El base_price inicial es el precio de lista normal
        base_price = list_price if list_price > 0 else selling_price
        parsed_promos = []

        # A. Procesar descuentos fijos directos
        if selling_price < list_price and list_price > 0:
            discount_pct = round(((list_price - selling_price) / list_price) * 100, 2)
            parsed_promos.append({
                "promo_id": f"dia_direct_{product_id}",
                "type": "direct_discount",
                "description": f"{int(discount_pct)}% Off Directo",
                "required_quantity": 1,
                "discount_price_per_unit": selling_price,
                "regular_price": list_price,
                "requires_membership": None
            })
            # El precio base real del producto para las fórmulas pasa a ser el rebajado

        # B. Procesar teasers de volumen (3x2, 2x1, 2do al 50%)
        teasers = raw_commertial_offer.get("teasers", [])
        for idx, teaser in enumerate(teasers):
            name = teaser.get("name", "").strip().lower()

            if "3x2" in name:
                parsed_promos.append({
                    "promo_id": f"dia_teaser_{product_id}_{idx}",
                    "type": "multi_buy",
                    "description": "Llevando 3 pagás 2",
                    "required_quantity": 3,
                    "free_quantity": 1,
                    "requires_membership": None
                })
            elif "2x1" in name:
                parsed_promos.append({
                    "promo_id": f"dia_teaser_{product_id}_{idx}",
                    "type": "multi_buy",
                    "description": "Llevando 2 pagás 1",
                    "required_quantity": 2,
                    "free_quantity": 1,
                    "requires_membership": None
                })
            elif "2do al 50" in name or "2da al 50" in name:
                parsed_promos.append({
                    "promo_id": f"dia_teaser_{product_id}_{idx}",
                    "type": "conditional_discount",
                    "description": "50% de descuento en la 2da unidad",
                    "required_quantity": 2,
                    "discount_percentage_on_next": 50.0,
                    "requires_membership": None
                })
            elif "2do al 70" in name or "2da al 70" in name:
                parsed_promos.append({
                    "promo_id": f"dia_teaser_{product_id}_{idx}",
                    "type": "conditional_discount",
                    "description": "70% de descuento en la 2da unidad",
                    "required_quantity": 2,
                    "discount_percentage_on_next": 70.0,
                    "requires_membership": None
                })

        return base_price, parsed_promos