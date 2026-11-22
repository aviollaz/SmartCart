# src/shelf_types.py
"""
El filtro "Tipo" de las góndolas grandes, leído del nombre del producto.

Una góndola de 38 páginas (vinos) no se recorre: hace falta poder pedir "sólo
tintos". Ninguna cadena separa así en las seis taxonomías, y partir la góndola
exige que todas lo hagan (src/shelves.py), así que el tipo sale del nombre, que
casi siempre lo dice. Es la generalización de `meat_cuts.py`, que sigue siendo
la tabla de carnes.

Mismas reglas que `meat_cuts.py`: **el orden de la tabla es la prioridad** (gana
el primer tipo cuya palabra aparece al principio de una palabra del nombre
normalizado, así lo específico va antes que lo general; con un espacio al
final, la palabra tiene que ir entera) y lo que no se reconoce
es "Otros", que nunca desaparece del listado.

No reemplaza a `src/attributes.py`: aquel decide qué puede reemplazar a qué y
erra hacia "no es lo mismo"; esto agrupa para mirar, y erra hacia "Otros". Las
tablas se miden contra el catálogo antes de entrar (cuánto cae en "Otros").
"""
import re

from src.meat_cuts import OTROS
from src.meat_cuts import product_type as meat_cut
from src.text_utils import normalize_label

