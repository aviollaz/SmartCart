# src/search_intent.py
"""
Qué góndola (y qué tipo, de src/shelf_types.py) nombra el texto de una búsqueda.

La búsqueda semántica sola trae los 100 productos más parecidos a "vino tinto"
mezclando góndolas, cuando lo que el usuario quiere es la góndola de vinos con
el filtro Tinto: los 1.300, ordenables y filtrables. Esto lo detecta con una
tabla explícita y no con el embedding (la misma lección que src/shelves.py: un
umbral de similitud no separa "es esa góndola" de "se parece").

Tres resultados:
- `listing`: todas las palabras son de la góndola o de sus tipos ("vino tinto",
  "tinto vino", "vinos"): la góndola entera, con esos tipos como filtro.
- `within`: la búsqueda EMPIEZA por la góndola y sigue con otras palabras
  ("vino reserva"): búsqueda semántica dentro de la góndola.
- None: la primera palabra no es una góndola ("vinagre de vino", "coca cola"):
  la búsqueda de siempre. En castellano el sustantivo que manda va primero, y
  así "vinagre de vino" no termina en vinos.

Gana la frase más larga ("dulce de leche" antes que "leche"). Las palabras se
comparan sin acentos, en minúscula y en singular. Una palabra que dos góndolas
comparten ("queso", "pan") no va sola en la tabla: va la frase que las separa.
"""
from dataclasses import dataclass, field

from src.shelf_types import type_values
from src.text_utils import normalize_label

# Palabras que no cuentan como "otra palabra" para decidir listing vs within.
_STOPWORDS = {"de", "del", "la", "el", "los", "las", "y", "e", "con", "para", "en", "a", "al"}

