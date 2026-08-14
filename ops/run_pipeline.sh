#!/usr/bin/env bash
#
# Wrapper del pipeline de scraping de SmartCart, pensado para correr desde cron.
#
#   ./ops/run_pipeline.sh                       # las tres tiendas + embeddings
#   ./ops/run_pipeline.sh --store dia           # los flags pasan al orquestador
#   PIPELINE_TIMEOUT=30m ./ops/run_pipeline.sh
#
# Prepara lo que cron NO hereda del shell interactivo —variables de entorno,
# venv, working directory— y ejecuta `python -m src.scripts.orchestrator` bajo un
# watchdog. La instalación en cron está en ops/crontab.example.
#
# set -E: los traps de ERR se heredan en funciones y subshells.
# set -u: una variable sin definir corta acá y no doce líneas más abajo con una
#         ruta vacía que borra lo que no debía.
# pipefail: un fallo en medio de un pipe no queda enmascarado por el último comando.
set -Eeuo pipefail

# El script se ubica solo en vez de llevar rutas absolutas hardcodeadas: funciona
# igual en /mnt/c/..., en ~/SmartCart o en /opt/smartcart, sin editarlo.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

LOG_DIR="${SMARTCART_LOG_DIR:-${PROJECT_ROOT}/logs}"
VENV_PATH="${SMARTCART_VENV:-${PROJECT_ROOT}/.venv-linux}"
PIPELINE_TIMEOUT="${PIPELINE_TIMEOUT:-2h}"
AUTOSTART_DB="${SMARTCART_AUTOSTART_DB:-0}"

# ---------------------------------------------------------------------------
# 1. Log. Se crea el directorio antes que nada: todo lo que sigue tiene que poder
#    dejar rastro, incluidos sus propios fallos.
# ---------------------------------------------------------------------------
mkdir -p "${LOG_DIR}"
PIPELINE_LOG="${LOG_DIR}/pipeline_$(date +%Y%m%d).log"

# De acá en adelante, stdout y stderr del script Y de todos sus hijos quedan
# archivados — incluido lo que escriban subprocesos por fuera del logging de
# Python (httpx, chromium, el propio timeout).
exec >>"${PIPELINE_LOG}" 2>&1

log() { printf '%s | run_pipeline | %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
die() { log "FATAL: $*"; exit 2; }

log "----- inicio (pid=$$, root=${PROJECT_ROOT}) -----"

# ---------------------------------------------------------------------------
# 2. Variables de entorno.
#    Esto es `source` de shell, no un parser de .env: los valores con espacios
#    TIENEN que ir entrecomillados en el archivo. Por eso DATABASE_URL se
#    documenta en formato URL (postgresql://...), que no lleva espacios, y no en
#    formato libpq (host=... port=...), que sí.
#    `set -a` exporta todo lo que se defina mientras esté activo.
# ---------------------------------------------------------------------------
if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${PROJECT_ROOT}/.env"
    set +a
    log ".env cargado."
else
    log "AVISO: no hay .env; se usan los defaults del código."
fi

# ---------------------------------------------------------------------------
# 3. Postgres. Por default NO se levanta el contenedor: arrancar servicios a las
#    3 de la mañana es un efecto colateral que conviene que sea una decisión
#    explícita. El orquestador igual espera a que la base responda (--db-timeout).
# ---------------------------------------------------------------------------
if [[ "${AUTOSTART_DB}" == "1" ]]; then
    log "SMARTCART_AUTOSTART_DB=1: levantando el contenedor de Postgres..."
    (cd "${PROJECT_ROOT}" && docker compose up -d) || log "AVISO: docker compose falló; se sigue igual."
fi

# ---------------------------------------------------------------------------
# 4. Entorno virtual, por ruta absoluta.
#    En WSL2 el venv creado desde Windows NO sirve: tiene Scripts/ y .exe en vez
#    de bin/ y binarios ELF. Hace falta uno propio de Linux (.venv-linux por
#    default), creado desde WSL con `python3 -m venv .venv-linux`.
# ---------------------------------------------------------------------------
[[ -f "${VENV_PATH}/bin/activate" ]] || die "no existe el venv en ${VENV_PATH} (¿es un venv de Windows? necesitás uno de Linux)"
# shellcheck disable=SC1091
source "${VENV_PATH}/bin/activate"
log "venv activo: $(python -V 2>&1) desde ${VENV_PATH}"

# ---------------------------------------------------------------------------
# 5. Working directory. Obligatorio, no cosmético: pytest.ini fija `pythonpath = .`
#    y todo el backend se importa como `src.modulo`, así que `python -m` exige
#    estar parado en la raíz del repo.
# ---------------------------------------------------------------------------
cd "${PROJECT_ROOT}"

# ---------------------------------------------------------------------------
# 6. Ejecución bajo watchdog.
#    `scraper_dia.scrape_entire_category` no tiene tope de páginas (a diferencia
#    del MAX_PAGES=60 de Carrefour): un endpoint que devuelva siempre la misma
#    página lo deja en bucle y el job de mañana se encuentra el lock tomado.
#    --signal=TERM primero, para que el orquestador cierre su fila de telemetría;
#    --kill-after manda SIGKILL 60s después si no se murió solo.
#    Sin `exec`, a propósito: hace falta seguir vivo para registrar cómo terminó.
# ---------------------------------------------------------------------------
START_TS=$(date +%s)
set +e
timeout --signal=TERM --kill-after=60s "${PIPELINE_TIMEOUT}" \
    python -m src.scripts.orchestrator "$@"
RC=$?
set -e
ELAPSED=$(( $(date +%s) - START_TS ))

case "${RC}" in
    0)   log "OK — todos los pasos SUCCESS (${ELAPSED}s)" ;;
    1)   log "DEGRADADO — algún paso PARTIAL/FAILED, ver scraper_execution_logs (${ELAPSED}s)" ;;
    2)   log "FATAL — fallo de arranque, no corrió ningún scraper (${ELAPSED}s)" ;;
    124) log "TIMEOUT — el pipeline superó ${PIPELINE_TIMEOUT} y fue interrumpido (${ELAPSED}s)" ;;
    143) log "ABORTADO — el pipeline recibió SIGTERM (${ELAPSED}s)" ;;
    *)   log "rc=${RC} inesperado (${ELAPSED}s)" ;;
esac

log "----- fin (rc=${RC}) -----"
exit "${RC}"
