# src/attributes.py
"""
Atributos que un reemplazo tiene que compartir con el original, por góndola.

La góndola y el tamaño (src/substitutions.py) no alcanzan: `leches` junta la
sin lactosa con la chocolatada, `arroz-y-legumbres` los garbanzos con las
lentejas, y el embedding de nombres cortos se guía por las palabras de formato
("Leche", "Larga Vida", "500 g"), así que el vecino más cercano muchas veces es
otro producto. Un umbral de distancia no separa eso (un reemplazo malo estaba
más cerca que uno bueno de otro caso), así que va una tabla explícita, como
`meat_cuts.py`. Las tablas salen de `python -m src.scripts.medir_reemplazos`.

Cada atributo lee un valor del nombre normalizado: gana el primero de la tabla
cuya palabra aparece al principio de una palabra del nombre. Si no aparece
ninguna, vale el default del atributo:
- un valor común ("con lactosa", "sin gas"), cuando el nombre calla lo normal;
- `None` ("no sé qué es"), que no coincide con nada: un "tipo" no reconocido
  queda sin reemplazo. Errar hacia "no lo tiene" sólo resigna un ahorro.

Dos productos son intercambiables si coinciden en todos los atributos de su
góndola. El sabor queda libre a propósito (decisión de producto): una Powerade
de naranja puede reemplazar a una de manzana. Una góndola sin fila no se filtra.

Sin TACC y vegano no están acá: salen de las columnas de la base
(`dietary_match`), no del nombre.
"""
import re

from src.meat_cuts import OTROS, product_type
from src.text_utils import normalize_label


def _attribute(default, values):
    """Un lector nombre -> valor: `values` es ((valor, (palabras...)), ...) en orden de prioridad."""
    patterns = tuple(
        (value, re.compile(r"\b(?:" + "|".join(re.escape(k) for k in keys) + r")"))
        for value, keys in values
    )

    def read(name: str):
        text = normalize_label(name)
        return next((value for value, pattern in patterns if pattern.search(text)), default)

    return read


def _tipo(*values):
    """El tipo de producto de una góndola mixta: lo no reconocido no tiene reemplazo."""
    return _attribute(None, values)


def _meat_cut(name: str):
    cut = product_type("carnes", name)
    return None if cut == OTROS else cut


def _never(name: str):
    return None


# --------------------------------------------------------------------------
# Atributos que cruzan góndolas
# --------------------------------------------------------------------------

SIN_AZUCAR = _attribute("con azucar", (
    ("sin azucar", ("zero", "sin azucar", "light", "diet", "libre de azucar", "bajas calorias", "bc")),
))
GAS = _attribute("sin gas", (
    ("sin gas", ("sin gas",)),
    ("con gas", ("con gas", "gasificada", "soda")),
))
INFANTIL = _attribute("adulto", (
    ("infantil", ("infantil", "nino", "kids", "kid", "bebe", "baby", "junior")),
))
# "men" sólo como palabra entera con su marca: como prefijo tomaría "menta".
GENERO = _attribute("unisex", (
    ("masculino", ("masculin", "hombre", "for men", "men care", "nivea men", "dove men",
                   "rexona men", "axe", "patrichs", "old spice")),
    ("femenino", ("femenin", "women", "mujer", "lady")),
))
SIN_LACTOSA = _attribute("con lactosa", (("sin lactosa", ("lactosa", "deslactosad")),))
LIGHT = _attribute("comun", (("light", ("light", "descremad", "magro", "reducido en grasa")),))
SIN_SAL = _attribute("comun", (
    ("sin sal", ("sin sal",)),
    ("con sal", ("con sal", "extra sal", "salada")),
))
REPUESTO = _attribute("completo", (("repuesto", ("repuesto", "recarga", "refill")),))
CONCENTRADO = _attribute("comun", (("concentrado", ("concentrad", "concent")),))