# Frases que nombran cada góndola, en singular y sin acentos.
SHELF_WORDS: dict[str, tuple[str, ...]] = {
    "aceites-y-aderezos": ("aceite", "aderezo", "mayonesa", "ketchup", "mostaza", "vinagre", "aceto",
                           "salsa golf", "condimento", "especia"),
    "harinas": ("harina", "premezcla para pan"),
    "arroz-y-legumbres": ("arroz", "legumbre", "lenteja", "garbanzo", "poroto", "arveja seca"),
    "pastas-secas": ("fideo", "pasta seca", "spaghetti", "tallarin", "mostachol", "tirabuzon", "penne"),
    "salsas-de-tomate": ("salsa de tomate", "pure de tomate", "tomate triturado", "tomate perita en lata",
                         "pulpa de tomate", "extracto de tomate"),
    "conservas-de-pescado": ("atun", "caballa", "sardina", "conserva de pescado"),
    "snacks": ("snack", "papa frita", "mani", "chizito", "palito", "pochoclo", "nacho", "fruto seco"),
    "leches": ("leche",),
    "yogures": ("yogur", "yogurt"),
    "quesos-untables": ("queso crema", "queso untable", "ricota", "ricotta"),
    "quesos-blandos": ("queso cremoso", "queso blando", "mozzarella", "muzzarella", "queso port salut"),
    "quesos-duros": ("queso duro", "queso semiduro", "reggianito", "parmesano", "provoleta", "queso azul",
                     "pategras", "queso tybo"),
    "quesos-rallados": ("queso rallado",),
    "dulce-de-leche": ("dulce de leche",),
    "mermeladas-y-miel": ("mermelada", "miel", "dulce de membrillo", "dulce de batata"),
    "galletitas": ("galletita", "galleta", "cracker"),
    "alfajores": ("alfajor",),
    "chocolates": ("chocolate", "bombon"),
    "cafe": ("cafe",),
    "yerba-mate": ("yerba", "yerba mate"),
    "azucar-y-endulzantes": ("azucar", "endulzante", "edulcorante", "stevia"),
    "gaseosas": ("gaseosa",),
    "aguas": ("agua", "soda", "agua mineral", "agua saborizada"),
    "conservas-de-vegetales": ("conserva de vegetal", "choclo en lata", "arveja en lata", "durazno en almibar"),
    "encurtidos-y-aceitunas": ("aceituna", "encurtido", "pickle", "pepino en vinagre"),
    "caldos-y-sopas": ("caldo", "sopa", "sopa instantanea"),
    "reposteria": ("reposteria", "polvo de hornear", "levadura", "gelatina", "esencia de vainilla",
                   "premezcla", "bizcochuelo en polvo"),
    "golosinas": ("golosina", "caramelo", "chicle", "chupetin", "gomita", "turron", "pastilla"),
    "cereales": ("cereal", "granola", "muesli", "copo de maiz", "barra de cereal", "avena"),
    "te-e-infusiones": ("te", "infusion", "mate cocido", "manzanilla"),
    "cacao-y-chocolatadas": ("cacao", "chocolatada en polvo", "cacao en polvo"),
    "pan-lactal": ("pan lactal", "pan de mesa", "pan de molde"),
    "pan-hamburguesa": ("pan de hamburguesa", "pan de pancho", "pan para hamburguesa", "pan para pancho"),
    "budines-y-bizcochuelos": ("budin", "bizcochuelo", "pan dulce", "madalena", "magdalena"),
    "manteca-y-margarina": ("manteca", "margarina"),
    "cremas-de-leche": ("crema de leche",),
    "postres-y-flanes": ("postre", "flan"),
    "huevos": ("huevo",),
    "fiambres": ("fiambre", "jamon", "jamon cocido", "jamon crudo", "salame", "mortadela"),
    "salchichas": ("salchicha", "pancho"),
    "pastas-frescas": ("pasta fresca", "raviol", "ravioles", "noqui", "tapa de empanada", "tapa de tarta",
                       "capeletti", "sorrentino"),
    "jugos": ("jugo",),
    "energizantes-e-isotonicas": ("energizante", "bebida energizante", "isotonica", "bebida isotonica"),
    "cervezas": ("cerveza", "birra"),
    "vinos": ("vino",),
    "espumantes-y-sidras": ("espumante", "sidra", "champagne", "champan"),
    "aperitivos-y-licores": ("aperitivo", "licor", "fernet", "vermut", "vermouth", "whisky", "vodka", "gin"),
    "papas-congeladas": ("papa congelada", "papa prefrita"),
    "hamburguesas-congeladas": ("hamburguesa", "medallon", "milanesa congelada"),
    "rebozados-congelados": ("nugget", "rebozado", "patita de pollo"),
    "vegetales-congelados": ("vegetal congelado", "verdura congelada"),
    "comidas-congeladas": ("comida congelada", "pizza congelada", "empanada congelada"),
    "pescados-congelados": ("pescado", "pescado congelado", "merluza", "filet de merluza", "langostino"),
    "helados": ("helado",),
    "frutas": ("fruta",),
    "verduras": ("verdura",),
    "carnes": ("carne", "carne de vaca", "carne de cerdo", "carne vacuna"),
    "pollo": ("pollo",),
    "papel-higienico": ("papel higienico",),
    "rollos-y-servilletas": ("rollo de cocina", "servilleta", "papel de cocina"),
    "detergente": ("detergente",),
    "lavavajillas": ("lavavajilla", "detergente para lavavajilla", "pastilla para lavavajilla"),
    "limpiadores-de-cocina": ("desengrasante", "limpiador de cocina"),
    "limpiadores-de-bano": ("limpiador de bano",),
    "pastillas-inodoro": ("pastilla para inodoro", "bloque para inodoro", "pastilla de inodoro"),
    "limpiavidrios": ("limpiavidrio", "limpia vidrio"),
    "limpiadores-de-piso": ("limpiador de piso", "limpia piso"),
    "jabon-para-ropa": ("jabon para ropa", "jabon para la ropa", "jabon en polvo", "jabon liquido para ropa"),
    "suavizantes": ("suavizante",),
    "lavandina": ("lavandina", "cloro"),
    "shampoo": ("shampoo", "champu"),
    "acondicionadores": ("acondicionador", "crema de enjuague"),
    "coloracion": ("coloracion", "tintura"),
    "desodorantes": ("desodorante", "antitranspirante"),
    "jabones": ("jabon", "jabon de tocador", "jabon liquido"),
    "pasta-dental": ("pasta dental", "crema dental", "dentifrico"),
    "cepillos-de-dientes": ("cepillo de diente", "cepillo dental"),
    "enjuague-bucal": ("enjuague bucal",),
    "toallitas-femeninas": ("toallita femenina", "toallita"),
    "protectores-diarios": ("protector diario",),
    "tampones": ("tampon", "tampones"),
    "afeitado": ("afeitadora", "maquina de afeitar", "espuma de afeitar", "gel de afeitar"),
    "cremas-corporales": ("crema corporal", "crema de cuerpo"),
    "proteccion-solar": ("protector solar", "bronceador", "pantalla solar"),
    "algodon-e-hisopos": ("algodon", "hisopo"),
}