# slug -> (etiqueta del filtro, ((tipo, (palabras...)), ...)).
TYPE_TABLES: dict[str, tuple[str, tuple[tuple[str, tuple[str, ...]], ...]]] = {
    # ---------------- Bebidas
    "vinos": ("Tipo", (
        # Los generosos primero: un "Moscato dulce" es blanco, pero un jerez no
        # tiene color que elegir.
        ("Jerez, oporto y generosos", ("jerez", "oporto", "marsala", "fino ", "vermouth")),
        ("Rosado", ("rosado", "rose", "blush", "clarete")),
        ("Blanco", ("blanco", "blanc", "chardo", "sauvignon blanc", "sauv blanc", "torrontes", "torron",
                    "viognier", "semillon", "chenin", "albarino", "riesling", "moscato", "moscatel",
                    "pinot grigio", "gruner", "white")),
        ("Tinto", ("tinto", "tintas", "malb", "cabernet", "caber", "cab.", "cab ", "merlot", "syrah", "shiraz",
                   "bonarda", "pinot noir", "tempranillo", "petit verdot", "tannat", "blend", "corte",
                   "assemblage", "bordeaux", "red ", "sangiovese", "carmenere", "cs ")),
        ("Dulce", ("dulce", "sweet")),
    )),
    "cervezas": ("Tipo", (
        ("Sin alcohol", ("sin alcohol", "0,0", "0.0")),
        ("Saborizada", ("limon", "pomelo", "flavour", "frutal", "miel")),
        ("De abadía", ("trapp", "tripel", "dubbel", "quadruple", "abadia")),
        ("IPA", ("ipa", "argentipa")),
        ("Negra", ("negra", "stout", "porter", "oscura", "black", "dunkel")),
        ("Roja", ("roja", "red ", "amber", "scottish", "irish")),
        ("Honey", ("honey",)),
        ("Blanca y de trigo", ("blanca", "trigo", "weiss", "weizen", "wheat", "witbier", "white")),
        ("Rubia", ("rubia", "lager", "golden", "pilsen", "pils", "kolsch", "helles", "pale ale", "clasica",
                   "original", "gold", "light", "ultra", "strong", "dorada", "hell", "munich", "oktober")),
    )),
    "espumantes-y-sidras": ("Tipo", (
        ("Sidra", ("sidra",)),
        ("Frizzante", ("frizz", "frizante")),
        ("Fizz y cócteles", ("fizz", "sangria", "coctel", "cocktail", "clerico", "sparkling")),
        # Vinos tranquilos que alguna cadena puso en esta hoja.
        ("Vino", ("vino", "chardonnay")),
        ("Espumante", ("espumante", "champ", "brut", "extra dry", "prosecco", "cava", "nature", "demi sec")),
    )),
    "aperitivos-y-licores": ("Tipo", (
        ("Fernet", ("fernet",)),
        ("Vermut y aperitivos", ("vermouth", "vermut", "aperitivo", "campari", "aperol", "gancia", "cynar",
                                 "americano", "amargo", "bitter", "spritz", "cinzano")),
        ("Whisky", ("whisky", "whiskey", "bourbon")),
        ("Gin", ("gin ",)),
        ("Vodka", ("vodka",)),
        ("Ron", ("ron ", "rum ")),
        ("Tequila", ("tequila",)),
        ("Licor", ("licor", "crema de", "cognac", "cachaca", "pisco", "grappa", "brandy", "cointreau",
                   "baileys", "amaretto", "limoncello", "sambuca", "anis", "triple sec", "jagermeister")),
    )),
    "jugos": ("Tipo", (
        ("En polvo", ("polvo", "tang", "clight", "baggio pronto", "arcor en polvo", "sobre")),
        ("Concentrado", ("concentrado", "para diluir", "rinde")),
        ("Listo para tomar", ("jugo", "nectar", "bebida")),
    )),
    # ---------------- Almacén
    "aceites-y-aderezos": ("Tipo", (
        ("Vinagre", ("vinagre", "aceto")),
        ("Aceite de oliva", ("aceite de oliva", "oliva")),
        ("Aceite", ("aceite", "rocio vegetal", "spray", "ghee", "manteca clarificada", "mct")),
        ("Mayonesa", ("mayonesa", "mayo ")),
        ("Ketchup", ("ketchup",)),
        ("Mostaza", ("mostaza",)),
        ("Salsa golf", ("golf",)),
        ("Jugo de limón", ("jugo de limon", "jugo limon")),
        ("Salsas", ("salsa", "barbacoa", "bbq", "chimichurri", "alioli", "soja", "picante", "tabasco",
                    "aderezo", "dressing", "caesar", "pesto", "humo liquido", "hummus")),
        ("Especias y condimentos", ("sal ", "pimienta", "oregano", "pimenton", "paprika", "aji", "comino",
                                    "condimento", "especia", "ajo", "perejil", "nuez moscada", "laurel",
                                    "curry", "canela", "provenzal", "adobo", "romero", "albahaca", "tomillo",
                                    "sazon", "saborizador", "deshidratad", "molinillo", "semillas", "cebolla",
                                    "tuco", "papelitos", "mix", "hierbas")),
    )),
    "galletitas": ("Tipo", (
        ("De arroz", ("de arroz", "arroz")),
        ("Obleas", ("oblea",)),
        ("Saladas", ("salada", "cracker", "agua", "salvado", "integral", "criollita", "express",
                     "club social", "tostada", "grisin", "queso", "semilla", "sesamo", "girasol", "cereal",
                     "semolada", "marinera", "sin sal", "picante", "hogarena", "cerealitas", "traviata",
                     "sandwich", "hojaldre", "lactal", "copetin", "snack", "salvaditas", "mediatarde")),
        ("Dulces", ("dulce", "rellena", "relleno", "rell", "chocolate", "choc", "vainilla", "chips", "oreo",
                    "pepito", "pepa", "merengue", "merengada", "maria", "manzana", "limon", "frutilla",
                    "frambuesa", "membrillo", "coco", "anillos", "surtid", "lincoln", "melba", "sonrisas",
                    "toddy", "tita", "rhodesia", "cookie", "bizcocho", "biscuit", "biscotti", "budin", "avena",
                    "miel", "polvoron", "donuts", "lenguita", "tartelette", "leche", "manteca", "duquesa",
                    "rocklets", "algarroba", "bitter", "brownie", "alfajor", "macuca", "mana", "terrabusi",
                    "bagley", "okebon", "galletas")),
    )),
    "golosinas": ("Tipo", (
        ("Chupetines", ("chupetin", "chupa")),
        ("Chicles", ("chicle", "beldent", "topline", "bazooka", "bubbaloo", "trident")),
        ("Pastillas", ("pastilla", "tic tac", "mentitas", "halls", "menta")),
        ("Obleas y cubanitos", ("oblea", "cubanito", "wafer", "kitkat")),
        ("Gomitas", ("gomita", "gomas", "mogul", "jelly", "regaliz", "yummy", "gelatina", "goma", "malvavisco",
                     "jalea", "tembleke")),
        ("Caramelos", ("caramelo", "masticable", "media hora", "sugus", "flynn paff", "butter toffee")),
        ("Turrones y bocaditos", ("turron", "bocadito", "crocante", "postre de mani", "garrapinada",
                                  "mantecol", "nucrem", "pasta de mani", "peladilla")),
        ("Bombones y chocolatines", ("bombon", "bombob", "chocolate", "chocolat", "chocolin", "chocolups",
                                     "smack", "mousse", "rocklets", "confite", "skittles", "m&m", "ferrero", "raffaello",
                                     "tabletita", "banad", "cubierto", "choco")),
    )),
    "snacks": ("Tipo", (
        ("Papas fritas", ("papas fritas", "papa frita", "papas", "pringles", "lays")),
        ("Pochoclos", ("pochoclo", "popcorn")),
        ("Maní", ("mani",)),
        ("Frutos secos", ("almendra", "nuez", "nueces", "castana", "caju", "avellana", "pistacho",
                          "frutos secos", "mix", "pasas", "arandano")),
        ("Palitos y chizitos", ("palito", "chizito", "chizzito", "maicito", "conito", "cheese", "curl",
                                "3d", "doritos", "nacho", "tortilla", "chips de maiz", "baston", "krachitos",
                                "conos", "takis", "pizzitos", "nikitos")),
        ("Galletitas y chips", ("galletita", "chips", "saladix", "pita", "pretzel", "tostadita",
                                "grisin", "crackers", "rosquita", "de arroz", "focaccine")),
    )),
    "cereales": ("Tipo", (
        ("Barras", ("barra", "barrita", "bar ")),
        ("Granola y muesli", ("granola", "muesli", "musli")),
        ("Avena", ("avena",)),
        ("Copos y cereales", ("copos", "cereal", "corn flakes", "zucaritas", "choco krispis", "fruit loops",
                              "almohadita", "aritos", "trix", "nesquik", "chocapic", "estrellitas", "inflado",
                              "daditos")),
    )),
    "reposteria": ("Tipo", (
        ("Premezclas", ("premezcla", "premzcla", "pre mezcla", "mezcla para", "bizcochuelo", "torta", "brownie",
                        "chipa", "muffin")),
        ("Harinas y almidones", ("almidon", "fecula", "maizena", "harina")),
        ("Gelatinas y postres", ("gelatina", "postre", "flan", "mousse", "budin de pan")),
        ("Polvo de hornear y levadura", ("polvo de hornear", "polvo para hornear", "levadura", "bicarbonato",
                                         "cremor")),
        ("Esencias y colorantes", ("esencia", "colorante", "extracto", "vainillin", "agua de azahar")),
        ("Decoración", ("grana", "confite", "perlita", "fondant", "glase", "baño de", "cobertura",
                        "merengue", "chips", "mostacilla", "mazapan", "bano", "coco rallado", "salsa")),
        ("Pastas untables", ("pasta de", "mantequilla", "crema de mani", "crema de avellana", "crema de almendra",
                             "nutella", "untable")),
        ("Chocolate para taza y cacao", ("chocolate", "cacao")),
    )),
    "pastas-secas": ("Tipo", (
        ("Ñoquis", ("noqui", "gnocchi")),
        ("Pastas listas", ("knorr", "pasta lista", "listos", "con salsa", "mac and cheese", "mac & cheese",
                           "pasta box", "menu box", "aji no men")),
        ("Rellenas", ("capelet", "capellet", "lucchettini", "raviol")),
        ("Fideos de arroz y legumbres", ("de arroz", "garbanzo", "lenteja", "arveja", "alubia", "legumbre")),
        ("Largos", ("spaghetti", "espagueti", "tallarin", "tallarines", "fettuccine", "fettucine", "linguine",
                    "cabello de angel", "vermicelli", "fideo largo", "bucatini", "fetuccine", "spaguetti",
                    "nidos", "nido", "pappardelle", "fettuccini", "capelli", "cinta")),
        ("Cortos", ("mostachol", "penne", "rigatti", "rigatoni", "tirabuzon", "fusilli", "fusili", "codito",
                    "dedalito", "mono", "farfalle", "moñito", "monito", "ave maria", "municion", "letras",
                    "guisero", "casarecc", "orecchiette", "conchiglie", "caracol", "pipe", "ditali", "corto",
                    "ziti", "maccheroni", "macarron", "fideo soperito", "sopero", "cabellin", "rigate", "codo",
                    "tortiglioni", "corbatita", "mona", "trompetin", "estrella", "letritas")),
        ("Lasagnas y canelones", ("lasagna", "lasana", "canelon")),
    )),
    "mermeladas-y-miel": ("Tipo", (
        ("Miel", ("miel",)),
        ("Dulce de membrillo y batata", ("membrillo", "mebrillo", "batata")),
        ("Mermeladas y dulces", ("mermelada", "dulce", "jalea", "confitura")),
    )),
    "cafe": ("Tipo", (
        # La forma antes que la marca: "Nescafé Gold Tostado y Molido" es molido.
        ("En cápsulas", ("capsula", "dolce gusto", "nespresso", "cafecito")),
        ("En saquitos", ("saquito",)),
        ("Cebada y sucedáneos", ("cebada", "a base de cafe", "malta")),
        ("Café con leche y mezclas", ("capuccino", "cappuccino", "mokaccino", "latte", "3 en 1", "coffee mate",
                                      "coffe mate")),
        ("En grano", ("en grano", "grano")),
        ("Molido", ("molido", "torrado", "tostado", "filtro", "blend", "starbucks", "lavazza", "origin")),
        ("Instantáneo", ("instantaneo", "soluble", "nescafe", "dolca", "liofilizado")),
    )),
    "te-e-infusiones": ("Tipo", (
        ("Mate cocido", ("mate cocido", "yerba")),
        ("Té verde", ("te verde", "green tea")),
        ("Té rojo", ("te rojo",)),
        ("Té negro", ("te negro", "earl gr", "lady grey", "english breakfast", "black")),
        ("Hierbas e infusiones", ("manzanilla", "tilo", "boldo", "menta", "peperina", "cedron", "hierba",
                                  "infusion", "rooibos", "jengibre", "frutos", "frutal", "hibisco", "canela",
                                  "naranja", "frutilla", "durazno", "limon", "diabetes", "relax", "detox")),
        ("Té en hebras y saquitos", ("te ", "hebras", "saquito", "chai", "tea")),
    )),
    "budines-y-bizcochuelos": ("Tipo", (
        ("Pan dulce", ("pan dulce", "panettone", "panetone")),
        ("Madalenas y muffins", ("madalena", "magdalena", "muffin", "cupcake")),
        ("Bizcochuelos y tortas", ("bizcochuelo", "torta", "brownie", "pionono", "vainillas")),
        ("Budines", ("budin", "pudding", "cake", "porcion")),
    )),
    # ---------------- Frescos
    "yogures": ("Tipo", (
        ("Vegetal", ("vegano", "vegetal", "coco ", "almendra", "cocoiogo")),
        ("Bebible", ("bebible", "liquido", "botella", "sachet", "brick")),
        ("Con cereales o colchón", ("cereal", "colchon", "granola", "topping", "con copos")),
        ("Griego", ("griego",)),
        ("Firme", ("firme", "cremoso", "batido", "pote", "yogur", "yogurt")),
    )),
    "pastas-frescas": ("Tipo", (
        ("Tapas de empanada", ("empanada",)),
        ("Tapas de tarta", ("pascualina", "tarta", "hojaldre")),
        ("Ravioles", ("raviol", "sorrentino", "agnolotti")),
        ("Capelettis", ("capel", "cappel")),
        ("Ñoquis", ("noqui", "gnocchi")),
        ("Tallarines y frescos", ("tallarin", "fettuccine", "spaghetti", "cinta", "lasagna", "lasana",
                                  "canelon", "panzotti", "fideos")),
        ("Wraps y masas", ("wrap", "rapidita", "tortilla", "masa", "pizza", "prepizza")),
    )),
    "quesos-duros": ("Tipo", (
        ("Azul", ("azul", "roquefort", "blue")),
        ("Provoleta", ("provoleta", "provo", "provolone")),
        ("Reggianito y parmesano", ("reggianito", "reggiano", "parmesano", "grana padano", "sbrinz",
                                    "goya", "sardo", "romano", "rallado", "raggianito")),
        ("Pategrás y gouda", ("pategras", "gouda", "gruyere", "fontina", "emmental", "holanda", "edam",
                              "danbo", "pepato", "fynbo")),
        ("Tybo y de máquina", ("tybo", "barra", "maquina", "fetas", "feteado")),
        ("Cremosos y otros", ("cuartirolo", "cremoso", "port salut", "banquete", "brie", "muzzarella",
                              "mozzarella", "campo")),
    )),
    "fiambres": ("Tipo", (
        ("Jamón crudo", ("jamon crudo", "crudo", "serrano")),
        ("Jamón cocido", ("jamon cocido", "jamon", "cocido")),
        ("Salame", ("salame", "salamin", "milan", "fuet", "longaniza")),
        ("Salchichón y chorizo seco", ("salchichon", "sopresat", "soppresat", "cantimpalo", "spianat",
                                       "chorizo", "rosca polaca", "pastron")),
        ("Mortadela", ("mortadela",)),
        ("Paleta", ("paleta",)),
        ("Bondiola", ("bondiola",)),
        ("Queso de máquina", ("queso de maquina", "queso")),
        ("Pavita y pollo", ("pavita", "pavo", "pollo")),
        ("Lomito y lomo", ("lomito", "lomo")),
        ("Leberwurst y paté", ("leberwurst", "pate", "pasta de")),
        ("Panceta", ("panceta", "bacon")),
        ("Ahumados", ("ahumad", "salmon", "trucha", "ciervo")),
        ("Matambre", ("matambre",)),
    )),
    # ---------------- Perfumería
    "jabones": ("Tipo", (
        ("Íntimo", ("intimo",)),
        ("Gel de ducha", ("gel de ducha", "gel ducha", "body wash", "corporal")),
        ("En espuma", ("espuma",)),
        ("Líquido", ("liquido", "para manos", "repuesto", "refill", "doypack", "dosificador")),
        ("En barra", ("tocador", "barra", "glicerina", "pan de jabon", "jabon")),
    )),
}

