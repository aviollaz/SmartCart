"""
Tests del orquestador del pipeline (src/scripts/orchestrator.py).

Python puro: ni Postgres ni el modelo. Los runners de tienda y la telemetría se
reemplazan por dobles, así que lo que se ejercita es la máquina de estados —qué
status sale de cada desenlace, cuándo se poda y cuándo no, y qué exit code se
devuelve—, que es justo la parte que a las 3 de la mañana nadie va a estar mirando.
"""
from contextlib import contextmanager

import pytest

from src.scraper_telemetry import (
    STATUS_FAILED,
    STATUS_PARTIAL,
    STATUS_SUCCESS,
    StepRecord,
)
from src.scripts import orchestrator, run_scrapers


# --------------------------------------------------------------------- dobles


class FakeTelemetry:
    """Registra los pasos en memoria en vez de en Postgres."""

    def __init__(self):
        self.records: list[StepRecord] = []
        self.enabled = True

    def ensure_schema(self):
        return True

    def step(self, supermercado):
        @contextmanager
        def _cm():
            rec = StepRecord(supermercado=supermercado, row_id=len(self.records) + 1)
            self.records.append(rec)
            try:
                yield rec
            except BaseException as exc:
                rec.status = STATUS_FAILED
                rec.error_message = f"{type(exc).__name__}: {exc}"
                raise

        return _cm()

    def by_step(self, nombre) -> StepRecord:
        return next(r for r in self.records if r.supermercado == nombre)


class FakeDB:
    """SmartCartDB mínimo: sólo registra qué podas se pidieron."""

    conn_string = "postgresql://fake/fake"

    def __init__(self, prune_result=None):
        self.prune_calls: list[tuple] = []
        self.prune_result = prune_result or {
            "deleted": 3, "orphans": 1, "skipped": False, "reason": None
        }

    def prune_missing_store_products(self, store_id, seen_skus, dry_run=False):
        self.prune_calls.append((store_id, set(seen_skus), dry_run))
        return self.prune_result


def _result(store="coto", *, ok=3, failed=0, items=120, skus=("a", "b")):
    return run_scrapers.StoreRunResult(
        store=store,
        store_id=f"{store}_online",
        items_scraped=items,
        seen_skus=set(skus),
        categories_total=ok + failed,
        categories_ok=ok,
        categories_failed=failed,
        errors=[f"cat{i}: boom" for i in range(failed)],
    )


@pytest.fixture(autouse=True)
def _restaurar_logging():
    """
    `main()` llama a `setup_logging`, que reemplaza los handlers del root logger.
    Sin restaurarlos, los tests que corren después de éste se quedan escribiendo
    en un tmp_path muerto y pytest pierde la captura de logs.
    """
    import logging

    root = logging.getLogger()
    previos, nivel = list(root.handlers), root.level
    yield
    for h in list(root.handlers):
        root.removeHandler(h)
        h.close()
    for h in previos:
        root.addHandler(h)
    root.setLevel(nivel)


# ---------------------------------------------------------- clasificación de status


def test_todo_ok_es_success():
    prune = {"deleted": 2, "orphans": 0, "skipped": False, "reason": None}
    assert orchestrator._classify_store(_result(), prune) == STATUS_SUCCESS


def test_una_categoria_caida_es_partial():
    """Rescatar 2 de 3 categorías no es un éxito, pero tampoco es un fallo total."""
    assert orchestrator._classify_store(_result(ok=2, failed=1), None) == STATUS_PARTIAL


def test_ninguna_categoria_ok_es_failed():
    assert orchestrator._classify_store(_result(ok=0, failed=3), None) == STATUS_FAILED


def test_pruning_abortado_es_partial():
    """
    Los dos frenos del pruning sólo se disparan ante la firma de un scraper roto
    (cero SKUs, o un borrado que se lleva más del 30%). Pintarlo verde escondería
    exactamente lo que hay que mirar.
    """
    prune = {"deleted": 0, "orphans": 0, "skipped": True,
             "reason": "borraría 900 de 1000 filas (90%)"}
    assert orchestrator._classify_store(_result(), prune) == STATUS_PARTIAL


def test_sin_pruning_no_degrada_el_status():
    """`prune_mode=off` devuelve None, que significa 'no se intentó', no 'falló'."""
    assert orchestrator._classify_store(_result(), None) == STATUS_SUCCESS


