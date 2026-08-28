#!/usr/bin/env bash
#
# Lo que corre la EC2 al arrancar, cuando EventBridge la prendió a las 03:00.
#
#   arranque -> systemd (smartcart-pipeline.service) -> ESTE script
#     1. ¿hay hold? -> no hace nada y deja la instancia prendida
#     2. baja DATABASE_URL de SSM Parameter Store y arma el .env
#     3. ops/run_pipeline.sh  (sin modificar: es el mismo de cron)
#     4. apaga la instancia
#
# El paso 4 es el que hace que esto cueste centavos en vez de US$12/mes. Si
# fallara, la instancia queda prendida y la única alarma es la de presupuesto —
# por eso el apagado va fuera del `set -e` y corre pase lo que pase.
#
# Ver ops/aws/README.md para la instalación completa.

set -Eeuo pipefail

PROJECT_ROOT="${SMARTCART_ROOT:-/opt/smartcart}"
HOLD_FILE="${SMARTCART_HOLD_FILE:-/etc/smartcart/hold}"
SSM_PARAM="${SMARTCART_SSM_PARAM:-/smartcart/prod/database_url}"
# Margen para que el agente de CloudWatch termine de subir los logs antes de que
# la máquina se apague debajo suyo. Sin esto, la corrida que más importa mirar
# —la que falló— es justo la que puede no llegar a quedar registrada.
DRAIN_SECONDS="${SMARTCART_DRAIN_SECONDS:-45}"

log() { printf '%s | boot_and_scrape | %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }

# ---------------------------------------------------------------------------
# 1. Freno de mano.
#
#    La instancia también se prende a mano para trabajar: abrir el túnel de SSM
#    hacia RDS, provisionar, depurar. Sin este chequeo, prenderla para eso
#    dispararía un barrido completo y después te apagaría la sesión en la cara.
#
#        sudo mkdir -p /etc/smartcart && sudo touch /etc/smartcart/hold
#
#    El archivo va en /etc y no en /run a propósito: /run se vacía en cada
#    arranque, o sea que no podría frenar el arranque que querés frenar.
# ---------------------------------------------------------------------------
if [[ -f "${HOLD_FILE}" ]]; then
    log "HOLD activo (${HOLD_FILE}): no se corre el pipeline y la instancia queda prendida."
    log "Para volver al modo automático: sudo rm ${HOLD_FILE}"
    exit 0
fi

log "----- arranque automático -----"

# ---------------------------------------------------------------------------
# 2. Secreto. La DATABASE_URL vive en SSM Parameter Store (SecureString), no en
#    la AMI ni en el repo: la instancia la lee con su instance profile, así que
#    no hay credencial de larga vida en disco.
#
#    Se escribe con permisos 600 porque run_pipeline.sh hace `source` del .env y
#    ahí adentro va la clave de la base.
# ---------------------------------------------------------------------------
if [[ ! -f "${PROJECT_ROOT}/.env" ]] || ! grep -q '^DATABASE_URL=' "${PROJECT_ROOT}/.env" 2>/dev/null; then
    log "FATAL: falta ${PROJECT_ROOT}/.env o no tiene DATABASE_URL. Ver ops/aws/README.md."
    exit 2
fi

DB_URL="$(aws ssm get-parameter --name "${SSM_PARAM}" --with-decryption \
            --query 'Parameter.Value' --output text 2>/dev/null || true)"

if [[ -n "${DB_URL}" ]]; then
    # Se reemplaza la línea en vez de reescribir el archivo entero: el resto del
    # .env (ANALYTICS_*, SMARTCART_*) es configuración que no vive en SSM.
    tmp="$(mktemp)"
    grep -v '^DATABASE_URL=' "${PROJECT_ROOT}/.env" > "${tmp}" || true
    printf 'DATABASE_URL=%s\n' "${DB_URL}" >> "${tmp}"
    install -m 600 "${tmp}" "${PROJECT_ROOT}/.env"
    rm -f "${tmp}"
    log "DATABASE_URL actualizada desde SSM (${SSM_PARAM})."
else
    # No es fatal: el .env ya tiene una. Si está vencida el orquestador corta
    # solo con rc=2, que es un error legible, y no uno de permisos de AWS.
    log "AVISO: no se pudo leer ${SSM_PARAM}; se usa la DATABASE_URL del .env."
fi

# ---------------------------------------------------------------------------
# 3. El pipeline de siempre. ops/run_pipeline.sh no se toca: es exactamente el
#    mismo que corría bajo cron en WSL, y toma su propio log, su venv y su
#    watchdog. Que sea el mismo archivo es la mitad del valor de esta migración.
# ---------------------------------------------------------------------------
set +e
"${PROJECT_ROOT}/ops/run_pipeline.sh" "$@"
RC=$?
set -e

log "pipeline terminó con rc=${RC}"

# ---------------------------------------------------------------------------
# 4. Apagado. Fuera del `set -e` y sin condicionar al rc: un pipeline que falló
#    igual tiene que apagar la máquina, si no un error de scraping se convierte
#    en una factura.
# ---------------------------------------------------------------------------
log "esperando ${DRAIN_SECONDS}s a que CloudWatch suba los logs..."
sleep "${DRAIN_SECONDS}"

log "----- apagando (rc=${RC}) -----"
shutdown -h now || poweroff -f