def _key(word: str) -> str:
    """Una palabra con espacio al final va entera ("cs ", "sal "); el resto, como prefijo."""
    return re.escape(word.strip()) + (r"\b" if word.endswith(" ") else "")


_PATTERNS = {
    shelf: (label, tuple(
        (value, re.compile(r"\b(?:" + "|".join(_key(k) for k in keys) + r")"))
        for value, keys in values
    ))
    for shelf, (label, values) in TYPE_TABLES.items()
}

_MEAT_LABEL = "Tipo de corte"


def type_label(shelf: str | None) -> str | None:
    """Cómo se llama el filtro de esa góndola, o None si no tiene."""
    if shelf == "carnes":
        return _MEAT_LABEL
    entry = _PATTERNS.get(shelf)
    return entry[0] if entry else None


def product_type(shelf: str | None, name: str) -> str | None:
    """El tipo del producto, "Otros" si no se reconoce, o None si la góndola no tiene filtro."""
    if shelf == "carnes":
        return meat_cut(shelf, name)
    entry = _PATTERNS.get(shelf)
    if entry is None:
        return None
    text = normalize_label(name)
    return next((value for value, pattern in entry[1] if pattern.search(text)), OTROS)


def type_values(shelf: str | None) -> tuple[str, ...]:
    """Los tipos posibles de una góndola, en el orden de su tabla (sin "Otros")."""
    if shelf == "carnes":
        from src.meat_cuts import CUTS
        return tuple(label for label, _ in CUTS)
    entry = TYPE_TABLES.get(shelf)
    return tuple(value for value, _ in entry[1]) if entry else ()