# ------------------------------------------------------------------- pruning


def test_barrido_incompleto_no_poda():
    """
    El invariante central: `seen_skus` sólo es podable si es el universo COMPLETO.
    Con categorías caídas, todo lo que no se recorrió parece discontinuado.
    """
    db = FakeDB()
    assert orchestrator._maybe_prune(db, _result(ok=2, failed=1), "coto_online", "on") is None
    assert db.prune_calls == []


def test_barrido_completo_poda():
    db = FakeDB()
    orchestrator._maybe_prune(db, _result(), "coto_online", "on")
    assert db.prune_calls == [("coto_online", {"a", "b"}, False)]


def test_modo_dry_run_propaga_la_bandera():
    db = FakeDB()
    orchestrator._maybe_prune(db, _result(), "coto_online", "dry-run")
    assert db.prune_calls[0][2] is True


def test_modo_off_ni_consulta():
    db = FakeDB()
    assert orchestrator._maybe_prune(db, _result(), "coto_online", "off") is None
    assert db.prune_calls == []


# ------------------------------------------------------- un paso de punta a punta


def test_run_one_store_llena_la_telemetria(monkeypatch):
    db = FakeDB()
    tel = FakeTelemetry()
    monkeypatch.setattr(run_scrapers, "STORE_RUNNERS",
                        {"coto": (lambda _db: _result("coto", items=250), "coto_online")})

    assert orchestrator._run_one_store(db, tel, "coto", "on") == STATUS_SUCCESS

    grabado = tel.by_step("coto")
    assert grabado.items_scraped == 250
    assert grabado.categories_ok == 3
    assert grabado.pruned_rows == 3
    assert grabado.pruned_orphans == 1
    assert grabado.prune_skipped_reason is None


def test_run_one_store_registra_el_motivo_del_pruning_abortado(monkeypatch):
    db = FakeDB(prune_result={"deleted": 0, "orphans": 0, "skipped": True,
                              "reason": "el scrapeo no devolvió ningún SKU"})
    tel = FakeTelemetry()
    monkeypatch.setattr(run_scrapers, "STORE_RUNNERS",
                        {"dia": (lambda _db: _result("dia", items=0, skus=()), "dia_online")})

    assert orchestrator._run_one_store(db, tel, "dia", "on") == STATUS_PARTIAL
    assert tel.by_step("dia").prune_skipped_reason == "el scrapeo no devolvió ningún SKU"


def test_excepcion_en_el_paso_cierra_la_fila_como_failed():
    """El `finally` del context manager es lo que evita filas huérfanas en RUNNING."""
    tel = FakeTelemetry()
    with pytest.raises(ValueError):
        with tel.step("dia") as rec:
            rec.items_scraped = 10
            raise ValueError("la tienda devolvió 500")

    grabado = tel.by_step("dia")
    assert grabado.status == STATUS_FAILED
    assert "la tienda devolvió 500" in grabado.error_message


# --------------------------------------------------------------- modo de pruning


@pytest.mark.parametrize("env,esperado", [
    ("on", "on"), ("off", "off"), ("dry-run", "dry-run"),
    ("DRY-RUN", "dry-run"), ("cualquiera", "on"), (None, "on"),
])
def test_resolve_prune_mode_desde_el_entorno(monkeypatch, env, esperado):
    if env is None:
        monkeypatch.delenv("SMARTCART_PRUNE", raising=False)
    else:
        monkeypatch.setenv("SMARTCART_PRUNE", env)
    args = orchestrator._build_parser().parse_args([])
    assert orchestrator._resolve_prune_mode(args) == esperado


def test_los_flags_le_ganan_al_entorno(monkeypatch):
    monkeypatch.setenv("SMARTCART_PRUNE", "on")
    args = orchestrator._build_parser().parse_args(["--no-prune"])
    assert orchestrator._resolve_prune_mode(args) == "off"

    args = orchestrator._build_parser().parse_args(["--prune-dry-run"])
    assert orchestrator._resolve_prune_mode(args) == "dry-run"


# ------------------------------------------------------------------ exit codes


