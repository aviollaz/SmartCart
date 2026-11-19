# src/meat_cuts.py
"""
El tipo de corte de un producto de la góndola de carnes, leído de su nombre.
Alimenta el filtro "Tipo de corte" de /category (como el de Carrefour).

No sale de las cadenas: ninguna separa por corte (Coto tiene una sola hoja para
vaca y cerdo, el resto separa vaca de cerdo y nada más). Los nombres, en
cambio, son muy regulares ("Asado x kg", "Vacío Envasado al Vacío"), así que
alcanza una tabla explícita, como `fresh_items.py`.

**El orden de la tabla es la prioridad**: gana el primer corte que aparece en
el nombre. Por eso lo específico va antes que lo general ("tapa de asado" antes
que "asado", "bife de chorizo" antes que "bife") y lo elaborado antes que el
corte del que sale ("Milanesa de nalga" es milanesa; "Carne picada de nalga",
picada). Lo que no matchea es "Otros": nunca desaparece del listado.

Las palabras se buscan al principio de una palabra del nombre normalizado (sin
acentos ni mayúsculas), así "costilla" toma "costillitas" y "riñon" no toma
"sarriñon".
"""
import re

from src.text_utils import normalize_label

OTROS = "Otros"

CUTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Carne picada", ("picada",)),
    ("Milanesa", ("milanesa",)),
    ("Hamburguesa", ("hamburguesa",)),
    ("Albóndigas", ("albondiga",)),
    ("Tapa de asado", ("tapa de asado",)),
    ("Tapa de nalga", ("tapa de nalga",)),
    ("Colita de cuadril", ("colita de cuadril",)),
    ("Bife de chorizo", ("bife de chorizo",)),
    ("Bife ancho", ("bife ancho", "ojo de bife")),
    ("Bife angosto", ("bife angosto",)),
    ("Bife americano", ("bife americano",)),
    ("Bola de lomo", ("bola de lomo",)),
    ("Roast beef", ("roast beef",)),
    ("Chorizo y morcilla", ("chorizo", "morcilla")),
    ("Achuras", ("chinchulin", "molleja", "rinon", "higado", "mondongo", "lengua", "corazon")),
    ("Asado", ("asado", "costill")),
    ("Vacío", ("vacio",)),
    ("Matambre", ("matambre",)),
    ("Entraña", ("entrana",)),
    ("Falda", ("falda",)),
    ("Cuadril", ("cuadril",)),
    ("Nalga", ("nalga",)),
    ("Peceto", ("peceto",)),
    ("Lomo", ("lomo",)),
    ("Solomillo", ("solomillo",)),
    ("Cuadrada", ("cuadrada",)),
    ("Paleta", ("paleta",)),
    ("Osobuco", ("osobuco",)),
    ("Palomita", ("palomita",)),
    ("Tortuga", ("tortug",)),
    ("Carnaza", ("carnaza",)),
    ("Picaña", ("picana", "picanha")),
    ("Tomahawk", ("tomahawk",)),
    ("Azotillo", ("azotillo",)),
    ("Aguja", ("aguja",)),
    ("Marucha", ("marucha",)),
    # Siempre de cerdo: la etiqueta ya lo dice, así no se parten en dos según
    # el nombre lo aclare o no.
    ("Bondiola de cerdo", ("bondiola",)),
    ("Carré de cerdo", ("carre",)),
    ("Pechito de cerdo", ("pechito",)),
    ("Ribs de cerdo", ("ribs",)),
    ("Panceta de cerdo", ("panceta",)),
    ("Jamón de cerdo", ("jamon",)),
    ("Costeletas", ("costeleta", "chuleta")),
    ("Churrasco", ("churras",)),
    ("Bife", ("bife",)),
)

# Las góndolas con tipo. Pollo podría ser la próxima fila.
_TYPED_SHELVES = {"carnes"}

_PATTERNS = tuple(
    (label, re.compile(r"\b(?:" + "|".join(re.escape(k) for k in keys) + r")"))
    for label, keys in CUTS
)


def product_type(shelf: str | None, name: str) -> str | None:
    """El corte del producto, "Otros" si no se reconoce, o None fuera de las góndolas con tipo."""
    if shelf not in _TYPED_SHELVES:
        return None
    # "Envasado al vacío" es el empaque, no el corte: sin sacarlo, todo lomo
    # envasado sería vacío.
    texto = normalize_label(name).replace("al vacio", "")
    for label, pattern in _PATTERNS:
        if pattern.search(texto):
            return f"{label} de cerdo" if "cerdo" in texto and "cerdo" not in label else label
    return OTROS
