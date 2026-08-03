import re

# Sufijos de magnitud, ordenados de más largo a más corto dentro de cada familia.
# El orden importa: con "gr" antes que "grs", "400 grs" hace que el motor matchee
# "gr", falle el \b contra la "s" y tenga que backtrackear. Funciona igual, pero
# leerlo de largo a corto es lo que hace evidente que "grs" está contemplado.
#
# La lista salió de relevar los 839 nombres del catálogo: "grs" aparece 64 veces
# y "lts" 4, y las dos caían al genérico (1.0, 'un').
_UNIT_SUFFIXES = r"kg|grs|grm|gr|g|lts|ltr|lt|ml|l|cc"

_SIZE_RE = re.compile(
    rf"(\d+(?:[,.]\d+)?)\s*({_UNIT_SUFFIXES})\b",
    re.IGNORECASE,
)

# Multiplicador de pack: "x6", "6x", "x 6 uni", "6 u.", "6 unidades".
#
# El lookahead negativo es imprescindible: sin él, "bolsa x 800 grs" devuelve un
# pack de 800 y "Harina Caserita x 1 kg" uno de 1. Un número seguido de una
# unidad de magnitud es un tamaño, no una cantidad de unidades.
_PACK_RES = [
    re.compile(rf"\bx\s*(\d+)\b(?!\s*(?:{_UNIT_SUFFIXES})\b)", re.IGNORECASE),
    re.compile(r"\b(\d+)\s*x\b", re.IGNORECASE),
    re.compile(r"\b(\d+)\s*(?:u|un|uni|unid|unids|unidad|unidades)\b", re.IGNORECASE),
]


def extract_real_volume(name: str) -> tuple[float, str]:
    """
    Parsea el nombre del producto para extraer el volumen/peso real usando Regex.
    Normaliza todo a gramos (g) o mililitros (ml) para poder comparar magnitudes.

    Devuelve el tamaño TAL COMO FIGURA en el nombre, sin multiplicarlo por la
    cantidad de un pack — ver `extract_pack_count()` para por qué eso no se puede
    hacer de forma confiable.
    """
    if not name:
        return 1.0, 'un'

    # "lt" está contemplado porque es como Carrefour escribe los litros
    # ("Aceite ... 1.5 lt."): sin esa variante el nombre no matchea y el producto
    # cae al genérico (1.0, 'un'), que rompe la comparación por magnitud y las
    # sugerencias de reemplazo "a igual peso".
    match = _SIZE_RE.search(name)
    if not match:
        return 1.0, 'un'

    try:
        val = float(match.group(1).replace(',', '.'))
    except ValueError:
        return 1.0, 'un'

    # La conversión se delega en vez de repetirse: tener acá una segunda tabla de
    # unidades en paralelo a la de normalize_magnitude es exactamente la
    # divergencia que dejó filas guardadas en 'kg' y en 'gr'. Agregar un sufijo
    # ahora es tocar _UNIT_SUFFIXES y los sets de abajo, no tres lugares.
    return normalize_magnitude(val, match.group(2))


_TO_GRAMS = {"kg", "kgs", "kilo", "kilos", "kilogramo", "kilogramos"}
_GRAMS = {"g", "gr", "grs", "grm", "gramo", "gramos"}
_TO_ML = {"l", "lt", "lts", "ltr", "litro", "litros"}
_ML = {"ml", "cc"}


def normalize_magnitude(value: float, unit: str) -> tuple[float, str]:
    """
    Expresa un (valor, unidad) cualquiera en el vocabulario canónico: 'g', 'ml'
    o 'un'. No cambia el tamaño físico, sólo cómo se escribe.

    Existe porque los tres scrapers tienen un fallback que estima el tamaño
    dividiendo el precio por el precio por unidad, y ahí la unidad sale de la
    tienda: Coto emitía 'kg' sin convertir, y Día y Carrefour dejaban pasar el
    string crudo de la property "UnidaddeMedida" de VTEX cuando no era ni litros
    ni kilos, con lo que un producto podía terminar guardado como 'gr' o 'un'.

    El daño de eso es silencioso, no ruidoso: nada compara unidades distintas
    (ni la heurística de swaps ni las sugerencias de api.py), así que una fila en
    'kg' o en 'gr' no da un error de 1000x — simplemente deja de ser comparable
    con nadie y desaparece de las dos features sin que se note.

    Una unidad desconocida devuelve (1.0, 'un'), el mismo "no sé el tamaño" que
    usa extract_real_volume(): inventar una equivalencia sería peor que admitir
    que no se sabe.
    """
    u = (unit or "").strip().lower().rstrip(".")

    if u in _TO_GRAMS:
        return value * 1000.0, "g"
    if u in _GRAMS:
        return value, "g"
    if u in _TO_ML:
        return value * 1000.0, "ml"
    if u in _ML:
        return value, "ml"

    return 1.0, "un"


def extract_pack_count(name: str) -> int:
    """
    Cantidad de unidades del pack, o 1 si el nombre no declara ninguna.

    Sirve para NO comparar un pack de 6 contra una unidad suelta. Deliberadamente
    NO se usa para multiplicar el peso, aunque sea lo primero que uno querría
    hacer: relevando los nombres reales, el tamaño que figura al lado del "xN" es
    a veces el total del pack y a veces el de cada unidad, sin ninguna marca que
    los distinga.

        "Alfajor Blanco Con Dulce De Leche X6 ALFA PAMPA 360g"  -> 360 g es el TOTAL
        "Alfajor de chocolate negro Entre Dos x6 45 g."         -> 45 g es CADA UNO
        "Alfajor Block cofler x6 244 grs"                       -> total
        "Alfajor de arroz Chocoarroz ... x6 36 grs"             -> cada uno

    Multiplicar siempre inflaría el peso justo en los casos donde ya venía el
    total, y un peso inflado abarata el precio por gramo: el producto pasaría a
    parecer una ganga y la app lo recomendaría. Es exactamente la dirección de
    error que el proyecto evita en el resto del pipeline (ver los flags dietarios
    en CLAUDE.md): errar hacia caro sólo pierde un ahorro, errar hacia barato
    rompe la promesa. Así que el tamaño queda como viene y el pack sólo se usa
    para exigir que dos productos sean del mismo formato.
    """
    if not name:
        return 1

    for pattern in _PACK_RES:
        match = pattern.search(name)
        if match:
            try:
                count = int(match.group(1))
            except ValueError:
                continue
            # Un "x0" no existe y un pack de 200 alfajores tampoco: si el número
            # es absurdo, casi seguro se matcheó otra cosa (un código, un año).
            if 1 <= count <= 100:
                return count

    return 1
