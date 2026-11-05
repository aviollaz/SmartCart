"""
Hook Stop: corre el chequeo del repo (CLAUDE.md, "Harness") antes de dejar
que el agente dé la tarea por terminada.

Salida 0 = puede parar. Salida 2 = Claude Code bloquea el stop y le pasa el
stderr al agente, que sigue trabajando con ese error a la vista.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
COLA = 60  # líneas de salida que vuelven al agente

# La base de docker-compose, siempre. Sin esto conftest.py carga el .env y el
# chequeo correría contra Neon en cada stop, gastando CU-hours. Si Docker está
# apagado, los tests de Postgres se saltean (y CI los corre de verdad).
# `connect_timeout` es obligatorio: en Windows un connect a un puerto sin nadie
# escuchando no recibe el rechazo y psycopg espera para siempre (medido: el
# suite quedaba colgado en test_pruning) en vez de fallar y saltear.
# 127.0.0.1 y no `localhost`: este último prueba ::1 y después IPv4, y cada
# uno paga el timeout entero en cada uno de los ~34 tests que se saltean.
DB_LOCAL = "postgresql://smartuser:smartpassword@127.0.0.1:5432/smartcart?connect_timeout=1"

PASOS = [
    ("pytest", [sys.executable, "-m", "pytest", "-m", "not catalogo", "-q", "-x", "-p", "no:cacheprovider", "--disable-warnings"], RAIZ),
    ("npm run lint", "npm run lint", RAIZ / "frontend"),
    ("npm run build", "npm run build", RAIZ / "frontend"),
]


def main() -> int:
    sys.stderr.reconfigure(encoding="utf-8")  # Windows usa cp1252 y rompe los acentos
    try:
        evento = json.load(sys.stdin)
    except Exception:
        evento = {}

    # Ya estamos continuando por un bloqueo anterior: dejar parar evita un loop
    # infinito. El agente tuvo su intento; si sigue rojo, el fallo queda visible.
    if evento.get("stop_hook_active"):
        return 0

    cambios = subprocess.run(["git", "status", "--porcelain"], cwd=RAIZ, capture_output=True, text=True)
    if cambios.returncode == 0 and not cambios.stdout.strip():
        return 0  # nada cambió: una respuesta sin edits no paga la corrida

    entorno = {**os.environ, "DATABASE_URL": DB_LOCAL}
    for nombre, comando, cwd in PASOS:
        r = subprocess.run(
            comando, cwd=cwd, env=entorno, shell=isinstance(comando, str),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if r.returncode != 0:
            salida = (r.stdout + r.stderr).strip().splitlines()[-COLA:]
            print(f"El chequeo falló en `{nombre}` (exit {r.returncode}). "
                  "Arreglá el código (no el test) antes de terminar:\n", file=sys.stderr)
            print("\n".join(salida), file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
