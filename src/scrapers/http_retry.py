# src/scrapers/http_retry.py
"""
Reintento corto para el único fallo que las tres tiendas comparten y que NO es
un error real: un timeout o un 5xx pasajero en una sola página, en medio de un
barrido de ~150-200 requests por noche. `CategoryScrapeError` ya hace lo
correcto ante un fallo genuino (perder la categoría en vez de podar catálogo
vivo con un `seen_skus` incompleto a medias) — lo que faltaba es no tratar un
blip de red como si fuera eso: hoy CUALQUIER categoría PARTIAL hace que
`orchestrator.py` salga con código != 0, y eso pinta el job de GitHub Actions
en rojo aunque haya sido una sola página entre cientos esa noche.

Sólo reintenta lo que un segundo intento puede arreglar: excepciones de
transporte de httpx (timeout, conexión reseteada) y status 429/5xx. Cualquier
otro 4xx, o el 200-con-`errors` de GraphQL cuando rota el hash de la persisted
query (ver `extract_search_payload` en src/scrapers/vtex.py), sigue fallando en
el primer intento — un reintento no cambia esos resultados, sólo demora el
diagnóstico.

Hay un 5xx que NO llega como status: el gateway GraphQL de VTEX contesta
**HTTP 200** con `errors: [{"message": "Request failed with status code 500"}]`
cuando el servicio de búsqueda de atrás falla. Visto en 5 categorías de Día y
Carrefour entre el 20 y el 25-sep-2026, cada una perdida al primer intento. Para
eso existe `is_retryable`: el llamador VTEX pasa
`vtex.is_transient_graphql_error`, que reconoce ese caso y deja afuera el hash
rotado.
"""
import logging
import random
import time
from typing import Callable

import httpx

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def request_with_retry(
    make_request: Callable[[], httpx.Response],
    label: str,
    is_retryable: Callable[[httpx.Response], bool] | None = None,
) -> httpx.Response:
    """
    Ejecuta `make_request` hasta MAX_ATTEMPTS veces.

    Devuelve la respuesta tal cual llegue, incluido su status_code: sigue
    siendo el llamador quien decide si ese status es un error (mismo
    comportamiento que antes de que esta función existiera). La única
    excepción es un status en RETRYABLE_STATUS, que se trata como si hubiera
    sido una excepción de transporte y dispara un nuevo intento. Lo mismo vale
    para una respuesta sobre la que `is_retryable` devuelve True.

    Al agotar los intentos, relanza la última excepción de transporte si la
    hubo; si lo que se agotó fue una racha de status reintentables, devuelve
    esa última respuesta para que el llamador la convierta en el error que ya
    sabe construir (con el detalle de sección/página que este módulo no
    conoce).
    """
    ultima_respuesta = None
    for intento in range(1, MAX_ATTEMPTS + 1):
        try:
            response = make_request()
        except httpx.TransportError as exc:
            if intento == MAX_ATTEMPTS:
                raise
            logger.warning("[%s] intento %s/%s falló (%s), reintentando...",
                            label, intento, MAX_ATTEMPTS, exc)
            time.sleep(_backoff(intento))
            continue

        reintentable = (response.status_code in RETRYABLE_STATUS
                        or (is_retryable is not None and is_retryable(response)))
        if reintentable and intento < MAX_ATTEMPTS:
            logger.warning("[%s] intento %s/%s respondió HTTP %s con error pasajero, reintentando...",
                            label, intento, MAX_ATTEMPTS, response.status_code)
            ultima_respuesta = response
            time.sleep(_backoff(intento))
            continue

        return response

    return ultima_respuesta


def _backoff(intento: int) -> float:
    # 1er reintento ~1-2s, 2do ~2-3s. Mismo orden de magnitud que la pausa
    # anti-bot que los scrapers ya hacen entre páginas (1.5-3s).
    return intento + random.uniform(0, 1.0)
