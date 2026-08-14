"""
Tests de la telemetría de ejecución (src/scraper_telemetry.py).

Corren contra Postgres pero no cargan el modelo. Cada test usa un `run_id` nuevo
—un UUID recién generado no puede colisionar con nada— así que son seguros contra
una base poblada; el fixture borra sus propias filas al terminar.
"""
import datetime as dt
import uuid

import psycopg
import pytest
from psycopg.rows import dict_row

from src.database import SmartCartDB
from src.scraper_telemetry import (
    STATUS_PARTIAL,
    STATUS_RUNNING,
    STATUS_SUCCESS,
    ScraperTelemetry,
    StepRecord,
    _truncate,
)


@pytest.fixture
def telemetry():
    conn_string = SmartCartDB().conn_string
    try:
        with psycopg.connect(conn_string):
            pass
    except Exception as e:
        pytest.skip(f"Postgres no disponible: {e}")

    tel = ScraperTelemetry(conn_string, uuid.uuid4())
    assert tel.ensure_schema()
    yield tel

    with psycopg.connect(conn_string) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM scraper_execution_logs WHERE run_id = %s", (tel.run_id,))


def _filas(tel):
    with psycopg.connect(tel.conn_string, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM scraper_execution_logs WHERE run_id = %s ORDER BY id",
                (tel.run_id,),
            )
            return cur.fetchall()


def test_ensure_schema_es_idempotente(telemetry):
    """Corre en cada arranque del pipeline: la segunda vez no puede fallar."""
    assert telemetry.ensure_schema()
    assert telemetry.ensure_schema()


def test_la_fila_nace_en_running(telemetry):
    """
    Lo que distingue "murió a mitad" de "nunca arrancó".

    Si la fila se insertara recién al terminar, un proceso matado por el watchdog
    no dejaría ninguna, exactamente igual que un cron que nunca disparó.
    """
    inicio = dt.datetime.now(dt.timezone.utc)
    row_id = telemetry.start_step("coto", inicio)
    assert row_id is not None

    fila = _filas(telemetry)[0]
    assert fila["status"] == STATUS_RUNNING
    assert fila["supermercado"] == "coto"
    assert fila["end_time"] is None
    assert fila["duration_seconds"] is None
    assert fila["hostname"]


def test_finish_step_cierra_la_fila(telemetry):
    inicio = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=42)
    rec = StepRecord(supermercado="dia")
    rec.row_id = telemetry.start_step("dia", inicio)
    rec.status = STATUS_SUCCESS
    rec.items_scraped = 427
    rec.categories_ok = 5
    rec.pruned_rows = 12
    rec.pruned_orphans = 3

    telemetry.finish_step(rec, inicio)

    fila = _filas(telemetry)[0]
    assert fila["status"] == STATUS_SUCCESS
    assert fila["items_scraped"] == 427
    assert fila["categories_ok"] == 5
    assert fila["pruned_rows"] == 12
    assert fila["pruned_orphans"] == 3
    assert fila["end_time"] is not None
    assert float(fila["duration_seconds"]) >= 42


def test_context_manager_ciclo_completo(telemetry):
    with telemetry.step("carrefour") as rec:
        rec.status = STATUS_PARTIAL
        rec.items_scraped = 80
        rec.categories_failed = 1
        rec.error_message = "aceites: HTTPError 503"

    fila = _filas(telemetry)[0]
    assert fila["status"] == STATUS_PARTIAL
    assert fila["categories_failed"] == 1
    assert "503" in fila["error_message"]


def test_una_excepcion_deja_la_fila_cerrada_como_failed(telemetry):
    """El `finally` es lo que evita filas huérfanas cuando algo revienta."""
    with pytest.raises(RuntimeError):
        with telemetry.step("coto"):
            raise RuntimeError("persisted query rotada")

    fila = _filas(telemetry)[0]
    assert fila["status"] == "FAILED"
    assert fila["end_time"] is not None
    assert "persisted query rotada" in fila["error_message"]


def test_varios_pasos_comparten_run_id(telemetry):
    for paso in ("coto", "dia", "embeddings"):
        with telemetry.step(paso) as rec:
            rec.status = STATUS_SUCCESS

    filas = _filas(telemetry)
    assert [f["supermercado"] for f in filas] == ["coto", "dia", "embeddings"]
    assert len({f["run_id"] for f in filas}) == 1


def test_el_check_rechaza_un_status_invalido(telemetry):
    """
    La constraint es la que impide que un typo invente un estado nuevo y rompa en
    silencio cualquier consulta que agrupe por status.
    """
    inicio = dt.datetime.now(dt.timezone.utc)
    rec = StepRecord(supermercado="coto")
    rec.row_id = telemetry.start_step("coto", inicio)
    rec.status = "CASI"

    # finish_step es fail-open: loguea el rechazo y no levanta...
    telemetry.finish_step(rec, inicio)
    # ...así que la fila queda en RUNNING en vez de con un estado inventado.
    assert _filas(telemetry)[0]["status"] == STATUS_RUNNING


def test_es_fail_open_con_una_base_inalcanzable():
    """
    La observabilidad no puede tumbar lo observado: con la base caída, todos los
    métodos tienen que devolver sin levantar.
    """
    rota = ScraperTelemetry("postgresql://nadie:nadie@127.0.0.1:1/nada", uuid.uuid4())

    assert rota.ensure_schema() is False
    assert rota.enabled is False
    assert rota.start_step("coto", dt.datetime.now(dt.timezone.utc)) is None

    rec = StepRecord(supermercado="coto", row_id=1, status=STATUS_SUCCESS)
    rota.finish_step(rec, dt.datetime.now(dt.timezone.utc))  # no levanta

    with rota.step("dia") as r:
        r.status = STATUS_SUCCESS


def test_truncate_recorta_los_mensajes_largos():
    """Un traceback de psycopg con el statement entero no entra en un vistazo."""
    assert _truncate(None) is None
    assert _truncate("corto") == "corto"
    largo = _truncate("x" * 5000)
    assert len(largo) == 2000 and largo.endswith("...")
