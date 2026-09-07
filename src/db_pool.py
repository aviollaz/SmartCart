# src/db_pool.py
"""
Pool de conexiones opcional, activo sólo en el proceso de la API.

Existe por una razón de despliegue, no de rendimiento local. Contra el Postgres
de `docker-compose` abrir una conexión cuesta ~1 ms y hacerlo una vez por request
es gratis; contra una base administrada en la nube cada conexión es un handshake
TCP + TLS sobre la red, y el costo pasa a ser del orden de la latencia de ida y
vuelta. Una sola llamada a /optimize abre HOY varias conexiones —una en
`_enrich_successful_result`, otra por cada `flatten_cart_prices`, y la heurística
de cierre de tienda llama a esa última una vez por cantidad distinta— así que el
costo se multiplica por algo que no es constante ni evidente leyendo el endpoint.

El pool es OPCIONAL a propósito: `connection()` cae a `psycopg.connect()` si
nadie lo abrió. Los scrapers, el orquestador y los scripts de `src/scripts/` son
procesos de una sola pasada: un pool ahí no ahorra nada, y encima habría que
acordarse de cerrarlo para que el proceso termine. Siguen conectando directo, sin
cambiar una línea. El único que lo abre es `lifespan` en `src/api.py`.

Las conexiones del pool se crean con `row_factory=dict_row`, que es lo que
espera todo el camino de request. Los caminos que quieren tuplas
(`save_store_products`, `prune_missing_store_products`) NO pasan por acá. La
alternativa —pedir el row factory por checkout— obliga a resetearlo al devolver
la conexión, y una conexión que vuelve al pool con estado de la request anterior
es exactamente la clase de bug que no se reproduce en desarrollo.
"""

import logging
import os
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)

# Chico a propósito. El backend corre como un uvicorn de un worker y las queries
# son cortas; lo que se quiere evitar es el handshake, no sostener concurrencia
# alta. Un max_size grande contra una instancia chica (db.t4g.micro tiene un
# `max_connections` de tres dígitos bajos) sólo mueve el problema a la base.
#
# `min_size` es configurable porque contra Neon decide si el proyecto entra o no
# en el plan gratuito, y no es una diferencia de rendimiento: Neon suspende la
# base sola tras 5 minutos SIN ACTIVIDAD, y una conexión abierta cuenta como
# actividad. Con min_size=1 el pool sostiene una permanentemente, la base no se
# suspende nunca y la API prendida consume ~1 CU-hour por hora — los 100
# CU-hours mensuales se agotan en poco más de 4 días y la base se apaga sola.
#
# En desarrollo eso no se nota porque la API corre sólo mientras trabajás; con
# la API publicada 24/7 es la diferencia entre que ande y que no. Por eso el
# despliegue pone SMARTCART_POOL_MIN_SIZE=0: el pool sigue evitando el handshake
# bajo carga, pero deja que la base duerma cuando nadie la usa.
MIN_SIZE = int(os.getenv("SMARTCART_POOL_MIN_SIZE", "1"))
MAX_SIZE = int(os.getenv("SMARTCART_POOL_MAX_SIZE", "8"))

# Segundos que una conexión por encima de `min_size` sobrevive sin usarse.
#
# Va de la mano de lo de arriba y por sí solo no alcanza: con min_size=0 pero el
# max_idle default de psycopg_pool (10 min), la última conexión de una visita
# sigue abierta 10 minutos y recién ahí arranca el reloj de 5 minutos de Neon.
# O sea 15 minutos de cómputo facturado por visita: veinte visitas sueltas en un
# día son 5 horas, y el mes se pasa de los 100 CU-hours igual. Con 60 segundos
# son ~6 minutos por visita.
#
# Lo que se paga a cambio es un handshake TCP+TLS en la primera consulta de cada
# visita nueva, que es exactamente el costo que el pool existe para evitar. Es
# el intercambio correcto para un despliegue de demo: ese handshake se paga una
# vez por sesión y cuesta milisegundos, mientras que agotar las CU-hours apaga
# la base para todo el mundo.
MAX_IDLE_S = float(os.getenv("SMARTCART_POOL_MAX_IDLE", "60"))

