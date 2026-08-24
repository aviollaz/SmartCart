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
