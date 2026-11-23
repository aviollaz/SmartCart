"""
La división tiene que terminar en una máquina de un núcleo, que es Cloud Run.

CP-SAT usa por defecto un worker por núcleo que ve. Con uno solo, este carrito
real (23 lácteos, las promos bancarias del lunes 23-nov-2026) no terminaba
nunca: la instancia quedaba al 99% de CPU, la memoria crecía hasta matar el
contenedor y `/compare` moría a los 300 s, arrastrando al catálogo de esa
instancia. Con varios workers el mismo modelo se resuelve en décimas.

Atar el proceso a un núcleo no alcanza para simularlo (CP-SAT sigue viendo los
de la máquina), así que el subproceso hace lo que hace un núcleo solo: si nadie
fijó `num_workers`, CP-SAT corre con uno.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).parent.parent
FIXTURE = RAIZ / "tests" / "fixtures" / "carrito_que_colgaba_cloud_run.json"

RESOLVER_CON_UN_NUCLEO = f"""
import json
from ortools.sat.python import cp_model

original = cp_model.CpSolver.solve
def con_un_nucleo(self, *args, **kwargs):
    if self.parameters.num_workers == 0:
        self.parameters.num_workers = 1
    return original(self, *args, **kwargs)
cp_model.CpSolver.solve = cp_model.CpSolver.Solve = con_un_nucleo

from src.optimizer import DEFAULT_MIN_SPEND_LIMITS, optimize_cart
datos = json.load(open({str(FIXTURE)!r}, encoding="utf-8"))
r = optimize_cart(
    cart_items=datos["cart"], user_memberships=datos["user_memberships"],
    user_cards=datos["user_cards"], min_spend_limits=DEFAULT_MIN_SPEND_LIMITS,
    delivery_costs={{s: 4000 for s in DEFAULT_MIN_SPEND_LIMITS}},
    flat_prices=datos["flat_prices"], bank_promos=datos["bank_promos"],
)
print(r["total_spent_net"])
"""


def test_la_division_termina_y_da_el_optimo_con_un_solo_nucleo():
    # preparar
    entorno = {**os.environ, "PYTHONPATH": str(RAIZ)}

    # ejecutar
    try:
        salida = subprocess.run(
            [sys.executable, "-c", RESOLVER_CON_UN_NUCLEO], env=entorno, cwd=RAIZ,
            capture_output=True, text=True, timeout=30, check=True,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("la división no terminó en 30 s con un núcleo")

    # verificar
    assert float(salida.stdout.strip()) == 376601.1