# Segundos que una request espera por una conexión libre antes de levantar.
POOL_TIMEOUT_S = 10.0

_pool = None
_pool_conn_string = None


def open_pool(conn_string: str, *, min_size: int = MIN_SIZE, max_size: int = MAX_SIZE) -> bool:
    """
    Abre el pool del proceso. Devuelve si quedó abierto.

    Falla abierto, igual que el resto de la infraestructura del proyecto
    (`coto_logistics.py`, `analytics.py`, `scraper_telemetry.py`): si psycopg_pool
    no está instalado o la base no responde, se loguea y se sigue sin pool. El
    backend queda más lento contra la nube, pero arranca y sirve — que es la misma
    decisión que ya toma `lifespan` al atrapar el error del DDL inicial.

    `psycopg_pool` se importa acá adentro y no arriba, por el mismo motivo que
    playwright en `src/promotions/`: es una dependencia que sólo necesita un
    camino del proyecto, y un import a nivel módulo la volvería obligatoria para
    los scrapers, que no la usan.
    """
    global _pool, _pool_conn_string

    if _pool is not None:
        return True

    try:
        from psycopg_pool import ConnectionPool
    except ImportError:
        logger.warning(
            "psycopg_pool no está instalado; se abre una conexión por request. "
            "Instalar con `pip install 'psycopg[binary,pool]'`."
        )
        return False

    try:
        # open=False + open(wait=False): la base puede no estar lista todavía y
        # eso no puede abortar el arranque. Las conexiones se establecen en
        # background y la primera request que llegue espera hasta POOL_TIMEOUT_S.
        pool = ConnectionPool(
            conninfo=conn_string,
            min_size=min_size,
            max_size=max_size,
            max_idle=MAX_IDLE_S,
            kwargs={"row_factory": dict_row},
            open=False,
        )
        pool.open(wait=False)
    except Exception as e:
        logger.error("No se pudo abrir el pool de conexiones: %s", e)
        return False

    _pool = pool
    _pool_conn_string = conn_string
    logger.info(
        "Pool de conexiones abierto (min=%d, max=%d, max_idle=%.0fs).",
        min_size, max_size, MAX_IDLE_S,
    )
    return True


def close_pool() -> None:
    """Cierra el pool en el shutdown. Idempotente."""
    global _pool, _pool_conn_string

    if _pool is None:
        return

    try:
        _pool.close()
    except Exception as e:
        logger.error("Error al cerrar el pool de conexiones: %s", e)
    finally:
        _pool = None
        _pool_conn_string = None
        logger.info("Pool de conexiones cerrado.")


@contextmanager
def connection(conn_string: str):
    """
    Una conexión con `row_factory=dict_row`, del pool si hay pool.

    La comparación contra `_pool_conn_string` no es ceremonia: `SmartCartDB`
    acepta una cadena explícita, así que un test o un script que apunte a otra
    base dentro del mismo proceso tiene que conectar a ESA base y no recibir una
    conexión del pool de la API.
    """
    if _pool is not None and conn_string == _pool_conn_string:
        with _pool.connection(timeout=POOL_TIMEOUT_S) as conn:
            yield conn
        return

    with psycopg.connect(conn_string, row_factory=dict_row) as conn:
        yield conn


def pool_status() -> dict:
    """
    Estado del pool, para exponerlo en `GET /`.

    Mismo motivo que `analytics_status()`: un pool que no se abrió se ve igual que
    uno sano —la app anda— hasta que alguien mide la latencia y no entiende por
    qué no bajó.
    """
    if _pool is None:
        return {"enabled": False}

    try:
        stats = _pool.get_stats()
        return {
            "enabled": True,
            "size": stats.get("pool_size"),
            "available": stats.get("pool_available"),
            "waiting": stats.get("requests_waiting"),
        }
    except Exception:
        return {"enabled": True}