def _run_main(monkeypatch, tmp_path, runners, telemetry, *, extra_args=()):
    db = FakeDB()
    monkeypatch.setattr(orchestrator, "SmartCartDB", lambda: db)
    monkeypatch.setattr(orchestrator, "_wait_for_db", lambda *_a, **_k: True)
    monkeypatch.setattr(orchestrator, "ScraperTelemetry", lambda *_a, **_k: telemetry)
    monkeypatch.setattr(run_scrapers, "STORE_RUNNERS", runners)
    monkeypatch.delenv("SMARTCART_PRUNE", raising=False)

    argv = ["--log-dir", str(tmp_path), "--skip-embeddings", *extra_args]
    return orchestrator.main(argv), db


def test_exit_0_cuando_todo_sale_bien(monkeypatch, tmp_path):
    runners = {"coto": (lambda _db: _result("coto"), "coto_online")}
    tel = FakeTelemetry()
    rc, db = _run_main(monkeypatch, tmp_path, runners, tel)
    assert rc == orchestrator.EXIT_OK
    assert tel.by_step("coto").status == STATUS_SUCCESS
    assert db.prune_calls  # el barrido completo sí podó


def test_exit_1_si_una_tienda_queda_partial(monkeypatch, tmp_path):
    runners = {
        "coto": (lambda _db: _result("coto"), "coto_online"),
        "dia": (lambda _db: _result("dia", ok=1, failed=2), "dia_online"),
    }
    tel = FakeTelemetry()
    rc, db = _run_main(monkeypatch, tmp_path, runners, tel)
    assert rc == orchestrator.EXIT_DEGRADED
    assert tel.by_step("dia").status == STATUS_PARTIAL
    # Y la tienda degradada no se podó, aunque la otra sí.
    assert [c[0] for c in db.prune_calls] == ["coto_online"]


def test_una_tienda_que_explota_no_tumba_a_la_otra(monkeypatch, tmp_path):
    def revienta(_db):
        raise RuntimeError("no se pudo construir el scraper")

    runners = {
        "carrefour": (revienta, "carrefour_online"),
        "coto": (lambda _db: _result("coto"), "coto_online"),
    }
    tel = FakeTelemetry()
    rc, _db = _run_main(monkeypatch, tmp_path, runners, tel)

    assert rc == orchestrator.EXIT_DEGRADED
    assert tel.by_step("carrefour").status == STATUS_FAILED
    assert tel.by_step("coto").status == STATUS_SUCCESS


def test_exit_2_si_postgres_no_responde(monkeypatch, tmp_path):
    monkeypatch.setattr(orchestrator, "_wait_for_db", lambda *_a, **_k: False)
    llamado = []
    monkeypatch.setattr(run_scrapers, "STORE_RUNNERS",
                        {"coto": (lambda _db: llamado.append(1), "coto_online")})

    rc = orchestrator.main(["--log-dir", str(tmp_path), "--skip-embeddings"])

    assert rc == orchestrator.EXIT_FATAL
    assert llamado == [], "no debe correr ningún scraper si la base no está"


def test_senal_aborta_con_143(monkeypatch, tmp_path):
    def aborta(_db):
        raise orchestrator.PipelineAborted("SIGTERM")

    runners = {"coto": (aborta, "coto_online")}
    tel = FakeTelemetry()
    rc, _db = _run_main(monkeypatch, tmp_path, runners, tel)

    assert rc == orchestrator.EXIT_ABORTED
    assert tel.by_step("coto").status == STATUS_FAILED


def test_las_tiendas_siguientes_no_corren_tras_un_aborto(monkeypatch, tmp_path):
    """SIGTERM significa "terminá ya", no "salteá esta tienda"."""
    corridas = []

    def aborta(_db):
        corridas.append("coto")
        raise orchestrator.PipelineAborted("SIGTERM")

    def segunda(_db):
        corridas.append("dia")
        return _result("dia")

    runners = {"coto": (aborta, "coto_online"), "dia": (segunda, "dia_online")}
    _run_main(monkeypatch, tmp_path, runners, FakeTelemetry())
    assert corridas == ["coto"]


# --------------------------------------------------------------------- varios


def test_safe_dsn_oculta_la_password():
    assert "smartpassword" not in orchestrator._safe_dsn(
        "host=localhost port=5432 dbname=smartcart user=smartuser password=smartpassword"
    )
    assert "secreta" not in orchestrator._safe_dsn(
        "postgresql://smartuser:secreta@localhost:5432/smartcart"
    )
