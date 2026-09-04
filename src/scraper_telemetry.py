"""
Telemetría de ejecución del pipeline de scraping.

Una fila por PASO por corrida en `scraper_execution_logs`: las tres tiendas más
los embeddings. Responde las preguntas que el log de texto no responde bien —
cuántos productos trajo Coto el martes, hace cuántos días que Carrefour viene
fallando, cuánto tarda cada tienda — y es la fuente de la que puede colgarse un
tablero sin parsear archivos.

Es deliberadamente independiente de `SmartCartDB`: usa su misma cadena de conexión
pero abre la suya, para que una transacción envenenada del camino de datos no se
lleve puesto el registro de que eso pasó.
"""
import datetime as dt
import logging
import socket
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator

import psycopg

from src.schema import ensure_schema as apply_schema

logger = logging.getLogger(__name__)

# Fail-open ante un error es la mitad del problema: sin timeout, una base que no
# rechaza pero tampoco responde (partición de red, servidor wedgeado) cuelga cada
# escritura durante el timeout TCP del sistema —minutos— y la telemetría termina
# costando más que el paso que mide.
#
# 15s y no los 5 originales: aquel número era "de sobra contra un Postgres
# local", y la base pasó a Neon, que se suspende tras 5 minutos sin actividad y
# tarda varios segundos en despertar. En el barrido nocturno esto está cubierto
# —`_wait_for_db` ya despertó la base antes del primer paso— pero un arranque en
# frío perdería justo la fila que dice que la corrida empezó, que es la que más
# vale. Sigue siendo corto frente a un paso que dura minutos.
CONNECT_TIMEOUT_S = 15

STATUS_RUNNING = "RUNNING"
STATUS_SUCCESS = "SUCCESS"
STATUS_PARTIAL = "PARTIAL"
STATUS_FAILED = "FAILED"

@dataclass
class StepRecord:
    """
    Lo que el orquestador va llenando mientras corre un paso.

    `status` arranca en FAILED a propósito: si el bloque `with` sale por una
    excepción antes de que nadie lo haya puesto en otra cosa, el desenlace honesto
    es que el paso falló. El default optimista sería el que miente.
    """
    supermercado: str
    row_id: int | None = None
    status: str = STATUS_FAILED
    items_scraped: int = 0
    categories_ok: int = 0
    categories_failed: int = 0
    categories_empty: int = 0
    pruned_rows: int | None = None
    pruned_orphans: int | None = None
    prune_skipped_reason: str | None = None
    error_message: str | None = None
    extra: dict = field(default_factory=dict)


