"""
Tests de la configuración de logging del pipeline (src/logging_setup.py).

Python puro. Cubren sobre todo `_prune_old_logs`, que BORRA archivos: es la clase
de rutina que conviene tener probada antes de soltarla a correr sola todas las
noches sobre un directorio del que nadie mira el contenido.
"""
import datetime as dt
import logging
import uuid

import pytest

from src.logging_setup import FILE_PREFIX, _prune_old_logs, setup_logging


@pytest.fixture
def restaurar_logging():
    """
    `setup_logging` reemplaza los handlers del root logger. Sin esto, los tests
    que corren después se quedan escribiendo en el tmp_path de éste.
    """
    root = logging.getLogger()
    previos, nivel = list(root.handlers), root.level
    yield
    for h in list(root.handlers):
        root.removeHandler(h)
        h.close()
    for h in previos:
        root.addHandler(h)
    root.setLevel(nivel)


def _log_de_hace(dias: int):
    fecha = dt.date.today() - dt.timedelta(days=dias)
    return f"{FILE_PREFIX}{fecha:%Y%m%d}.log"


def test_escribe_en_un_archivo_con_la_fecha(tmp_path, restaurar_logging):
    log_file = setup_logging(tmp_path, uuid.uuid4())

    assert log_file.name == f"{FILE_PREFIX}{dt.date.today():%Y%m%d}.log"
    logging.getLogger("prueba").info("hola")
    logging.shutdown()
    assert "hola" in log_file.read_text(encoding="utf-8")


def test_cada_linea_lleva_el_run_id(tmp_path, restaurar_logging):
    """
    El run_id es lo que ata una línea del archivo a su fila de
    scraper_execution_logs. Va por filtro, así que tiene que alcanzar también a
    los loggers de módulos que no saben nada del pipeline.
    """
    run_id = uuid.uuid4()
    log_file = setup_logging(tmp_path, run_id)

    logging.getLogger("src.database").warning("algo raro")
    logging.shutdown()

    contenido = log_file.read_text(encoding="utf-8")
    assert f"run={str(run_id)[:8]}" in contenido
    assert "src.database" in contenido


def test_no_duplica_handlers_si_se_llama_dos_veces(tmp_path, restaurar_logging):
    setup_logging(tmp_path, uuid.uuid4())
    log_file = setup_logging(tmp_path, uuid.uuid4())

    logging.getLogger("prueba").info("una sola vez")
    logging.shutdown()

    assert log_file.read_text(encoding="utf-8").count("una sola vez") == 1


def test_varias_corridas_del_mismo_dia_comparten_archivo(tmp_path, restaurar_logging):
    """Modo 'a': un re-run manual no debe pisar el log que dejó el cron."""
    setup_logging(tmp_path, uuid.uuid4())
    logging.getLogger("prueba").info("primera corrida")
    log_file = setup_logging(tmp_path, uuid.uuid4())
    logging.getLogger("prueba").info("segunda corrida")
    logging.shutdown()

    contenido = log_file.read_text(encoding="utf-8")
    assert "primera corrida" in contenido and "segunda corrida" in contenido


def test_retencion_borra_lo_viejo_y_respeta_lo_reciente(tmp_path):
    viejo = tmp_path / _log_de_hace(40)
    limite = tmp_path / _log_de_hace(14)   # justo en el borde: no se borra
    reciente = tmp_path / _log_de_hace(2)
    for p in (viejo, limite, reciente):
        p.write_text("x", encoding="utf-8")

    assert _prune_old_logs(tmp_path, retention_days=14) == 1
    assert not viejo.exists()
    assert limite.exists() and reciente.exists()


def test_retencion_no_toca_archivos_ajenos(tmp_path):
    """
    Sólo los `orchestrator_*.log` con fecha parseable. Un nombre que no se entiende
    se ignora en vez de borrarse: nunca borrar lo que no se entiende. Los nombres
    de abajo son los que dejaban el wrapper de cron y su redirect, y se conservan
    como casos de prueba aunque esos archivos ya no se generen — lo que se está
    verificando es la regla, no esos nombres en particular.
    """
    ajenos = [
        tmp_path / "pipeline_19990101.log",
        tmp_path / "cron_boot_19990101.log",
        tmp_path / f"{FILE_PREFIX}sin_fecha.log",
        tmp_path / "notas.txt",
    ]
    for p in ajenos:
        p.write_text("x", encoding="utf-8")

    assert _prune_old_logs(tmp_path, retention_days=1) == 0
    assert all(p.exists() for p in ajenos)


def test_retencion_desactivada_no_borra_nada(tmp_path):
    viejo = tmp_path / _log_de_hace(999)
    viejo.write_text("x", encoding="utf-8")

    assert _prune_old_logs(tmp_path, retention_days=0) == 0
    assert viejo.exists()


def test_crea_el_directorio_si_no_existe(tmp_path, restaurar_logging):
    destino = tmp_path / "no" / "existe" / "todavia"
    log_file = setup_logging(destino, uuid.uuid4())
    assert log_file.parent.is_dir()
