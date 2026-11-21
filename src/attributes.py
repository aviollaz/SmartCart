# src/attributes.py
"""
Atributos que un reemplazo tiene que compartir con el original, por góndola.

La góndola y el tamaño (src/substitutions.py) no alcanzan: `leches` junta la
sin lactosa con la chocolatada, y el embedding de nombres cortos se guía por
las palabras de formato ("Leche", "Larga Vida", "1 Lt"), así que la más
cercana a una "reducida en lactosa" era una chocolatada. Un umbral de distancia
no separa eso (el reemplazo malo de otro caso estaba más cerca que el bueno de
este), así que va una tabla explícita, como `meat_cuts.py`.

Cada atributo lee un valor del nombre: gana el primero de la tabla que aparece
al principio de una palabra, y si no aparece ninguno vale el valor común (una
leche que no habla de lactosa la tiene). Dos productos son intercambiables si
coinciden en todos los atributos de su góndola; un valor `None` ("no sé") no
coincide con nada: errar hacia "no lo tiene" sólo resigna un ahorro.

Una góndola sin fila acá no se filtra.
"""
import re

from src.meat_cuts import OTROS, product_type
from src.text_utils import normalize_label


def _attribute(default, values):
    """Un lector de nombre -> valor: `values` es ((valor, (palabras...)), ...) en orden de prioridad."""
    patterns = tuple(
        (value, re.compile(r"\b(?:" + "|".join(re.escape(k) for k in keys) + r")"))
        for value, keys in values
    )

    def read(name: str):
        text = normalize_label(name)
        return next((value for value, pattern in patterns if pattern.search(text)), default)

    return read


def _meat_cut(name: str):
    cut = product_type("carnes", name)
    return None if cut == OTROS else cut


SHELF_ATTRIBUTES = {
    "leches": (
        # La infantil va por marca: "Leche En Polvo 800gr 1 Nidina" no dice infantil.
        _attribute("comun", (
            ("infantil", ("infantil", "nidina", "nutrilon", "nutribaby", "sancor bebe")),
            ("vegetal", ("vegetal", "almendra", "avena", "soja", "coco")),
            ("chocolatada", ("chocolatada", "chocolate", "cindor")),
        )),
        _attribute("con lactosa", (
            ("sin lactosa", ("lactosa", "deslactosad")),
        )),
        _attribute("fluida", (
            ("polvo", ("polvo",)),
            ("condensada", ("condensada",)),
        )),
        # La que no declara la grasa es entera: así se erra hacia estricto.
        _attribute("entera", (
            ("parcialmente descremada", ("parcialmente descremada", "parcial descremada", "semi descremada",
                                         "semidescremada", "semi-descremada")),
            ("descremada", ("descremada",)),
        )),
    ),
    "carnes": (_meat_cut,),
}


def attributes_match(shelf: str | None, original_name: str, candidate_name: str) -> bool:
    """¿Coinciden en todos los atributos de la góndola? Sin tabla, siempre."""
    for read in SHELF_ATTRIBUTES.get(shelf, ()):
        value = read(original_name)
        if value is None or value != read(candidate_name):
            return False
    return True
