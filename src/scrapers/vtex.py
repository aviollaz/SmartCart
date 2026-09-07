# src/scrapers/vtex.py
"""
Lo que Día y Carrefour comparten por correr sobre la misma plataforma.

Las dos tiendas le pegan a la misma operación `productSearchV3` de VTEX con la
misma persisted query, así que la lectura de la respuesta es idéntica y vivía
duplicada a medias: Carrefour tenía la validación y Día no tenía ninguna.
"""
import logging

from src.scrapers.errors import CategoryScrapeError

logger = logging.getLogger(__name__)


def extract_search_payload(response_json, label: str) -> dict:
    """
    Devuelve el bloque `productSearch` de una respuesta de `productSearchV3`.

    LEVANTA `CategoryScrapeError` si la respuesta no es un resultado de búsqueda
    válido. No es paranoia: el `sha256Hash` de la persisted query está fijo y
    salió de una sesión del navegador, así que cuando la tienda lo rota GraphQL
    contesta **HTTP 200** con un array `errors` (PERSISTED_QUERY_NOT_FOUND) y sin
    `data`. Devolver `None` ahí —lo que hacía la versión anterior— terminaba en
    cero productos, que la regla de "página vacía = fin de categoría" lee como un
    barrido exitoso: la categoría se reportaba OK y el pruning borraba todo lo
    que no se alcanzó a recorrer.

    Una categoría realmente agotada NO pasa por acá: es un payload válido con
    `products: []`, y eso se devuelve normalmente. Esa es toda la distinción que
    este módulo existe para hacer.
    """
    if not isinstance(response_json, dict):
        raise CategoryScrapeError(
            f"[{label}] La respuesta no es un objeto JSON: {type(response_json).__name__}."
        )

    errors = response_json.get("errors")
    if errors:
        mensajes = "; ".join(
            str(err.get("message", err)) for err in errors if isinstance(err, dict)
        ) or str(errors)
        logger.error("[%s] La API devolvió errores de GraphQL: %s", label, mensajes)
        logger.error("[%s] Suele significar que el sha256Hash de la persisted query cambió.", label)
        raise CategoryScrapeError(f"[{label}] Errores de GraphQL: {mensajes}")

    data = response_json.get("data")
    if not isinstance(data, dict) or data.get("productSearch") is None:
        raise CategoryScrapeError(
            f"[{label}] Respuesta sin 'data.productSearch': no es un resultado de búsqueda válido."
        )

    return data["productSearch"]


def read_availability(first_item: dict) -> bool:
    """
    Disponibilidad declarada por VTEX para una oferta, con default seguro.

    Antes esto era un `"in_stock": True` literal en los dos scrapers. Medido
    contra el endpoint en vivo (Carrefour, 6 combinaciones de categoría y
    filtros), con los parámetros que el proyecto manda hoy
    —`hideUnavailableItems: True` + `skusFilter: "ALL_AVAILABLE"`— VTEX filtra
    lo agotado del lado del servidor y **todo** lo que vuelve trae
    `AvailableQuantity: 10000`. O sea que ese `True` no era una mentira: era
    verdad por construcción, y leer el campo hoy da exactamente lo mismo.

    Se lee igual, y el motivo es la trampa que dejaba montada. Con
    `hideUnavailableItems: False` la misma categoría devuelve 50 productos de
    los cuales **14 tienen `AvailableQuantity: 0`**. Aflojar ese filtro es un
    cambio de una palabra y una idea razonable (amplía el catálogo), y con el
    `True` hardcodeado habría marcado esas 14 filas como comprables sin que
    nada fallara. El flag pasa a decir lo que la tienda dijo.

    El default es `True` a propósito, no por optimismo: el `sha256Hash` de la
    persisted query fija el conjunto de campos del lado del servidor, así que
    si la tienda lo rota y `AvailableQuantity` desaparece, un default `False`
    marcaría el catálogo entero como agotado y el optimizador no podría armar
    ningún carrito. Ausencia significa "la tienda no dijo", y el proyecto ya
    resuelve esa clase de duda hacia el lado que no rompe.

    Ojo con lo que esto NO arregla: la disponibilidad de VTEX es la de la
    región por defecto, porque el pedido no manda `regionId` ni segment. Un
    producto puede volver disponible acá y que el checkout de la tienda diga
    "no tiene inventario para tu dirección" — que es exactamente lo que pasa.
    Eso es un ítem aparte en docs/TODO.md, no algo que este helper pueda ver.
    """
    for seller in first_item.get("sellers") or []:
        offer = seller.get("commertialOffer") or {}
        if "AvailableQuantity" in offer:
            try:
                return float(offer["AvailableQuantity"]) > 0
            except (TypeError, ValueError):
                return True

    return True
