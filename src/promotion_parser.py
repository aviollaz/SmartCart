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

    # Redacciones que delatan que un precio depende de la tarjeta Carrefour o de
    # su programa de fidelidad ("Mi Carrefour"), relevadas de teasers y
    # discountHighlights reales del sitio. Ver .carrefour() para qué se hace con
    # ellas.
    _CARREFOUR_MEMBERSHIP_MARKERS = (
        "mi crf",
        "mi carrefour",
        "tarjeta carrefour",
        "cuenta digital",
    )

    # Teasers que ninguna regla reconoció, para poder ampliarlas cuando una
    # tienda estrena una redacción. Se imprime una sola vez por nombre distinto:
    # hoy un teaser no reconocido se descarta en silencio y el usuario paga de
    # más sin que nada lo delate.
    _teasers_desconocidos: set = set()

    @staticmethod
    def _vtex(raw_commertial_offer: dict, product_id: str, prefix: str,
              price_gap_membership: str | None = None) -> tuple[float, list]:
        """
        Traduce una oferta comercial de VTEX (`commertialOffer`) al estándar único.

        Es la misma matemática para Día y Carrefour porque es la misma
        plataforma: el precio de lista sale de `ListPrice`, el vigente de `Price`
        y las promos de volumen de `teasers`.

        :param prefix: namespacea los `promo_id` por tienda ("dia", "carrefour").
        :param price_gap_membership: cuando la diferencia entre `ListPrice` y
            `Price` no es un descuento abierto sino un precio de socio/tarjeta,
            el `direct_discount` resultante queda condicionado a esa membresía y
            `evaluate_best_promo()` sólo lo aplica si el usuario la declaró.
        :return: (base_price_calculado, lista_promos_estandarizadas)
        """
        list_price = float(raw_commertial_offer.get("ListPrice", 0.0))
        selling_price = float(raw_commertial_offer.get("Price", 0.0))

        # El base_price inicial es el precio de lista normal
        base_price = list_price if list_price > 0 else selling_price
        parsed_promos = []

        # A. Procesar descuentos fijos directos
        if selling_price < list_price and list_price > 0:
            discount_pct = round(((list_price - selling_price) / list_price) * 100, 2)
            descripcion = f"{int(discount_pct)}% Off Directo"
            if price_gap_membership:
                descripcion = f"{int(discount_pct)}% Off con {price_gap_membership}"

            parsed_promos.append({
                "promo_id": f"{prefix}_direct_{product_id}",
                "type": "direct_discount",
                "description": descripcion,
                "required_quantity": 1,
                "discount_price_per_unit": selling_price,
                "regular_price": list_price,
                "requires_membership": price_gap_membership
            })
            # El precio base real del producto para las fórmulas pasa a ser el rebajado

        # B. Procesar teasers de volumen (3x2, 2x1, 2do al 50%)
        teasers = raw_commertial_offer.get("teasers") or []
        for idx, teaser in enumerate(teasers):
            name = (teaser.get("name") or "").strip().lower()

            if "3x2" in name:
                parsed_promos.append({
                    "promo_id": f"{prefix}_teaser_{product_id}_{idx}",
                    "type": "multi_buy",
                    "description": "Llevando 3 pagás 2",
                    "required_quantity": 3,
                    "free_quantity": 1,
                    "requires_membership": None
                })
            elif "2x1" in name:
                parsed_promos.append({
                    "promo_id": f"{prefix}_teaser_{product_id}_{idx}",
                    "type": "multi_buy",
                    "description": "Llevando 2 pagás 1",
                    "required_quantity": 2,
                    "free_quantity": 1,
                    "requires_membership": None
                })
            elif "2do al 50" in name or "2da al 50" in name:
                parsed_promos.append({
                    "promo_id": f"{prefix}_teaser_{product_id}_{idx}",
                    "type": "conditional_discount",
                    "description": "50% de descuento en la 2da unidad",
                    "required_quantity": 2,
                    "discount_percentage_on_next": 50.0,
                    "requires_membership": None
                })
            elif "2do al 70" in name or "2da al 70" in name:
                parsed_promos.append({
                    "promo_id": f"{prefix}_teaser_{product_id}_{idx}",
                    "type": "conditional_discount",
                    "description": "70% de descuento en la 2da unidad",
                    "required_quantity": 2,
                    "discount_percentage_on_next": 70.0,
                    "requires_membership": None
                })
            elif name and name not in PromoTransformer._teasers_desconocidos:
                PromoTransformer._teasers_desconocidos.add(name)
                print(f"[PROMOS/{prefix}] Teaser sin regla, ignorado: {teaser.get('name')!r}")

        return base_price, parsed_promos

    @staticmethod
    def dia(raw_commertial_offer: dict, product_id: str) -> tuple[float, list]:
        """
        Traduce la oferta comercial y teasers de Día (VTEX) al estándar único.
        Retorna una tupla: (base_price_calculado, lista_promos_estandarizadas)
        """
        return PromoTransformer._vtex(raw_commertial_offer, product_id, "dia")

    @staticmethod
    def carrefour(raw_commertial_offer: dict, product_id: str) -> tuple[float, list]:
        """
        Traduce la oferta comercial y teasers de Carrefour (VTEX) al estándar único.

        Única diferencia real con Día, y el motivo de que no sea un alias:
        en Carrefour el hueco entre `ListPrice` y `Price` suele ser el "Doble
        Precio" de Mi Carrefour (o el precio con Tarjeta Carrefour), no un
        descuento abierto — los `discountHighlights` lo dicen textualmente
        ("PROMO-Mi CRF -mfl-1-6-Dto de 6% Doble Precio"). Tomarlo como directo,
        que es lo que hace la regla de Día, cotizaría a todo el mundo un precio
        de socio y haría ganar a Carrefour splits que en la caja salen más caros.

        Así que cuando el texto delata tarjeta o fidelidad, el descuento se emite
        condicionado a la membresía "mi_carrefour": por defecto el optimizador
        usa el precio de lista (nunca promete de menos) y el usuario que declara
        la membresía en su perfil lo desbloquea. La asimetría es deliberada, la
        misma que con los flags dietarios: quedarse corto sólo cuesta un ahorro,
        pasarse cuesta credibilidad en la caja.
        """
        textos = [
            (promo.get("name") or "")
            for clave in ("teasers", "discountHighlights")
            for promo in (raw_commertial_offer.get(clave) or [])
        ]
        requiere_membresia = any(
            marker in texto.lower()
            for texto in textos
            for marker in PromoTransformer._CARREFOUR_MEMBERSHIP_MARKERS
        )

        return PromoTransformer._vtex(
            raw_commertial_offer,
            product_id,
            "carrefour",
            price_gap_membership="mi_carrefour" if requiere_membresia else None,
        )