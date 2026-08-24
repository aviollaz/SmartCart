"""
Orquestador del pipeline de scraping. Es el entry point desatendido (cron).

    python -m src.scripts.orchestrator                    # las tres tiendas + embeddings
    python -m src.scripts.orchestrator --store dia --skip-embeddings
    python -m src.scripts.orchestrator --prune-dry-run --log-level DEBUG

Qué agrega sobre `run_scrapers.py`, que es el CLI interactivo:

  * logging estructurado a consola y a archivo diario, con un run_id en cada línea;
  * una fila por paso en `scraper_execution_logs` (ver `src/scraper_telemetry.py`);
  * espera activa a que Postgres responda antes de empezar;
  * manejo de SIGTERM, para cerrar la telemetría cuando el watchdog lo mata;
  * exit codes con significado, que es el contrato con el monitoreo.

Lo que NO agrega es lógica de scrapeo: los runners por tienda se importan de
`run_scrapers.py`. Una copia del bucle de categorías acá sería la clase de
duplicación que se desincroniza en silencio.

Exit codes:
    0    todos los pasos SUCCESS
    1    algún paso PARTIAL o FAILED
    2    fallo de arranque (Postgres inalcanzable, configuración rota)
    143  abortado por señal (128 + SIGTERM)
"""
import argparse
import logging
import os
import re
import signal
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv

# Antes de instanciar SmartCartDB, que lee DATABASE_URL en su __init__.
# `load_dotenv` no pisa lo que ya esté exportado, así que el `.env` que carga
# run_pipeline.sh y este archivo conviven sin ambigüedad.
load_dotenv()

import psycopg  # noqa: E402  (después de load_dotenv, a propósito)

from src.database import SmartCartDB  # noqa: E402
from src.logging_setup import setup_logging  # noqa: E402
from src.scraper_telemetry import (  # noqa: E402
    STATUS_FAILED,
    STATUS_PARTIAL,
    STATUS_SUCCESS,
    ScraperTelemetry,
)
from src.scripts import run_scrapers  # noqa: E402

logger = logging.getLogger("orchestrator")

EXIT_OK = 0
EXIT_DEGRADED = 1
EXIT_FATAL = 2
EXIT_ABORTED = 143

EMBEDDINGS_STEP = "embeddings"


class PipelineAborted(RuntimeError):
    """Se recibió SIGTERM/SIGINT. Existe para que el corte pase por los `finally`."""


# --------------------------------------------------------------------- señales


def _install_signal_handlers() -> None:
    """
    Convierte SIGTERM y SIGINT en una excepción.

    `timeout --signal=TERM` (lo que usa run_pipeline.sh) manda SIGTERM: sin esto el
    proceso muere en el acto y la fila del paso en curso queda RUNNING para
    siempre. Levantando una excepción, el context manager de la telemetría alcanza
    a cerrarla con su motivo antes de que el proceso se vaya.
    """
    def handler(signum, _frame):
        nombre = signal.Signals(signum).name
        logger.warning("Señal %s recibida: abortando ordenadamente.", nombre)
        raise PipelineAborted(nombre)

    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)


# ----------------------------------------------------------------- pre-vuelo DB


def _wait_for_db(conn_string: str, timeout_s: int) -> bool:
    """
    Espera a que Postgres acepte conexiones. Devuelve si llegó a responder.

    En WSL2 el modo de falla más común a las 03:00 no es un scraper roto sino que
    el contenedor de Postgres todavía no terminó de levantar, o que Docker Desktop
    ni siquiera está corriendo. Reintentar unos segundos convierte la primera causa
    en un no-evento; la segunda sigue siendo un fallo, pero uno con un mensaje que
    dice qué pasó.
    """
    deadline = time.monotonic() + timeout_s
    intento = 0
    ultimo_error: Exception | None = None

    while True:
        intento += 1
        try:
            with psycopg.connect(conn_string, connect_timeout=5) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
            if intento > 1:
                logger.info("Postgres respondió en el intento %d.", intento)
            return True
        except Exception as exc:
            ultimo_error = exc
            if time.monotonic() >= deadline:
                break
            logger.warning("Postgres todavía no responde (intento %d): %s", intento, exc)
            time.sleep(min(5.0, max(1.0, timeout_s / 10)))

    logger.error("Postgres inalcanzable tras %ds: %s", timeout_s, ultimo_error)
    return False


# ------------------------------------------------------------------ un paso más