def _singular(word: str) -> str:
    """Singular aproximado: "tintos" -> "tinto", "tallarines" -> "tallarin", "dulces" -> "dulce"."""
    if len(word) > 4 and word.endswith("es") and word[-3] in "lrndzj":
        return word[:-2]
    if len(word) > 3 and word.endswith("s"):
        return word[:-1]
    return word


def _words(text: str) -> tuple[str, ...]:
    clean = "".join(c if c.isalnum() else " " for c in normalize_label(text))
    return tuple(_singular(w) for w in clean.split())


_SHELF_PHRASES = sorted(
    ((_words(phrase), shelf) for shelf, phrases in SHELF_WORDS.items() for phrase in phrases),
    key=lambda entry: -len(entry[0]),
)


@dataclass
class Intent:
    shelf: str
    mode: str  # "listing" | "within"
    types: list = field(default_factory=list)


def _read_types(shelf: str, words: tuple, at: int, length: int) -> tuple[list, list]:
    """
    Los tipos de la góndola en la búsqueda y las palabras que sobran.

    Los tipos se buscan en TODA la frase, la palabra de la góndola incluida
    ("aceite de oliva" es el tipo Aceite de oliva, "vinagre" es el tipo
    Vinagre), la frase más larga primero. Lo que no es tipo, ni la góndola (en
    `at`, de largo `length`), ni una palabra vacía, sobra.
    """
    used = [False] * len(words)
    found = []
    phrases = sorted(((_words(t), t) for t in type_values(shelf)), key=lambda e: -len(e[0]))
    for phrase, label in phrases:
        n = len(phrase)
        for i in range(len(words) - n + 1):
            if words[i:i + n] == phrase and not any(used[i:i + n]):
                used[i:i + n] = [True] * n
                found.append(label)
                break
    rest = [
        w for i, w in enumerate(words)
        if not used[i] and not at <= i < at + length and w not in _STOPWORDS
    ]
    return found, rest


def read_intent(q: str) -> Intent | None:
    """La góndola y los tipos que nombra la búsqueda, o None si no nombra ninguna."""
    words = _words(q)
    if not words:
        return None

    # La búsqueda empieza por la góndola: "vino", "vino tinto", "vino reserva".
    for phrase, shelf in _SHELF_PHRASES:
        if words[:len(phrase)] == phrase:
            types, rest = _read_types(shelf, words, 0, len(phrase))
            return Intent(shelf=shelf, mode="within" if rest else "listing", types=types)

    # La góndola en otro lugar ("tinto vino"): sólo si el resto son sus tipos.
    for phrase, shelf in _SHELF_PHRASES:
        n = len(phrase)
        at = next((i for i in range(1, len(words) - n + 1) if words[i:i + n] == phrase), -1)
        if at > 0:
            types, rest = _read_types(shelf, words, at, n)
            if types and not rest:
                return Intent(shelf=shelf, mode="listing", types=types)
    return None