class ScraperTelemetry:
    """
    Escribe `scraper_execution_logs`. Nunca levanta.

    Misma doctrina fail-open que `coto_logistics.py` y `analytics.py`: la
    observabilidad no puede tumbar lo observado. Si la telemetría no puede
    escribir, se loguea y el scrapeo sigue — perder la métrica es molesto, perder
    el catálogo del día es roto.
    """

    def __init__(self, conn_string: str, run_id: uuid.UUID | str | None = None) -> None:
        self.conn_string = conn_string
        self.run_id = uuid.UUID(str(run_id)) if run_id else uuid.uuid4()
        self.hostname = socket.gethostname()
        self.enabled = True

    # ---------------------------------------------------------------- esquema

    def ensure_schema(self) -> bool:
        """
        Aplica el DDL de src/schema.py (que incluye `scraper_execution_logs`) y
        devuelve si la telemetría queda usable.

        La tabla se definía acá, y era el único CREATE TABLE del repo: el resto
        del esquema estaba hecho a mano contra la base de desarrollo. Se movió
        junto con las otras dos, pero el patrón que este módulo estrenó —DDL
        idempotente en código, porque un job desatendido no puede depender de que
        alguien se acuerde de correrlo a mano— es el que quedó para todo.
        """
        try:
            with psycopg.connect(self.conn_string, connect_timeout=CONNECT_TIMEOUT_S) as conn:
                apply_schema(conn)
            return True
        except Exception:
            logger.exception(
                "No se pudo preparar scraper_execution_logs; la corrida sigue sin telemetría."
            )
            self.enabled = False
            return False

    # ------------------------------------------------------------------ pasos

    def start_step(self, supermercado: str, start_time: dt.datetime) -> int | None:
        """
        Inserta la fila del paso en estado RUNNING y devuelve su id.

        Se inserta al EMPEZAR y se actualiza al terminar, en vez de un único INSERT
        al final. Si el proceso muere de golpe —`timeout` que escala a SIGKILL, un
        OOM, un reboot— la fila queda en RUNNING para siempre, que es exactamente
        la señal que se quiere: "esto arrancó y nunca terminó". Con un INSERT final
        no quedaría ninguna fila, indistinguible de "el cron nunca disparó".

        `start_time` lo pasa el llamador (no se usa `now()` de Postgres) para que la
        duración mida el paso y no el round-trip a la base.
        """
        if not self.enabled:
            return None
        try:
            with psycopg.connect(self.conn_string, connect_timeout=CONNECT_TIMEOUT_S) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO scraper_execution_logs
                            (run_id, supermercado, start_time, status, hostname)
                        VALUES (%s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (self.run_id, supermercado, start_time, STATUS_RUNNING, self.hostname),
                    )
                    return cur.fetchone()[0]
        except Exception:
            logger.exception("No se pudo registrar el inicio del paso '%s'.", supermercado)
            return None

    def finish_step(self, record: StepRecord, start_time: dt.datetime,
                    end_time: dt.datetime | None = None) -> None:
        """Cierra la fila del paso con su desenlace."""
        if not self.enabled or record.row_id is None:
            return

        end_time = end_time or dt.datetime.now(dt.timezone.utc)
        duration = (end_time - start_time).total_seconds()

        try:
            with psycopg.connect(self.conn_string, connect_timeout=CONNECT_TIMEOUT_S) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE scraper_execution_logs SET
                            end_time             = %s,
                            duration_seconds     = %s,
                            items_scraped        = %s,
                            categories_ok        = %s,
                            categories_failed    = %s,
                            categories_empty     = %s,
                            pruned_rows          = %s,
                            pruned_orphans       = %s,
                            prune_skipped_reason = %s,
                            status               = %s,
                            error_message        = %s
                        WHERE id = %s
                        """,
                        (
                            end_time,
                            round(duration, 2),
                            record.items_scraped,
                            record.categories_ok,
                            record.categories_failed,
                            record.categories_empty,
                            record.pruned_rows,
                            record.pruned_orphans,
                            _truncate(record.prune_skipped_reason),
                            record.status,
                            _truncate(record.error_message),
                            record.row_id,
                        ),
                    )
        except Exception:
            logger.exception("No se pudo cerrar el paso '%s'.", record.supermercado)

    @contextmanager
    def step(self, supermercado: str) -> Iterator[StepRecord]:
        """
        Envuelve un paso: abre la fila, la cierra pase lo que pase, re-levanta.

        El `finally` es lo que garantiza que una excepción —incluida la
        `PipelineAborted` que dispara SIGTERM— deje la fila cerrada con su motivo
        antes de propagar.
        """
        start_time = dt.datetime.now(dt.timezone.utc)
        record = StepRecord(supermercado=supermercado)
        record.row_id = self.start_step(supermercado, start_time)
        try:
            yield record
        except BaseException as exc:
            record.status = STATUS_FAILED
            if not record.error_message:
                record.error_message = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            self.finish_step(record, start_time)


def _truncate(text: str | None, limit: int = 2000) -> str | None:
    """
    Recorta los mensajes largos.

    Un traceback de psycopg con el statement entero puede tener decenas de miles de
    caracteres, y `error_message` es para diagnosticar de un vistazo, no para
    archivar: el traceback completo ya está en el log de archivo.
    """
    if text is None:
        return None
    text = str(text)
    return text if len(text) <= limit else text[: limit - 3] + "..."