def _classify_store(result: run_scrapers.StoreRunResult, prune: dict | None) -> str:
    """
    Traduce el desenlace de una tienda a SUCCESS / PARTIAL / FAILED.

    Que el pruning quede `skipped` cuenta como PARTIAL y no como SUCCESS: sus dos
    frenos (cero SKUs vistos, o un borrado que se lleva más del 30% del alcance)
    sólo se disparan ante la firma de un scraper roto. Un tablero que muestre eso
    en verde es un tablero que esconde justo lo que hay que mirar.

    No cambia con el pruning acotado por categoría: una categoría caída sigue
    siendo PARTIAL, y tiene que seguir siéndolo. Lo que cambia es que ya no arrastra
    consigo el pruning omitido de toda la tienda.
    """
    if result.categories_ok == 0:
        return STATUS_FAILED
    if result.categories_failed:
        return STATUS_PARTIAL
    if prune and prune.get("skipped"):
        return STATUS_PARTIAL
    return STATUS_SUCCESS


def _run_one_store(
    db: SmartCartDB,
    telemetry: ScraperTelemetry,
    store: str,
    prune_mode: str,
) -> str:
    """Corre una tienda con su fila de telemetría y devuelve el status resultante."""
    runner, store_id = run_scrapers.STORE_RUNNERS[store]

    with telemetry.step(store) as rec:
        logger.info("=== %s: iniciando ===", store.upper())
        result = runner(db)

        rec.items_scraped = result.items_scraped
        rec.categories_ok = result.categories_ok
        rec.categories_failed = result.categories_failed
        if result.errors:
            rec.error_message = " | ".join(result.errors)

        prune = _maybe_prune(db, result, store_id, prune_mode)
        if prune:
            rec.pruned_rows = prune["deleted"]
            rec.pruned_orphans = prune["orphans"]
            rec.prune_skipped_reason = prune["reason"] if prune["skipped"] else None

        rec.status = _classify_store(result, prune)
        logger.info(
            "=== %s: %s — %d productos, %d/%d categorías OK ===",
            store.upper(), rec.status, rec.items_scraped,
            result.categories_ok, result.categories_total,
        )
        return rec.status


def _maybe_prune(
    db: SmartCartDB,
    result: run_scrapers.StoreRunResult,
    store_id: str,
    prune_mode: str,
) -> dict | None:
    """Poda las filas obsoletas, si corresponde. `None` significa "no se intentó"."""
    if prune_mode == "off":
        return None
    if not result.ok_categories:
        # El invariante que hace seguro el pruning: `seen_skus` tiene que ser el
        # universo completo de lo que la tienda ofrece hoy, DENTRO del alcance que
        # se poda. Sin ninguna categoría cerrada no hay alcance, y todo parecería
        # discontinuado.
        logger.warning("Pruning de '%s' omitido: ninguna categoría terminó su barrido.",
                       store_id)
        return None

    if not result.complete:
        logger.warning(
            "Pruning de '%s' acotado a %d/%d categorías: las %d que fallaron quedan "
            "fuera del borrado, en vez de dejar sin podar a toda la tienda.",
            store_id, result.categories_ok, result.categories_total,
            result.categories_failed,
        )

    logger.info("Pruning de '%s' (modo: %s, %d categorías en alcance)...",
                store_id, prune_mode, len(result.ok_categories))
    return db.prune_missing_store_products(
        store_id, result.seen_skus, dry_run=(prune_mode == "dry-run"),
        categories=result.ok_categories,
    )


def _run_embeddings(telemetry: ScraperTelemetry) -> str:
    """
    Regenera los embeddings pendientes como un paso más, con su propia fila.

    No es opcional en la práctica: un producto sin `name_embedding` es invisible
    para GET /search. Que falle en silencio es la forma de tener la base poblada y
    el buscador vacío al mismo tiempo, así que acá tiene status propio.
    """
    with telemetry.step(EMBEDDINGS_STEP) as rec:
        logger.info("=== EMBEDDINGS: iniciando ===")
        # Import diferido: carga sentence-transformers, que es lento y sólo hace
        # falta en este paso.
        from src.embeddings import EmbeddingPipeline

        stats = EmbeddingPipeline().generate_and_save_embeddings() or {}
        rec.items_scraped = stats.get("embedded", 0)
        rec.categories_ok = stats.get("batches_ok", 0)
        rec.categories_failed = stats.get("batches_failed", 0)

        if rec.categories_failed:
            rec.status = STATUS_PARTIAL
            rec.error_message = f"{rec.categories_failed} lote(s) fallidos"
        else:
            rec.status = STATUS_SUCCESS

        logger.info(
            "=== EMBEDDINGS: %s — %d productos embebidos, %d lote(s) fallidos ===",
            rec.status, rec.items_scraped, rec.categories_failed,
        )
        return rec.status


# ------------------------------------------------------------------------- CLI


