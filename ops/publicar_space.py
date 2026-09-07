"""
Publica la API en un Space de Hugging Face.

Uso:
    # una sola vez, cloná el Space que creaste en la web:
    git clone https://huggingface.co/spaces/TU-USUARIO/smartcart ../smartcart-space

    # cada vez que quieras actualizar la API publicada:
    python ops/publicar_space.py ../smartcart-space
    python ops/publicar_space.py ../smartcart-space --dry-run

El Space vive en SU PROPIO repositorio, aparte de éste, y este script copia lo
que la API necesita. Es a propósito y no una complicación evitable:

* **Spaces lee su configuración del frontmatter YAML del `README.md`**, en la
  raíz del repo. El `README.md` de SmartCart no lo tiene y no debería tenerlo
  —GitHub lo dibuja como una tabla arriba de todo, en el archivo que es la carta
  de presentación del proyecto—, así que empujar este repo al Space le borra la
  configuración. Este script escribe el README del Space, que es el único lugar
  donde ese frontmatter tiene sentido.
* Lo que la API necesita es `Dockerfile`, `requirements.txt` y `src/`. El
  frontend, los tests, `docs/` y `ops/` no pintan nada en la imagen (ya están
  excluidos en `.dockerignore`) y menos todavía en un repo público de HF.

El frontend NO se publica por acá: va en Vercel y se despliega solo con cada
push a GitHub. Ver `ops/demo-publica.md`.
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# Lo único que entra en la imagen. Espeja el .dockerignore: si se agrega un
# archivo que la API lee en runtime, va acá Y allá.
A_COPIAR = ("Dockerfile", "requirements.txt", "src")

# Spaces lee esto y nada más: sin el bloque, el Space no sabe que es Docker.
# `app_port` coincide con el EXPOSE/CMD del Dockerfile.
README_DEL_SPACE = """---
title: SmartCart
emoji: 🛒
colorFrom: purple
colorTo: red
sdk: docker
app_port: 7860
pinned: false
short_description: API del optimizador de canasta para supermercados argentinos
---

# SmartCart — API

Backend del optimizador de canasta de compra para supermercados argentinos
(Coto, Día y Carrefour). El código vive en
<https://github.com/aviollaz/SmartCart>; este Space es sólo el despliegue de la
API, y se actualiza con `python ops/publicar_space.py` desde ese repo.

La interfaz está en Vercel y le pega a este Space. La documentación de la API
está en `/docs`.
"""


def correr(comando, cwd, dry_run):
    if dry_run:
        print(f"   [dry-run] {' '.join(comando)}")
        return ""
    resultado = subprocess.run(comando, cwd=cwd, capture_output=True, text=True)
    if resultado.returncode != 0:
        print(f"ERROR: {' '.join(comando)}\n{resultado.stderr}", file=sys.stderr)
        raise SystemExit(1)
    return resultado.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("space_dir", help="Ruta al clon local del Space.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Muestra qué copiaría y no toca nada.")
    parser.add_argument("--mensaje", default="Actualizar API desde SmartCart",
                        help="Mensaje del commit en el Space.")
    args = parser.parse_args()

    destino = Path(args.space_dir).resolve()
    if not (destino / ".git").is_dir():
        print(f"ERROR: {destino} no es un repositorio git.\n"
              f"Cloná primero el Space:\n"
              f"  git clone https://huggingface.co/spaces/TU-USUARIO/smartcart {destino}",
              file=sys.stderr)
        return 1

    print(f"origen : {RAIZ}\ndestino: {destino}\n")

    for nombre in A_COPIAR:
        origen = RAIZ / nombre
        if not origen.exists():
            print(f"ERROR: falta {origen}", file=sys.stderr)
            return 1

        objetivo = destino / nombre
        if args.dry_run:
            print(f"   [dry-run] copiar {nombre}")
            continue

        if origen.is_dir():
            # Se borra primero para que un archivo eliminado acá desaparezca
            # allá: un copytree sobre lo viejo deja huérfanos que la imagen
            # seguiría incluyendo.
            shutil.rmtree(objetivo, ignore_errors=True)
            shutil.copytree(
                origen, objetivo,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
            )
        else:
            shutil.copy2(origen, objetivo)
        print(f"   copiado {nombre}")

    if not args.dry_run:
        (destino / "README.md").write_text(README_DEL_SPACE, encoding="utf-8")
        print("   escrito README.md (con el frontmatter que Spaces necesita)")

    print("\nCommit y push al Space:")
    correr(["git", "add", "-A"], destino, args.dry_run)

    if not args.dry_run:
        pendiente = correr(["git", "status", "--porcelain"], destino, False)
        if not pendiente:
            print("   nada cambió; el Space ya está al día.")
            return 0

    correr(["git", "commit", "-m", args.mensaje], destino, args.dry_run)
    correr(["git", "push"], destino, args.dry_run)

    if not args.dry_run:
        print("\nListo. El build tarda ~10 min la primera vez (baja torch).")
        print("Mirá el progreso en la pestaña 'Logs' del Space.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
