# src/dietary_parser.py
"""
Detección de atributos dietarios (sin TACC / vegano) desde el texto que los
scrapers ya tienen a mano.

Criterio deliberado: un flag se pone en True SOLO con evidencia textual
explícita. `False` significa "sin evidencia", NO "contiene gluten" ni "no es
vegano" — un falso positivo acá tiene consecuencias reales para alguien
celíaco, así que se prefiere no marcar antes que marcar de más.

Por eso tampoco se infiere nada a partir de la categoría (del estilo "todo lo
que cuelga de frutas es vegano") y se buscan frases completas en vez de tokens
sueltos: el token "gluten" solo daría positivo en "contiene gluten", y
"vegetal" daría positivo en productos como "Sémola Vegetales Vitina Luchetti".

IMPORTANTE para quien llame a esta función: pasarle SOLO texto que describa al
producto en cuestión —su nombre, su marca, su categoría, y los campos
estructurados que la tienda le asigna—. Las descripciones de marketing NO
sirven, porque enumeran productos hermanos de la misma línea: la descripción
del "Ketchup Hellmann's Regular" incluye "...mayonesa hellmann's light,
clásica, suave, vegana, oliva..." y hacía que el ketchup se marcara vegano.
Ninguna regla de frases evita eso, porque el reclamo es legítimo pero es sobre
otro producto; la única defensa es no mirar ese texto.
"""
import re

from src.text_utils import normalize_label

# Frases que invalidan cualquier evidencia encontrada en el mismo texto.
_NEGATIONS = [
    r"\bno apto\b",
    r"\bno es apto\b",
    r"\bcontiene gluten\b",
    r"\bcontiene tacc\b",
    r"\bcontiene trazas\b",
]

_GLUTEN_FREE = [
    r"\bsin tacc\b",
    r"\bsin t\.a\.c\.c\.?",
    r"\blibre de gluten\b",
    r"\bsin gluten\b",
    r"\bgluten free\b",
]

# "vegetal" suelto queda fuera a propósito (ver docstring del módulo).
_VEGAN = [
    r"\bvegan[oa]s?\b",
    r"\bplant[\s-]based\b",
    r"\b100\s*%\s*vegetal\b",
]


def _flatten(values) -> list[str]:
    """Aplana los textos de entrada, que pueden venir sueltos o como listas
    (ej. los `values` de una property de VTEX)."""
    out = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            out.append(value)
        elif isinstance(value, dict):
            # ej. clusterHighlights de VTEX: {id: "Sin TACC"}
            out.extend(_flatten(value.values()))
        elif isinstance(value, (list, tuple, set)):
            out.extend(_flatten(value))
        else:
            out.append(str(value))
    return out


def detect_dietary_flags(*texts) -> tuple[bool, bool]:
    """
    Busca evidencia dietaria en los textos recibidos (nombre, marca, ruta de
    categoría, properties de VTEX, descripción si la hubiera).

    Retorna una tupla (is_gluten_free, is_vegan).
    """
    joined = " ".join(_flatten(texts))
    if not joined.strip():
        return False, False

    normalized = normalize_label(joined)
    # Variante sin puntos para que "Sin T.A.C.C." matchee el patrón "sin tacc".
    dotless = normalized.replace(".", "")
    haystacks = (normalized, dotless)

    def matches(patterns) -> bool:
        return any(re.search(p, h) for p in patterns for h in haystacks)

    if matches(_NEGATIONS):
        return False, False

    return matches(_GLUTEN_FREE), matches(_VEGAN)