SHELF_ATTRIBUTES = {
    # ---------------- Frescos
    "leches": (
        # La infantil va por marca: "Leche En Polvo 800gr 1 Nidina" no dice infantil.
        _attribute("comun", (
            ("infantil", ("infantil", "nidina", "nutrilon", "nutribaby", "sancor bebe")),
            ("vegetal", ("vegetal", "almendra", "avena", "soja", "coco")),
            ("chocolatada", ("chocolatada", "chocolate", "cindor")),
        )),
        SIN_LACTOSA,
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
    "yogures": (
        _attribute("firme", (("bebible", ("bebible",)),)),
        _attribute("comun", (("griego", ("griego",)),)),
        _attribute("entero", (("descremado", ("descremad", "zero", "light", "0%")),)),
        _attribute("solo", (("con cereales", ("cereal", "colchon", "granola", "topping")),)),
    ),
    "quesos-untables": (
        _tipo(
            ("hummus", ("hummus",)),
            ("ricota", ("ricota", "ricotta")),
            ("mascarpone", ("mascarpone",)),
            ("queso crema", ("queso crema", "crema original", "quescrem", "philadelphia")),
            ("untable", ("untable", "cremon", "fundido", "finlandia", "casancrem", "mendicrim")),
            ("brie", ("brie", "camembert", "briette")),
        ),
        LIGHT,
        SIN_LACTOSA,
    ),
    "quesos-blandos": (
        _tipo(
            ("mozzarella", ("mozzarella", "muzzarella", "muzarella", "mozarella")),
            ("port salut", ("port salut", "por salut")),
            ("cremoso", ("cremoso", "doble crema")),
            ("cuartirolo", ("cuartirolo",)),
            ("danbo", ("danbo",)),
            ("criollo", ("criollo",)),
            ("feta", ("feta ",)),
            ("brie", ("brie", "camembert")),
        ),
        LIGHT,
        SIN_SAL,
        SIN_LACTOSA,
    ),
    "quesos-duros": (
        _tipo(
            ("azul", ("azul", "roquefort", "gorgonzola")),
            ("reggianito", ("reggianito",)),
            ("parmesano", ("parmesano", "grana padano")),
            ("sardo", ("sardo",)),
            ("pategras", ("pategras",)),
            ("gouda", ("gouda",)),
            ("holanda", ("holanda", "edam")),
            ("provolone", ("provolet", "provolone")),
            ("danbo", ("danbo",)),
            ("fontina", ("fontina",)),
            ("tybo", ("tybo",)),
            ("gruyere", ("gruyere", "emmental", "maasdam")),
            ("fynbo", ("fynbo", "fymbo", "minifynbo")),
            ("mozzarella", ("mozzarella", "muzzarella")),
            ("cheddar", ("cheddar",)),
            ("goya", ("goya",)),
            ("mar del plata", ("mar del plata",)),
        ),
        LIGHT,
        SIN_LACTOSA,
    ),
    # El reggianito es el rallado por default: casi todos lo son sin decirlo.
    "quesos-rallados": (
        _attribute("rallado", (
            ("alimento a base de queso", ("alimento", "procesado", "deshidratado", "parmiginas")),
            ("parmesano", ("parmesano",)),
            ("sardo", ("sardo",)),
            ("hebras", ("hebra",)),
        )),
    ),
    "manteca-y-margarina": (
        _tipo(
            ("ghee", ("ghee", "clarificada")),
            ("levadura", ("levadura",)),
            ("margarina", ("margarina",)),
            ("manteca", ("manteca",)),
        ),
        SIN_SAL,
    ),
    "cremas-de-leche": (
        _attribute("comun", (
            ("liviana", ("liviana", "light")),
            ("para cocinar", ("cocinar",)),
            ("chantilly", ("chantilly",)),
            ("vegetal", ("vegetal",)),
        )),
    ),
    "postres-y-flanes": (
        _tipo(
            ("compota de fruta", ("fruit", "compota")),
            ("flan", ("flan",)),
            ("mousse", ("mousse",)),
            ("arroz con leche", ("arroz con leche",)),
            ("panna cotta", ("panna cotta",)),
            ("gelatina", ("gelatina",)),
            ("postre", ("postre", "serenito", "danette", "shimy")),
        ),
        SIN_AZUCAR,
    ),
    "huevos": (_attribute("blanco", (("color", ("color",)),)),),
    "fiambres": (
        _tipo(
            ("queso de cerdo", ("queso de cerdo",)),
            ("jamon crudo", ("crudo", "serrano", "prosciutto")),
            ("jamon cocido", ("cocido",)),
            ("salame", ("salame", "salamin", "milan", "fuet")),
            ("mortadela", ("mortadela",)),
            ("bondiola", ("bondiola",)),
            ("panceta", ("panceta",)),
            ("paleta", ("paleta",)),
            ("pavo", ("pavo",)),
            ("lomito", ("lomito", "lomo")),
            ("pastron", ("pastron",)),
            ("matambre", ("matambre",)),
        ),
    ),
    "salchichas": (
        _attribute("salchicha", (
            ("leberwurst", ("leberwurst",)),
            ("morcilla", ("morcilla",)),
            ("chorizo", ("chorizo",)),
            ("alemana", ("aleman", "frankfurt")),
        )),
    ),
    "pastas-frescas": (
        _tipo(
            ("tapa de empanada", ("empanada",)),
            ("tapa de pascualina", ("pascualina", "tarta")),
            ("tortilla", ("tortilla", "rapidita", "wrap")),
            ("masa de pizza", ("pizza",)),
            ("sorrentinos", ("sorrentino",)),
            ("ravioles", ("raviol",)),
            ("capeletinis", ("capelet",)),
            ("agnolotis", ("agnolot",)),
            ("canelones", ("canelon",)),
            ("lasagna", ("lasagna", "lasana")),
            ("noquis", ("noqui", "gnocchi")),
            ("fideos", ("fideo", "tallarin", "cinta", "spaghetti", "mostachol", "fetuccine", "fettuccine")),
        ),
    ),
    # ---------------- Almacén
    "aceites-y-aderezos": (
        _tipo(
            ("aceite de oliva", ("oliva",)),
            ("aceite de girasol", ("girasol",)),
            ("aceite de maiz", ("aceite de maiz",)),
            ("aceite de canola", ("canola",)),
            ("aceite mezcla", ("mezcla",)),
            ("aceite en aerosol", ("aerosol", "rocio")),
            ("aceto balsamico", ("balsamico", "aceto")),
            ("vinagre", ("vinagre",)),
            ("jugo de limon", ("jugo de limon",)),
            ("mayonesa", ("mayonesa",)),
            ("ketchup", ("ketchup",)),
            ("mostaza", ("mostaza",)),
            ("salsa golf", ("golf",)),
            ("barbacoa", ("barbacoa", "bbq")),
            ("chimichurri", ("chimichurri",)),
            ("salsa de soja", ("soja", "soya")),
            ("cheddar", ("cheddar",)),
            ("aderezo", ("aderezo", "cesar")),
            ("condimento", ("condimento", "oregano", "pimienta", "comino", "pimenton", "aji molido",
                            "nuez moscada", "provenzal", "adobo", "laurel", "curry", "canela", "ajo")),
            ("sal", ("sal ", "sal fina", "sal gruesa", "sal marina", "sal entrefina")),
            ("aceite", ("aceite",)),
        ),
    ),
    "harinas": (
        _tipo(
            ("premezcla", ("premezcla",)),
            ("almidon", ("almidon", "maicena", "fecula")),
            ("arepa", ("arepa",)),
            ("polenta", ("polenta",)),
            ("semola", ("semola",)),
            ("rebozador", ("rebozador", "pan rallado")),
            ("levadura", ("levadura",)),
            ("harina de arroz", ("de arroz",)),
            ("harina de almendras", ("almendra",)),
            ("harina de garbanzo", ("garbanzo",)),
            ("harina de avena", ("avena",)),
            ("harina de sarraceno", ("sarraceno",)),
            ("harina de mandioca", ("mandioca",)),
            ("harina de maiz", ("de maiz",)),
            ("harina leudante", ("leudante",)),
            ("harina integral", ("integral",)),
            ("harina 0000", ("0000",)),
            ("harina 000", ("000",)),
            ("harina 00", ("00",)),
            ("harina", ("harina",)),
        ),
    ),
    "arroz-y-legumbres": (
        _tipo(
            ("porotos alubia", ("alubia",)),
            ("porotos pallares", ("pallar",)),
            ("porotos negros", ("porotos negros", "poroto negro")),
            ("porotos colorados", ("colorado",)),
            ("porotos mung", ("mung",)),
            ("porotos", ("poroto",)),
            ("lentejas", ("lenteja",)),
            ("garbanzos", ("garbanzo",)),
            ("arvejas", ("arveja",)),
            ("soja", ("soja",)),
            ("maiz pisingallo", ("pisingallo", "pochoclo")),
            ("quinoa", ("quinoa", "quinua")),
            ("chia", ("chia",)),
            ("lino", ("lino",)),
            ("sesamo", ("sesamo",)),
            ("semillas de girasol", ("girasol",)),
            ("semillas", ("semilla",)),
            ("mijo", ("mijo",)),
            ("trigo burgol", ("burgol", "trigo")),
            ("cebada", ("cebada",)),
            ("arroz integral", ("arroz integral", "integral")),
            ("arroz yamani", ("yamani",)),
            ("arroz parboil", ("parboil",)),
            ("arroz para risotto", ("carnaroli", "arborio", "risotto")),
            ("arroz basmati", ("basmati",)),
            ("arroz jazmin", ("jazmin",)),
            ("arroz doble carolina", ("carolina",)),
            ("arroz largo fino", ("largo fino",)),
            ("arroz", ("arroz",)),
        ),
    ),
    "pastas-secas": (
        _tipo(
            ("noquis", ("noqui", "gnocchi")),
            ("lasagna", ("lasagna", "lasana")),
            ("canelones", ("canelon",)),
            ("pasta instantanea", ("box", "instantane", "listo")),
            ("fideos para sopa", ("municion", "dedalito", "letra", "ave maria", "pastina", "sopa", "cabello de angel")),
            ("fideos largos", ("tallarin", "spaghetti", "spagueti", "espagueti", "linguine", "fettuccine",
                               "fetuccine", "cinta", "vermicelli", "bucatini", "largo", "nido")),
            ("fideos cortos", ("mostachol", "penne", "tirabuzon", "fusil", "mono", "codito", "rigatoni",
                               "farfalle", "spirale", "macarron", "conchita", "rigate", "corto", "tortiglioni")),
        ),
    ),
    "salsas-de-tomate": (
        _tipo(
            ("pesto", ("pesto",)),
            ("salsa picante", ("chili", "chilli", "picante")),
            ("salsa blanca", ("blanca", "bechamel")),
            ("pure de tomate", ("pure",)),
            ("tomate triturado", ("triturado",)),
            ("tomate cubeteado", ("cubeteado", "en cubos")),
            ("tomate perita", ("perita", "pelado", "pelati", "entero")),
            ("extracto de tomate", ("extracto", "concentrado")),
            ("salsa", ("salsa", "filetto", "fileto", "pomarola", "bolognesa", "napolitana")),
        ),
    ),
    "conservas-de-pescado": (
        _tipo(
            ("atun", ("atun",)),
            ("caballa", ("caballa",)),
            ("sardinas", ("sardina",)),
            ("anchoas", ("anchoa", "anchoita")),
            ("boquerones", ("boqueron",)),
            ("mejillones", ("mejillon", "cholga", "chorito", "almeja")),
            ("pulpo", ("pulpo",)),
            ("calamar", ("calamar",)),
            ("salmon", ("salmon",)),
            ("merluza", ("merluza",)),
            ("paella", ("paella",)),
        ),
    ),
    "conservas-de-vegetales": (
        _tipo(
            ("garbanzos", ("garbanzo",)),
            ("lentejas", ("lenteja",)),
            ("porotos", ("poroto",)),
            ("arvejas", ("arveja",)),
            ("choclo", ("choclo", "maiz")),
            ("palmitos", ("palmito",)),
            ("champinones", ("champi", "hongo")),
            ("jardinera", ("jardinera", "macedonia")),
            ("alcaparras", ("alcaparra",)),
            ("chauchas", ("chaucha",)),
            ("zanahorias", ("zanahoria",)),
            ("remolacha", ("remolacha",)),
            ("esparragos", ("esparrago",)),
            ("morrones", ("morron", "pimiento")),
            ("alcauciles", ("alcaucil",)),
            ("tomates", ("tomate",)),
            ("duraznos", ("durazno",)),
            ("anana", ("anana",)),
            ("peras", ("pera ", "peras")),
            ("coctel de frutas", ("coctel", "ensalada de frutas")),
        ),
    ),
    "encurtidos-y-aceitunas": (
        _attribute(None, (
            ("berenjenas", ("berenjena",)),
            ("cebollitas", ("cebollita",)),
            ("pepinillos", ("pepinillo",)),
            ("pickles", ("pickle",)),
            ("ajies", ("aji", "jalapeno", "pimiento", "morron")),
            ("alcaparras", ("alcaparra",)),
            ("chucrut", ("chucrut",)),
            ("giardiniera", ("giardiniera",)),
            ("aceitunas rellenas", ("rellena",)),
            ("aceitunas negras", ("negra",)),
            ("aceitunas verdes", ("aceituna",)),
        )),
    ),
    "caldos-y-sopas": (
        _tipo(
            ("pure instantaneo", ("pure",)),
            ("bolsa para horno", ("bolsa",)),
            ("sopa", ("sopa",)),
            ("caldo", ("caldo",)),
            ("saborizador", ("saborizador", "sabor en polvo")),
            ("condimento", ("condimento", "sazon")),
            ("salsa en polvo", ("salsa",)),
        ),
    ),
    "reposteria": (
        _tipo(
            ("gelatina", ("gelatina",)),
            ("flan", ("flan",)),
            ("mousse", ("mousse",)),
            ("postre", ("postre",)),
            ("bizcochuelo", ("bizcochuelo",)),
            ("premezcla de torta", ("torta", "brownie", "budin", "muffin", "cookie", "panqueque")),
            ("premezcla de pizza o pan", ("pizza", "pan ")),
            ("polvo para hornear", ("polvo de hornear", "polvo para hornear", "bicarbonato")),
            ("levadura", ("levadura",)),
            ("esencia", ("esencia",)),
            ("coco rallado", ("coco",)),
            ("decoracion", ("chips", "grana", "decorac", "confite", "colorante", "fondant", "glase")),
            ("crema", ("chantilly", "crema")),
        ),
        SIN_AZUCAR,
    ),
    "golosinas": (
        _tipo(
            ("chicles", ("chicle",)),
            ("caramelos", ("caramelo", "pastilla")),
            ("gomitas", ("gomita", "goma")),
            ("chupetines", ("chupetin",)),
            ("turron", ("turron",)),
            ("bombones", ("bombon",)),
            ("garrapinada", ("garrapinada",)),
            ("mani con chocolate", ("mani con chocolate", "confitado", "rocklets")),
            ("obleas", ("oblea",)),
            ("malvaviscos", ("malvavisco", "marshmallow")),
            ("huevo de pascua", ("huevo",)),
        ),
        SIN_AZUCAR,
    ),
    "snacks": (
        _tipo(
            ("pochoclos", ("pochoclo", "pop")),
            ("chizitos", ("chizito", "cheetos")),
            ("nachos", ("nacho", "doritos", "tortilla chips")),
            ("palitos", ("palito",)),
            ("conitos", ("conito",)),
            ("tutucas", ("tutuca",)),
            ("papas fritas", ("papa",)),
            ("mani", ("mani",)),
            ("frutos secos", ("nuez", "nueces", "almendra", "castana", "mix", "pasas", "frutos secos", "pistacho")),
            ("galletas de arroz", ("arroz",)),
        ),
    ),
    # ---------------- Desayuno y merienda
    "dulce-de-leche": (
        _attribute("clasico", (("repostero", ("repostero",)),)),
        SIN_AZUCAR,
    ),
    "mermeladas-y-miel": (
        _tipo(
            ("dulce de membrillo", ("membrillo",)),
            ("dulce de batata", ("batata",)),
            ("miel", ("miel",)),
            ("mermelada", ("mermelada", "confitura")),
            ("dulce", ("dulce",)),
        ),
        SIN_AZUCAR,
    ),
    "galletitas": (
        _attribute("dulce", (
            ("salada", ("cracker", "salada", "de agua", "criollita", "traviata", "express", "club social",
                        "salvado", "grisin", "tostada")),
            ("rellena", ("rellena", "oreo", "sonrisa")),
            ("de arroz", ("arroz",)),
        )),
    ),
    "alfajores": (
        _attribute("comun", (("de arroz", ("arroz",)),)),
        _attribute("simple", (("triple", ("triple",)),)),
    ),
    "chocolates": (
        _attribute("tableta", (
            ("galletita", ("galle",)),
            ("huevo", ("huevo",)),
            ("en rama", ("rama",)),
            ("confitado", ("lenteja", "confitad", "confite", "rocklets")),
            ("bombones", ("bombon",)),
            ("mani con chocolate", ("mani",)),
        )),
        _attribute("con leche", (
            ("amargo", ("amargo",)),
            ("blanco", ("blanco",)),
        )),
    ),
    "cafe": (
        _tipo(
            ("capsulas", ("capsula",)),
            ("cappuccino", ("cappuccino", "capuccino", "capuchino")),
            ("instantaneo", ("instantaneo", "soluble")),
            ("en grano", ("grano",)),
            ("molido", ("molido",)),
        ),
        _attribute("tostado", (("torrado", ("torrado",)),)),
    ),
    "yerba-mate": (
        _attribute("yerba", (("mate cocido", ("mate cocido", "saquito")),)),
        _attribute("tradicional", (
            ("compuesta", ("hierba", "compuesta", "menta", "cachamate", "jengibre", "gengibre", "boldo",
                           "peperina", "burrito", "naranja", "limon")),
        )),
        _attribute("con palo", (("sin palo", ("despalada", "sin palo")),)),
    ),
    "azucar-y-endulzantes": (
        _tipo(
            ("edulcorante", ("edulcorante", "sacarina", "sucralosa", "stevia", "xilitol", "eritritol")),
            ("azucar negra", ("negra", "mascabo")),
            ("azucar impalpable", ("impalpable",)),
            ("azucar organica", ("organica",)),
            ("azucar light", ("light",)),
            ("azucar rubia", ("rubia",)),
            ("azucar", ("azucar",)),
        ),
        _attribute("polvo", (("liquido", ("liquido",)),)),
    ),
    "cereales": (
        _tipo(
            ("barra", ("barra",)),
            ("granola", ("granola",)),
            ("muesli", ("muesli",)),
            ("almohaditas", ("almohadita",)),
            ("aritos", ("arito", "fruit loops")),
            ("copos", ("copo", "flakes")),
            ("inflado", ("inflado",)),
            ("avena", ("avena",)),
        ),
        _attribute("comun", (("proteica", ("proteic", "proteina", "protein")),)),
        SIN_AZUCAR,
    ),
    "te-e-infusiones": (
        _attribute("te negro", (
            ("chai", ("chai",)),
            ("te verde", ("verde",)),
            ("te rojo", ("rojo",)),
            ("manzanilla", ("manzanilla",)),
            ("boldo", ("boldo",)),
            ("tilo", ("tilo",)),
            ("peperina", ("peperina",)),
            ("menta", ("menta",)),
            ("cedron", ("cedron",)),
            ("hierbas", ("hierba",)),
        )),
    ),
    "cacao-y-chocolatadas": (
        _attribute("cacao en polvo", (
            ("chocolate para taza", ("taza",)),
            ("chocolate amargo", ("amargo",)),
        )),
    ),
    "pan-lactal": (
        _attribute("blanco", (
            ("panaderia", ("ciriola", "frances", "baguette", "felipe", "flauta")),
            ("tostadas", ("tostada",)),
            ("salvado", ("salvado",)),
            ("integral", ("integral",)),
            ("con semillas", ("semilla", "cereal", "lino", "chia")),
        )),
    ),
    "pan-hamburguesa": (
        _tipo(
            ("pan de hamburguesa", ("hamburguesa", "burger")),
            ("pan de pancho", ("pancho",)),
        ),
    ),
    "budines-y-bizcochuelos": (
        _tipo(
            ("pan dulce", ("pan dulce",)),
            ("madalenas", ("madalena", "magdalena")),
            ("muffins", ("muffin",)),
            ("brownie", ("brownie",)),
            ("arrollado", ("arrollado",)),
            ("budin", ("budin", "pudding", "pudin")),
            ("bizcochuelo", ("bizcochuelo",)),
            ("biscuits", ("biscuit",)),
        ),
    ),
    # ---------------- Bebidas
    "aguas": (
        _attribute("agua", (("saborizada", ("saborizada", "levite", "aquarius")),)),
        GAS,
        SIN_AZUCAR,
    ),
    "gaseosas": (SIN_AZUCAR,),
    "jugos": (
        _attribute("liquido", (
            ("en polvo", ("polvo", "clight", "tang")),
            ("concentrado", ("concentrado", "para diluir")),
        )),
        SIN_AZUCAR,
    ),
    "energizantes-e-isotonicas": (
        _tipo(
            ("isotonica", ("isotonica", "powerade", "gatorade")),
            ("energizante", ("energizante", "monster", "red bull", "speed", "rockstar", "black fire")),
        ),
        SIN_AZUCAR,
    ),
    "cervezas": (
        _attribute("rubia", (
            ("negra", ("negra", "oscura", "stout", "porter")),
            ("roja", ("roja", "red")),
        )),
        _attribute("con alcohol", (("sin alcohol", ("sin alcohol", "0,0", "0.0")),)),
    ),
    "vinos": (
        _attribute("tinto", (
            ("rosado", ("rosado", "rose", "blush")),
            ("blanco", ("blanco", "chardonnay", "sauvignon blanc", "torrontes", "viognier", "semillon", "chenin")),
        )),
        _attribute("seco", (("dulce", ("dulce", "cosecha tardia", "late harvest", "tardio")),)),
    ),
    "espumantes-y-sidras": (
        _tipo(
            ("sidra", ("sidra",)),
            ("espumante", ("espumante", "champ")),
            ("vino", ("vino",)),
        ),
        _attribute("brut", (("dulce", ("dulce", "demi", "sweet", "dolce")),)),
        _attribute("blanco", (("rosado", ("rose", "rosado")),)),
    ),
    "aperitivos-y-licores": (
        _tipo(
            ("aperitivo", ("aperitivo", "vermouth", "vermut", "campari", "aperol", "gancia", "cynar", "americano")),
            ("licor", ("licor",)),
            ("fernet", ("fernet",)),
            ("gin", ("gin",)),
            ("vodka", ("vodka",)),
            ("whisky", ("whisky", "whiskey")),
            ("ron", ("ron",)),
            ("tequila", ("tequila",)),
            ("cachaca", ("cachaca",)),
            ("pisco", ("pisco",)),
            ("grappa", ("grappa",)),
        ),
    ),
    # ---------------- Congelados
    "papas-congeladas": (
        _attribute("baston", (
            ("noisette", ("noisette",)),
            ("croquetas", ("croqueta", "golazo")),
            ("caritas", ("carita", "smile")),
            ("rejilla", ("rejilla",)),
            ("rusticas", ("rustica",)),
        )),
    ),
    "hamburguesas-congeladas": (
        _attribute("medallon", (("milanesa", ("milanesa",)),)),
        # Lo animal primero: "Medallón carne vacuna con soja" es carne.
        _attribute(None, (
            ("animal", ("carne", "vacuna", "pollo", "cerdo", "pescado")),
            ("vegetal", ("soja", "verdura", "espinaca", "calabaza", "garbanzo", "lenteja", "plant", "vegetal",
                         "veggie", "quinoa", "arveja", "brocoli", "notburger", "not burger")),
            ("animal", ("hamburguesa", "paty", "swift", "union ganadera")),
        )),
    ),
    "rebozados-congelados": (
        _tipo(
            ("nuggets", ("nugget",)),
            ("formitas", ("formita",)),
            ("bocaditos", ("bocadito",)),
            ("bastones", ("baston", "stick")),
            ("milanesas", ("milanesa",)),
            ("supremas", ("suprema",)),
            ("patitas", ("patita",)),
        ),
        # "Sabor pollo" y "notchicken" antes que "pollo": son de soja.
        _attribute(None, (
            ("vegetal", ("soja", "notchicken", "not chicken", "vegetal", "plant", "sabor pollo")),
            ("pescado", ("merluza", "pescado", "atun")),
            ("pollo", ("pollo",)),
            ("vegetal", ("espinaca", "calabaza", "brocoli", "verdura")),
        )),
    ),
    "vegetales-congelados": (
        _tipo(
            ("espinaca", ("espinaca",)),
            ("acelga", ("acelga",)),
            ("brocoli", ("brocoli",)),
            ("coliflor", ("coliflor",)),
            ("arvejas", ("arveja",)),
            ("choclo", ("choclo",)),
            ("chauchas", ("chaucha",)),
            ("zanahoria", ("zanahoria",)),
            ("calabaza", ("calabaza", "zapallo")),
            ("cebolla", ("cebolla",)),
            ("morron", ("morron", "pimiento")),
            ("mix de verduras", ("jardinera", "mix", "primavera", "salteado", "wok", "verduras")),
            ("frutillas", ("frutilla",)),
            ("frambuesas", ("frambuesa",)),
            ("arandanos", ("arandano",)),
            ("frutos rojos", ("frutos rojos", "frutos del bosque")),
            ("mango", ("mango",)),
            ("palta", ("palta",)),
            ("anana", ("anana",)),
        ),
    ),
    "comidas-congeladas": (
        _tipo(
            ("pizza", ("pizza",)),
            ("empanadas", ("empanada",)),
            ("tarta", ("tarta",)),
            ("chipa", ("chipa",)),
            ("barritas de muzzarella", ("barrita", "bastones de muzza")),
            ("croquetas", ("croqueta",)),
            ("pancakes", ("pancake", "panqueque")),
            ("lasagna", ("lasagna", "lasana")),
            ("canelones", ("canelon",)),
            ("sorrentinos", ("sorrentino",)),
            ("ravioles", ("raviol",)),
            ("pastel de papas", ("pastel",)),
            ("salchichas", ("salchicha", "notsalxicha")),
            ("medallones", ("medallon",)),
        ),
    ),
    "pescados-congelados": (
        _tipo(
            ("merluza", ("merluza",)),
            ("langostinos", ("langostino",)),
            ("camarones", ("camaron",)),
            ("trucha", ("trucha",)),
            ("salmon", ("salmon",)),
            ("kani kama", ("kani", "surimi")),
            ("rabas", ("raba", "calamar")),
            ("mariscos", ("marisco", "paella")),
            ("abadejo", ("abadejo",)),
            ("pollo de mar", ("pollo de mar",)),
            ("atun", ("atun",)),
        ),
        _attribute("natural", (("rebozado", ("rebozad", "baston", "milanesa", "medallon", "croc", "empanad")),)),
    ),
    "helados": (
        _attribute("pote", (
            ("palito", ("palito",)),
            ("bombon", ("bombon",)),
            ("postre helado", ("postre", "torta")),
            ("cucurucho", ("cucurucho", "cono")),
        )),
        SIN_AZUCAR,
    ),
    # ---------------- Frutas y verduras
    "frutas": (
        _tipo(
            ("manzana", ("manzana",)),
            ("pera", ("pera",)),
            ("naranja", ("naranja",)),
            ("mandarina", ("mandarina",)),
            ("pomelo", ("pomelo",)),
            ("limon", ("limon",)),
            ("lima", ("lima",)),
            ("banana", ("banana", "platano")),
            ("frutilla", ("frutilla",)),
            ("arandano", ("arandano",)),
            ("frambuesa", ("frambuesa",)),
            ("mora", ("mora",)),
            ("uva", ("uva",)),
            ("durazno", ("durazno",)),
            ("pelon", ("pelon",)),
            ("ciruela", ("ciruela",)),
            ("kiwi", ("kiwi",)),
            ("melon", ("melon",)),
            ("sandia", ("sandia",)),
            ("anana", ("anana",)),
            ("mango", ("mango",)),
            ("palta", ("palta",)),
            ("cereza", ("cereza",)),
            ("damasco", ("damasco",)),
            ("higo", ("higo",)),
            ("coco", ("coco",)),
            ("granada", ("granada",)),
            ("maracuya", ("maracuya",)),
            ("papaya", ("papaya", "mamon")),
        ),
    ),
    "verduras": (
        _tipo(
            ("tomate cherry", ("cherry",)),
            ("tomate", ("tomate",)),
            ("batata", ("batata",)),
            ("papa", ("papa",)),
            ("cebolla de verdeo", ("verdeo",)),
            ("cebolla", ("cebolla",)),
            ("ajo", ("ajo",)),
            ("zanahoria", ("zanahoria",)),
            ("lechuga", ("lechuga",)),
            ("repollo", ("repollo",)),
            ("acelga", ("acelga",)),
            ("espinaca", ("espinaca",)),
            ("zapallito", ("zapallito",)),
            ("zapallo", ("zapallo", "calabaza", "anco")),
            ("berenjena", ("berenjena",)),
            ("morron", ("morron", "pimiento")),
            ("aji", ("aji", "jalapeno")),
            ("choclo", ("choclo",)),
            ("brocoli", ("brocoli",)),
            ("coliflor", ("coliflor",)),
            ("pepino", ("pepino",)),
            ("apio", ("apio",)),
            ("puerro", ("puerro",)),
            ("remolacha", ("remolacha",)),
            ("rabanito", ("rabanito", "rabano")),
            ("rucula", ("rucula",)),
            ("radicheta", ("radicheta",)),
            ("achicoria", ("achicoria",)),
            ("champinon", ("champi", "hongo", "girgola")),
            ("perejil", ("perejil",)),
            ("albahaca", ("albahaca",)),
            ("chaucha", ("chaucha",)),
            ("esparrago", ("esparrago",)),
            ("jengibre", ("jengibre",)),
            ("hinojo", ("hinojo",)),
            ("ensalada lista", ("ensalada", "blend", "mix", "rallada")),
        ),
    ),
    # ---------------- Carnes
    "carnes": (_meat_cut,),
    "pollo": (
        _tipo(
            ("milanesa", ("milanesa",)),
            ("hamburguesa", ("hamburguesa",)),
            ("pata muslo", ("pata muslo", "pata y muslo", "cuarto trasero")),
            ("suprema", ("suprema", "pechuga")),
            ("muslo", ("muslo",)),
            ("pata", ("pata",)),
            ("alitas", ("ala ", "alas", "alita")),
            ("menudos", ("menudo", "higado", "molleja", "corazon")),
            ("pollo entero", ("entero", "parrillero")),
        ),
    ),
    # ---------------- Limpieza
    "papel-higienico": (
        _attribute("simple", (
            ("triple", ("triple",)),
            ("doble", ("doble",)),
        )),
    ),
    "rollos-y-servilletas": (
        _tipo(
            ("rollo de cocina", ("rollo",)),
            ("servilletas", ("servilleta",)),
            ("panuelos", ("panuelo", "tissue")),
        ),
    ),
    "detergente": (_attribute("listo", (("para diluir", ("diluir", "rinde")),)),),
    "lavavajillas": (
        _tipo(
            ("tabletas", ("tableta", "pastilla", "capsula")),
            ("abrillantador", ("abrillantador",)),
            ("sal", ("sal ",)),
            ("gel", ("gel",)),
            ("polvo", ("polvo",)),
            ("liquido", ("liquido",)),
        ),
    ),
    "limpiadores-de-cocina": (
        _tipo(
            ("toallitas", ("toallita",)),
            ("cremoso", ("cremoso",)),
            ("multiuso", ("multiuso", "multisuperficie")),
            ("antigrasa", ("cocina", "antigrasa", "desengrasante")),
            ("desinfectante", ("desinfectante",)),
        ),
        REPUESTO,
    ),
    "limpiadores-de-bano": (
        _tipo(
            ("destapa canerias", ("destapa", "caneria")),
            ("inodoro", ("inodoro", "harpic")),
            ("antihongos", ("hongo", "moho")),
            ("antisarro", ("sarro",)),
            ("limpiador de bano", ("bano",)),
        ),
        REPUESTO,
    ),
    "pastillas-inodoro": (
        _tipo(
            ("canasta liquida", ("liquida",)),
            ("canasta solida", ("solida",)),
            ("pastillas", ("pastilla",)),
            ("bloque adhesivo", ("bloque", "adhesivo", "gel", "disco")),
        ),
        REPUESTO,
    ),
    "limpiavidrios": (
        _attribute("liquido", (("herramienta", ("secador", "limpiamax", "aquasplash", "escurridor")),)),
        REPUESTO,
    ),
    "limpiadores-de-piso": (
        _attribute("limpiador", (
            ("autobrillo", ("autobrillo", "cera", "acondicionador")),
            ("para diluir", ("diluir", "rinde")),
        )),
    ),
    "jabon-para-ropa": (
        _tipo(
            ("capsulas", ("capsula", "pods")),
            ("en barra", ("barra", "pan de jabon")),
            ("en polvo", ("polvo",)),
            ("liquido", ("liquido", "gel")),
        ),
    ),
    "suavizantes": (CONCENTRADO,),
    "lavandina": (
        _attribute("liquida", (("gel", ("gel",)),)),
        CONCENTRADO,
    ),
    # ---------------- Perfumería
    "shampoo": (
        INFANTIL,
        _attribute("comun", (("anticaspa", ("caspa",)),)),
    ),
    "acondicionadores": (
        INFANTIL,
        _attribute("acondicionador", (
            ("crema para peinar", ("peinar",)),
            ("mascara", ("mascara", "tratamiento", "bano de crema")),
        )),
    ),
    # El tono es lo que se compra: ningún otro tinte lo reemplaza.
    "coloracion": (_never,),
    "desodorantes": (
        GENERO,
        _attribute("aerosol", (
            ("roll on", ("roll",)),
            ("barra", ("barra", "stick")),
            ("crema", ("crema",)),
        )),
    ),
    "jabones": (
        INFANTIL,
        _attribute("barra", (("liquido", ("liquido",)),)),
    ),
    "pasta-dental": (
        INFANTIL,
        _attribute("pasta", (("adhesivo para protesis", ("adhesiv", "corega", "protesis")),)),
        _attribute("comun", (("sensibilidad", ("sensib", "sensitiv")),)),
    ),
    "cepillos-de-dientes": (
        INFANTIL,
        _attribute("cepillo", (
            ("electrico", ("electric", "sonic", "bateria", "pila")),
            ("interdental", ("interdental",)),
            ("kit", ("kit",)),
            ("hilo dental", ("hilo", "seda dental")),
        )),
    ),
    "toallitas-femeninas": (_attribute("dia", (("nocturna", ("nocturna", "noche")),)),),
    "tampones": (
        _tipo(
            ("super plus", ("super plus",)),
            ("super", ("super",)),
            ("medio", ("medio", "regular")),
            ("mini", ("mini",)),
        ),
    ),
    "afeitado": (
        _tipo(
            ("repuesto", ("repuesto", "cartucho")),
            ("gel", ("gel",)),
            ("espuma", ("espuma",)),
            ("after shave", ("after shave", "balsamo", "locion")),
            ("crema de afeitar", ("crema",)),
            ("maquina", ("maquina", "afeitadora", "prestobarba")),
        ),
        _attribute("unisex", (("femenino", ("venus", "soleil", "femenin", "mujer", "women", "rosa")),)),
    ),
    "cremas-corporales": (
        INFANTIL,
        _attribute("corporal", (
            ("set", ("set ", "kit")),
            ("manos", ("mano",)),
            ("facial", ("facial", "rostro")),
            ("pies", ("pie ", "pies")),
        )),
    ),
    "proteccion-solar": (
        INFANTIL,
        _attribute("protector", (
            ("bronceador", ("bronceador",)),
            ("post solar", ("post solar", "after sun", "aftersun")),
        )),
        _attribute("corporal", (("facial", ("facial", "rostro")),)),
    ),
    "algodon-e-hisopos": (
        _tipo(
            ("hisopos", ("hisopo", "cotonete")),
            ("discos", ("disco",)),
            ("panos desmaquillantes", ("pano", "desmaquill")),
            ("algodon", ("algodon",)),
        ),
    ),
}


def attributes_match(shelf: str | None, original_name: str, candidate_name: str) -> bool:
    """¿Coinciden en todos los atributos de la góndola? Sin tabla, siempre."""
    for read in SHELF_ATTRIBUTES.get(shelf, ()):
        value = read(original_name)
        if value is None or value != read(candidate_name):
            return False
    return True


def dietary_match(original: dict, candidate: dict) -> bool:
    """Un sin TACC o vegano sólo se reemplaza por otro que también lo sea (FALSE es "sin evidencia")."""
    return all(candidate.get(flag) for flag in ("is_gluten_free", "is_vegan") if original.get(flag))
