"""
Configuración de logging para el pipeline desatendido.

El resto del backend usa `logging.basicConfig(handlers=[StreamHandler()])`: sirve
para uvicorn en primer plano, pero un job de cron necesita además un archivo, un
identificador que ate cada línea a su corrida y una política de retención.
"""
import datetime as dt
import logging
import sys
import uuid
from pathlib import Path

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-28s | run=%(run_id)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
FILE_PREFIX = "orchestrator_"


class _RunIdFilter(logging.Filter):
    """
    Inyecta el run_id en cada record.

    Va como filtro y no como LoggerAdapter porque tiene que alcanzar también a los
    loggers de terceros (httpx, sentence-transformers) y a los módulos existentes
    que ya hacen `logging.getLogger(__name__)` sin saber nada del pipeline. Con el
    run_id en cada línea, aislar una corrida en el archivo es un grep, y cruzarla
    con su fila de `scraper_execution_logs` es inmediato.
    """

    def __init__(self, run_id: str) -> None:
        super().__init__()
        self.run_id = run_id

    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = self.run_id
        return True


def setup_logging(
    log_dir: Path,
    run_id: uuid.UUID | str,
    level: str = "INFO",
    retention_days: int = 14,
) -> Path:
    """
    Deja el root logger escribiendo a consola y a `<log_dir>/orchestrator_YYYYMMDD.log`.

    Devuelve la ruta del archivo.

    Sobre la rotación: NO se usa `TimedRotatingFileHandler`. Ese handler rota
    cuando el proceso sigue vivo al cruzar la medianoche, y un job que arranca a
    las 03:00 y dura minutos nunca la cruza — escribiría siempre en el mismo
    archivo, creciendo sin límite y sin borrar nada nunca. Para un proceso corto y
    diario la rotación correcta es la fecha en el nombre (el propio cron abre uno
    nuevo cada día) más una limpieza explícita por antigüedad.
    """
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    short_id = str(run_id)[:8]
    log_file = log_dir / f"{FILE_PREFIX}{dt.date.today():%Y%m%d}.log"

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    run_filter = _RunIdFilter(short_id)

    # `mode="a"`: varias corridas del mismo día comparten archivo y se distinguen
    # por su run_id. Un `"w"` haría que un re-run manual pise el log del cron.
    file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.addFilter(run_filter)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(run_filter)

    root = logging.getLogger()
    root.setLevel(getattr(logging, str(level).upper(), logging.INFO))
    # Idempotente: sin esto, importar el orquestador dos veces en un test duplica
    # cada línea. `basicConfig` no alcanza porque no hace nada si ya hay handlers.
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    root.addHandler(file_handler)
    root.addHandler(stream_handler)

    # httpx emite una línea INFO por request: con ~5 categorías x N páginas x 3
    # tiendas, ahoga todo lo demás en el archivo.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    _install_excepthook()
    _prune_old_logs(log_dir, retention_days)

    return log_file


def _install_excepthook() -> None:
    """
    Manda las excepciones no atrapadas al logger.

    Sin esto un crash duro sale sólo por stderr y termina en el redirect del cron,
    no en el archivo estructurado — o sea, justo el evento que más se quiere
    encontrar es el único que no está donde se lo busca.
    """
    def handler(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logging.getLogger("orchestrator").critical(
            "Excepción no atrapada.", exc_info=(exc_type, exc_value, exc_tb)
        )

    sys.excepthook = handler


def _prune_old_logs(log_dir: Path, retention_days: int) -> int:
    """
    Borra los `orchestrator_*.log` más viejos que `retention_days`. Devuelve cuántos.

    Se apoya en la fecha del NOMBRE, no en el mtime: un archivo del que se leyó o
    se hizo backup no debería parecer más nuevo de lo que es. Un nombre que no
    parsea se ignora en vez de borrarse — nunca borrar lo que no se entiende.
    """
    if retention_days <= 0:
        return 0

    cutoff = dt.date.today() - dt.timedelta(days=retention_days)
    borrados = 0

    for path in log_dir.glob(f"{FILE_PREFIX}*.log"):
        stamp = path.stem[len(FILE_PREFIX):]
        try:
            fecha = dt.datetime.strptime(stamp, "%Y%m%d").date()
        except ValueError:
            continue
        if fecha < cutoff:
            try:
                path.unlink()
                borrados += 1
            except OSError:
                # Limpiar logs no puede tumbar el pipeline.
                logging.getLogger(__name__).warning("No se pudo borrar %s.", path)

    return borrados
