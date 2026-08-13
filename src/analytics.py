"""
Emisión del evento analítico a SmartCart Performance Analyzer.

El microservicio (../SmartCart Performance Analyzer) recibe un evento por cada
carrito optimizado y lo persiste en su propio data warehouse, que es lo que
después consume Power BI. Corre aparte: otro puerto, otra base, otro proceso.

**Invariante que manda sobre todo lo demás en este módulo: la analítica no puede
tumbar ni demorar /optimize.** Si el analyzer está caído, timeoutea o contesta
cualquier cosa, el usuario tiene que recibir su optimización igual y a la misma
velocidad. Por eso todo lo que hace I/O acá corre en un BackgroundTask, con
timeout corto, y no propaga ninguna excepción: sólo loguea.

El contrato completo está en ../SmartCart Performance Analyzer/src/models.py y
rechaza con 422 lo que no cumple. Dos reglas suyas condicionan este archivo:

  - `occurred_at` tiene que traer zona horaria. El emisor corre en Buenos Aires
    (UTC-3): un timestamp naive se interpretaría como UTC y correría cada evento
    tres horas, desalineando todos los cortes diarios del tablero sin que nadie
    lo note. De ahí el datetime.now(timezone.utc).
  - `event_id` es UNIQUE del lado del warehouse. Es la clave de idempotencia: un
    reenvío del mismo evento se descarta en vez de duplicar la facturación de una
    tienda en el market share. Uno nuevo por optimización, nunca por reintento.

El mapeo es deliberadamente tonto: `optimize_cart()` ya devuelve `status`,
`total_spent_net`, `split` y `excluded_stores` con exactamente el nombre y la
forma que espera el contrato, así que acá se reenvía y no se calcula nada. Los
agregados (totales por tienda, conteos) los hace el analyzer, en un solo lugar —
recalcularlos acá sería una segunda definición que se desincroniza en silencio.
"""

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

# Timeout agresivo a propósito. Corre en background, así que no bloquea la
# respuesta, pero un socket colgado igual ocupa un hilo del threadpool que le
# hace falta a /optimize. Perder una métrica es barato; quedarse sin hilos, no.
ANALYTICS_TIMEOUT_SECONDS = 2.0

EVENT_PATH = "/events/cart-optimized"

# Versión del emisor, no del contrato (eso es `schema_version`). Viaja en
# `source.version` para poder atribuir una anomalía del tablero a un deploy.
EMITTER_VERSION = "1.0.0"

# Se loguea UNA sola vez que falta la API key. Un warning por optimización
# inundaría los logs de cualquiera que levante SmartCart sin el analyzer, que es
# el caso normal en desarrollo.
_missing_key_logged = False


def _analytics_url() -> str:
    return os.getenv("ANALYTICS_URL", "http://localhost:8001").rstrip("/")


def _analytics_env() -> str:
    return os.getenv("ANALYTICS_ENV", "dev")


def build_cart_optimized_event(
    request: Any,
    result: Dict[str, Any],
    duration_ms: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Arma el envelope del evento a partir del request y de la respuesta de
    /optimize. Es pura: no hace I/O ni toca `result`.

    Sirve para las DOS salidas del endpoint. Un carrito `infeasible` no trae
    `split`, ni `price_savings`, ni `suggestions`, ni `strategic_swaps`, así que
    todo se lee con `.get()`: se guarda igual, con `split` vacío y los montos en
    None, porque es el KPI de fricción ("% carritos inviables") y descartarlo
    sería justo perder la métrica que explica por qué la gente no compra.

    Los montos van a None y NO a 0: un cero se promediaría como una compra de $0
    y hundiría el ticket promedio con carritos que nunca existieron.
    """
    logistics_coto = ((result.get("logistics") or {}).get("coto") or {})

    # El `or {}` no es defensivo de más: api.py setea price_savings = None si su
    # propio cálculo falla, y `None.get` sería un AttributeError que se comería
    # el evento entero por un número accesorio.
    price_savings = result.get("price_savings") or {}

    return {
        "event_id": str(uuid.uuid4()),
        "event_type": "cart_optimized",
        "schema_version": 1,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "app": "smartcart",
            "env": _analytics_env(),
            "version": EMITTER_VERSION,
        },
        "user": {
            "anon_user_id": request.anon_user_id,
            "zone": request.zone,
            "memberships": request.user_memberships or [],
            "cards": request.user_cards or [],
        },
        "cart": {"items": [item.model_dump() for item in request.cart]},
        "result": {
            "status": result.get("status"),
            "total_spent_net": result.get("total_spent_net"),
            "price_savings_total": price_savings.get("total"),
            "excluded_stores": result.get("excluded_stores") or [],
            "split": result.get("split") or {},
        },
        "engine": {
            "suggestions_count": len(result.get("suggestions") or []),
            "strategic_swaps_count": len(result.get("strategic_swaps") or []),
            "coto_covered": logistics_coto.get("covered"),
            "coto_delivery_source": logistics_coto.get("source"),
            "duration_ms": duration_ms,
        },
    }


def send_cart_optimized_event(payload: Dict[str, Any]) -> None:
    """
    Manda el evento al analyzer. Pensada para correr dentro de un
    BackgroundTask: no devuelve nada y NUNCA lanza.

    Sincrónica y no async a propósito: /optimize es un endpoint `def`, y
    Starlette corre las background tasks sincrónicas en el threadpool, así que
    no hay event loop que bloquear.
    """
    global _missing_key_logged

    api_key = os.getenv("ANALYTICS_API_KEY")
    if not api_key:
        if not _missing_key_logged:
            _missing_key_logged = True
            logger.warning(
                "ANALYTICS_API_KEY no está seteada: no se emiten eventos a "
                "SmartCart Performance Analyzer. (Este aviso sale una sola vez.)"
            )
        return

    url = f"{_analytics_url()}{EVENT_PATH}"

    try:
        response = httpx.post(
            url,
            json=payload,
            headers={"X-API-Key": api_key},
            timeout=ANALYTICS_TIMEOUT_SECONDS,
        )
        # Un 422 silencioso es el peor final posible para esto: el evento se
        # pierde y nadie se entera hasta que el tablero aparece vacío tres meses
        # después. Se loguea el cuerpo, que es donde el contrato explica qué
        # campo rechazó.
        if response.status_code >= 400:
            logger.error(
                "El analyzer rechazó el evento %s (HTTP %s): %s",
                payload.get("event_id"),
                response.status_code,
                response.text[:500],
            )
    except Exception as e:
        # Fail-open, igual que src/coto_logistics.py: que un servicio de terceros
        # se caiga no puede costarle al usuario la optimización que ya se calculó.
        logger.error("No se pudo emitir el evento analítico a %s: %s", url, e)