def _build_parser() -> argparse.ArgumentParser:
    parser = run_scrapers.build_arg_parser(
        description="Pipeline de scraping de SmartCart (entry point desatendido)."
    )
    parser.add_argument(
        "--log-dir",
        default=os.getenv("SMARTCART_LOG_DIR", "logs"),
        help="Directorio de logs (default: logs, o SMARTCART_LOG_DIR).",
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("SMARTCART_LOG_LEVEL", "INFO"),
        help="Nivel de logging (default: INFO, o SMARTCART_LOG_LEVEL).",
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=int(os.getenv("SMARTCART_LOG_RETENTION_DAYS", "14")),
        help="Días de logs a conservar (default: 14).",
    )
    parser.add_argument(
        "--db-timeout",
        type=int,
        default=int(os.getenv("SMARTCART_DB_WAIT", "60")),
        help="Segundos a esperar a que Postgres responda antes de abortar (default: 60).",
    )
    return parser


def _resolve_prune_mode(args: argparse.Namespace) -> str:
    """
    'on' | 'off' | 'dry-run'. Los flags del CLI le ganan a SMARTCART_PRUNE.

    El default sigue siendo 'on' porque es el comportamiento actual de
    `run_scrapers.py`: apagarlo en silencio dejaría la base acumulando productos
    discontinuados que el optimizador sigue cotizando.
    """
    mode = os.getenv("SMARTCART_PRUNE", "on").strip().lower()
    if mode not in {"on", "off", "dry-run"}:
        logger.warning("SMARTCART_PRUNE='%s' no es válido; se usa 'on'.", mode)
        mode = "on"
    if args.no_prune:
        mode = "off"
    if args.prune_dry_run:
        mode = "dry-run"
    return mode


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    run_id = uuid.uuid4()
    log_file = setup_logging(
        Path(args.log_dir), run_id,
        level=args.log_level, retention_days=args.retention_days,
    )
    _install_signal_handlers()

    started = time.monotonic()
    logger.info("Pipeline iniciado. run_id=%s log=%s", run_id, log_file)

    db = SmartCartDB()
    # No loguear la cadena entera: lleva la contraseña.
    logger.info("Base de datos: %s", _safe_dsn(db.conn_string))

    if not _wait_for_db(db.conn_string, args.db_timeout):
        # Sin base no hay dónde escribir la telemetría, y fingir lo contrario sería
        # peor que no tenerla. El log de archivo y el exit code 2 son el registro.
        logger.critical("Abortado: Postgres no respondió. No se ejecutó ningún scraper.")
        return EXIT_FATAL

    telemetry = ScraperTelemetry(db.conn_string, run_id)
    telemetry.ensure_schema()

    prune_mode = _resolve_prune_mode(args)
    selected = list(run_scrapers.STORE_RUNNERS) if args.store == "all" else [args.store]
    statuses: dict[str, str] = {}
    exit_code = EXIT_OK

    try:
        for store in selected:
            try:
                statuses[store] = _run_one_store(db, telemetry, store, prune_mode)
            except PipelineAborted:
                statuses[store] = STATUS_FAILED
                raise
            except Exception:
                # `_run_store` ya tolera la caída de una categoría; llegar acá es
                # algo estructural. Una tienda caída no debe tumbar a las otras.
                logger.exception("La tienda '%s' falló por completo.", store)
                statuses[store] = STATUS_FAILED

        if args.skip_embeddings:
            logger.info("Embeddings salteados por --skip-embeddings.")
        elif all(s == STATUS_FAILED for s in statuses.values()):
            logger.warning("Embeddings salteados: ninguna tienda dejó datos nuevos.")
        else:
            try:
                statuses[EMBEDDINGS_STEP] = _run_embeddings(telemetry)
            except PipelineAborted:
                statuses[EMBEDDINGS_STEP] = STATUS_FAILED
                raise
            except Exception:
                logger.exception("Falló la generación de embeddings.")
                statuses[EMBEDDINGS_STEP] = STATUS_FAILED

    except PipelineAborted as exc:
        logger.error("Pipeline abortado por señal %s.", exc)
        exit_code = EXIT_ABORTED

    _log_summary(run_id, statuses, time.monotonic() - started, prune_mode)

    if exit_code == EXIT_OK and any(s != STATUS_SUCCESS for s in statuses.values()):
        exit_code = EXIT_DEGRADED
    return exit_code


def _log_summary(run_id: uuid.UUID, statuses: dict[str, str],
                 elapsed: float, prune_mode: str) -> None:
    logger.info("=" * 62)
    logger.info("RESUMEN run_id=%s  pruning=%s", run_id, prune_mode)
    for paso, status in statuses.items():
        logger.info("  %-12s -> %s", paso, status)
    logger.info("  tiempo total -> %.0fs", elapsed)
    logger.info(
        "  consultá el detalle: SELECT * FROM scraper_execution_logs WHERE run_id = '%s';",
        run_id,
    )
    logger.info("=" * 62)


def _safe_dsn(conn_string: str) -> str:
    """Oculta la contraseña de la cadena de conexión antes de loguearla."""
    dsn = re.sub(r"(password=)[^\s]+", r"\1***", conn_string)
    return re.sub(r"(://[^:/]+:)[^@]+(@)", r"\1***\2", dsn)


if __name__ == "__main__":
    raise SystemExit(main())
