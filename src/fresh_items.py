"""
Frutas, verduras y carnes emparejadas a mano entre cadenas.

Estos productos no tienen un EAN que unifique. Lo que traen en el campo del
código de barras es un número de circulación restringida (prefijo 2, ver la
regla 3 de `src/ean.py`): cada cadena lo inventa para lo que pesa en balanza,
así que la misma manzana roja es `2000529000008` en Coto, `2490039000000` en
Día y `2300397000002` en Carrefour. `normalize_ean()` los descarta y el producto
entra como oferta de una sola tienda.

Esta tabla es la otra puerta: un `FreshItem` declara que ciertos SKUs de cada
cadena son el mismo producto, y `save_store_products` les da un único
`unified_id = f"fresh_{slug}"`. Es explícita por la misma razón que
`src/shelves.py`: un umbral de similitud no separa lo igual de lo parecido.
Medido sobre los nombres reales, "ananá" quedó a 0,49 de "nalga" y "manzana
verde" a 0,21 de "manzana roja", más cerca que pares genuinos como "banana" y
"banana selección" (0,29). Los embeddings PROPONEN candidatos
(`src/scripts/curar_frescos.py`); decide una persona.

Reglas de curado, todas por la misma asimetría de siempre (no unificar cuesta
una comparación; unificar mal rompe la promesa):

- **Estricto.** Misma variedad y misma calidad común. Las líneas premium
  ("Elegida", "Etiqueta Negra", "Huella Natural") y las variedades distintas
  (Red Delicious contra Royal Gala) no se juntan: quedan como ofertas sueltas.
- **Un SKU por tienda.** Dos ofertas de la misma cadena bajo un `unified_id`
  obligarían al flattener y al optimizador a elegir entre ellas, y nada lo
  contempla hoy.
- **Nada vendido por pieza con peso aproximado.** Coto publica cosas como
  "Asado (peso aproximado de la unidad 2.170 kg)" con el precio de la PIEZA
  ($18.699), no del kilo. Emparejarlo contra un "Asado x kg" compararía una
  pieza de 2 kg contra un kilo.
- **Al menos dos cadenas.** Un ítem en una sola tienda no compara nada.

`unit` fija la medida con la que se compara, y PISA lo que leyó el parser de
tamaños: Día y Carrefour publican "x Kg." como un sufijo que
`extract_real_volume()` no lee, y lo guardaban como `('un', 1.0)`. Así el
precio por kilo sale igual para las tres, y en el carrito 1 = 1 kg.
"""
from dataclasses import dataclass, field

from src.shelves import STORE_IDS

# Lo que `unit` pone en `unified_products.unit_type` / `total_volume_weight`.
# Sólo dos valores, dentro del vocabulario que exige la etapa 2 ('g'/'ml'/'un').
UNIT_MEASURES = {
    "kg": ("g", 1000.0),
    "un": ("un", 1.0),
}

# Las góndolas donde viven estos productos. Un ítem fuera de ellas es un error de
# curado: un envasado con EAN no necesita esta tabla.
FRESH_SHELVES = ("frutas", "verduras", "carnes", "pollo")


@dataclass(frozen=True)
class FreshItem:
    slug: str
    label: str
    shelf: str
    unit: str
    # tienda ("coto"/"dia"/"carrefour") -> store_sku, tal como lo emite el scraper
    skus: dict[str, str] = field(default_factory=dict)

    @property
    def unified_id(self) -> str:
        return f"fresh_{self.slug}"


def _item(slug: str, label: str, shelf: str, unit: str, **skus: str) -> FreshItem:
    return FreshItem(slug=slug, label=label, shelf=shelf, unit=unit, skus=dict(skus))


# Primera versión, curada el 2026-09-26 sobre lo que las tres cadenas publicaban
# ese día (`python -m src.scripts.curar_frescos`) y revisada por AV. Los
# comentarios de línea dejan asentado por qué se juntaron dos nombres que no son
# idénticos, para no volver a discutirlo en el próximo curado.
#
# Convenciones que valen para toda la tabla:
# - Coto: "Estancias Coto" es su línea común de carnicería, no una premium (sus
#   precios están a la par del "de Novillo" de Carrefour). Todo su pollo se vende
#   por pieza con peso aproximado, así que no aparece.
# - Día: su carnicería online viene casi toda "Envasado al Vacío"; se trata como
#   el mismo corte que el de mostrador.
# - Carrefour: entre "de Novillo" y "de Novillito" se toma Novillo, que es el
#   común; Novillito sólo cuando es la única opción no premium.
FRESH_ITEMS: tuple[FreshItem, ...] = (
    # ------------------------------------------------------------------ frutas
    _item("banana", "Banana x kg", "frutas", "kg",
          coto="sku00000446", dia="90110",
          carrefour="719074"),  # Carrefour la llama "selección"
    _item("limon", "Limón x kg", "frutas", "kg",
          coto="sku00061007", dia="90114", carrefour="8312"),
    _item("manzana-roja", "Manzana roja x kg", "frutas", "kg",
          coto="sku00000529", dia="90039", carrefour="432782"),
    _item("manzana-verde", "Manzana verde (Granny Smith) x kg", "frutas", "kg",
          coto="sku00000527", dia="90112",
          carrefour="8342"),  # Carrefour la llama "especial"
    _item("naranja-jugo", "Naranja de jugo x kg", "frutas", "kg",
          coto="sku00061005", dia="90117",
          carrefour="8314"),  # Carrefour publica dos SKUs iguales (8314 y 270997)
    _item("naranja-ombligo", "Naranja ombligo x kg", "frutas", "kg",
          coto="sku00000420", dia="90118"),
    _item("pera", "Pera x kg", "frutas", "kg",
          dia="90113", carrefour="8357"),  # ninguna de las dos dice la variedad
    _item("ciruela", "Ciruela x kg", "frutas", "kg",
          coto="sku00063594", dia="90138", carrefour="612068"),
    _item("anana", "Ananá x kg", "frutas", "kg",
          coto="sku00017541", dia="90137",
          carrefour="8352"),  # el de Carrefour es marca Dole
    _item("melon-amarillo", "Melón amarillo x kg", "frutas", "kg",
          coto="sku00000538", carrefour="8332"),
    _item("melon-blanco", "Melón blanco x kg", "frutas", "kg",
          coto="sku00000536",
          carrefour="8331"),  # Carrefour tiene otro a $1.999 (719170)
    _item("sandia-mini", "Sandía mini x kg", "frutas", "kg",
          coto="sku00000443", carrefour="8338"),  # "mini" en Coto, "baby" en Carrefour
    _item("mango", "Mango x unidad", "frutas", "un",
          dia="225863", carrefour="691815"),
    _item("coco", "Coco x kg", "frutas", "kg",
          coto="sku00000454", carrefour="8353"),
    _item("kinoto", "Kinoto x kg", "frutas", "kg",
          coto="sku00000500", carrefour="8329"),

    # ---------------------------------------------------------------- verduras
    _item("batata", "Batata x kg", "verduras", "kg",
          coto="sku00072041", dia="90062", carrefour="151817"),
    _item("berenjena", "Berenjena x kg", "verduras", "kg",
          coto="sku00000593", dia="90179", carrefour="8383"),
    _item("cebolla", "Cebolla x kg", "verduras", "kg",
          coto="sku00000602", carrefour="8404"),
    _item("cebolla-morada", "Cebolla morada x kg", "verduras", "kg",
          coto="sku00036144", dia="263485"),  # Coto la llama "roja"
    _item("lechuga-mantecosa", "Lechuga mantecosa x kg", "verduras", "kg",
          coto="sku00000424", dia="90143", carrefour="8427"),
    _item("lechuga-francesa", "Lechuga francesa x kg", "verduras", "kg",
          coto="sku00000650", carrefour="8426"),
    _item("lechuga-morada", "Lechuga morada x kg", "verduras", "kg",
          coto="sku00000651", carrefour="8428"),
    _item("lechuga-capuchina", "Lechuga capuchina x kg", "verduras", "kg",
          coto="sku00000648", carrefour="8421"),
    _item("pepino", "Pepino x kg", "verduras", "kg",
          coto="sku00000665", dia="90145", carrefour="8391"),
    _item("morron-rojo", "Morrón rojo x kg", "verduras", "kg",
          coto="sku00000671", dia="90123", carrefour="8386"),
    _item("morron-verde", "Morrón verde x kg", "verduras", "kg",
          coto="sku00000672", dia="90124", carrefour="8388"),
    _item("morron-amarillo", "Morrón amarillo x kg", "verduras", "kg",
          coto="sku00000709", carrefour="8392"),
    # Sin papa blanca: la única otra oferta es la "Papa Blanca en malla" de Día,
    # que suele ser una selección mejor que la suelta. Coto sola no compara nada.
    _item("remolacha", "Remolacha x kg", "verduras", "kg",
          coto="sku00000677", dia="90125", carrefour="8447"),
    _item("repollo-blanco", "Repollo blanco x kg", "verduras", "kg",
          coto="sku00000678", carrefour="8433"),  # el "Repollo" de Día no es blanco
    _item("tomate-perita", "Tomate perita x kg", "verduras", "kg",
          coto="sku00000683", dia="90074", carrefour="8396"),
    _item("tomate-redondo", "Tomate redondo x kg", "verduras", "kg",
          coto="sku00000684", dia="90127",
          carrefour="432751"),  # "Tomate Red" en Coto, "Tomate" a secas en Carrefour
    _item("tomate-cherry", "Tomate cherry x kg", "verduras", "kg",
          coto="sku00000567", dia="90314"),
    _item("zapallito-redondo", "Zapallito redondo x kg", "verduras", "kg",
          coto="sku00000691", dia="90121", carrefour="8399"),
    _item("zapallito-largo", "Zapallito largo x kg", "verduras", "kg",
          coto="sku00000690", carrefour="8400"),
    _item("zapallo-anco", "Zapallo anco x kg", "verduras", "kg",
          coto="sku00000688", dia="90120", carrefour="718888"),
    _item("zapallo-japones", "Zapallo japonés x kg", "verduras", "kg",
          coto="sku00017625", carrefour="718894"),
    _item("zapallo-plomo", "Zapallo plomo x kg", "verduras", "kg",
          coto="sku00000689", carrefour="718895"),
    _item("apio", "Apio x kg", "verduras", "kg",
          coto="sku00000588", dia="90130", carrefour="8431"),
    _item("brocoli", "Brócoli x kg", "verduras", "kg",
          coto="sku00000598", carrefour="8437"),
    _item("coliflor", "Coliflor x kg", "verduras", "kg",
          coto="sku00000619", carrefour="8439"),
    _item("chaucha", "Chaucha x kg", "verduras", "kg",
          coto="sku00000613", carrefour="8394"),
    _item("hinojo", "Hinojo x kg", "verduras", "kg",
          coto="sku00000647", carrefour="8425"),
    _item("jengibre", "Jengibre x kg", "verduras", "kg",
          coto="sku00092926", carrefour="150888"),
    _item("aji-picante", "Ají picante x kg", "verduras", "kg",
          coto="sku00000696", carrefour="89127"),
    # Coto vende estas hojas "x Uni" y Carrefour "x atado": es la misma unidad de
    # venta, un atado.
    _item("rucula", "Rúcula x atado", "verduras", "un",
          coto="sku00039566", carrefour="504734"),
    _item("perejil", "Perejil x atado", "verduras", "un",
          coto="sku00047599", carrefour="504731"),
    _item("radicheta", "Radicheta x atado", "verduras", "un",
          coto="sku00039562", carrefour="504735"),
    _item("puerro", "Puerro x atado", "verduras", "un",
          coto="sku00046632", carrefour="504732"),
    _item("espinaca", "Espinaca x atado", "verduras", "un",
          coto="sku00065678", carrefour="504730"),
    _item("cebolla-de-verdeo", "Cebolla de verdeo x atado", "verduras", "un",
          coto="sku00046634", carrefour="504729"),
    _item("albahaca", "Albahaca x atado", "verduras", "un",
          coto="sku00037201", carrefour="504727"),

    # ------------------------------------------------------------------ carnes
    _item("asado", "Asado x kg", "carnes", "kg",
          dia="279637", carrefour="627285"),
    _item("bife-ancho", "Bife ancho x kg", "carnes", "kg",
          coto="sku00041385", carrefour="647031"),
    _item("bife-angosto", "Bife angosto x kg", "carnes", "kg",
          coto="sku00047987", carrefour="647032"),
    _item("bife-americano", "Bife americano x kg", "carnes", "kg",
          coto="sku00041414", carrefour="678571"),
    _item("bife-de-chorizo", "Bife de chorizo x kg", "carnes", "kg",
          coto="sku00029804", carrefour="662854"),  # Carrefour sólo tiene Novillito
    _item("bola-de-lomo", "Bola de lomo x kg", "carnes", "kg",
          coto="sku00047993", carrefour="678581"),
    _item("carnaza", "Carnaza común x kg", "carnes", "kg",
          coto="sku00041383", dia="90422", carrefour="674622"),
    _item("chiquizuela", "Chiquizuela x kg", "carnes", "kg",
          coto="sku00042659", carrefour="678572"),
    _item("colita-de-cuadril", "Colita de cuadril x kg", "carnes", "kg",
          coto="sku00047990", dia="279544", carrefour="743069"),
    _item("cuadrada", "Cuadrada x kg", "carnes", "kg",
          coto="sku00029905", carrefour="676014"),
    _item("entrana", "Entraña x kg", "carnes", "kg",
          coto="sku00047982", dia="279546"),
    _item("espinazo", "Espinazo x kg", "carnes", "kg",
          coto="sku00042304", carrefour="678574"),
    _item("falda", "Falda x kg", "carnes", "kg",
          coto="sku00041392", dia="125302"),  # Día la llama "parrillera"
    _item("lomo", "Lomo x kg", "carnes", "kg",
          coto="sku00047989", dia="279548",
          carrefour="662859"),  # Carrefour sólo tiene Novillito
    _item("marucha", "Marucha x kg", "carnes", "kg",
          coto="sku00043060", carrefour="678576"),
    _item("matambre", "Matambre x kg", "carnes", "kg",
          coto="sku00047996", dia="279498", carrefour="662844"),
    _item("nalga", "Nalga x kg", "carnes", "kg",
          coto="sku00047991", carrefour="743074"),
    _item("ojo-de-bife", "Ojo de bife x kg", "carnes", "kg",
          coto="sku00029810", dia="279509",
          carrefour="662864"),  # Carrefour sólo tiene Novillito
    _item("osobuco", "Osobuco x kg", "carnes", "kg",
          coto="sku00041463", dia="90357",
          carrefour="678577"),  # Coto especifica "de garrón"
    _item("paleta", "Paleta x kg", "carnes", "kg",
          coto="sku00047984", carrefour="662849"),  # Coto dice "del centro"
    _item("palomita", "Palomita x kg", "carnes", "kg",
          coto="sku00041448", carrefour="678578",
          dia="161330"),  # la de Día viene en medallones
    _item("peceto", "Peceto x kg", "carnes", "kg",
          coto="sku00047994", carrefour="743071"),
    _item("picada-especial", "Carne picada especial x kg", "carnes", "kg",
          coto="sku00069607",
          carrefour="678597"),  # Carrefour publica dos SKUs con el mismo nombre (678597 y 681076)
    _item("roast-beef", "Roast beef x kg", "carnes", "kg",
          coto="sku00047985", carrefour="662851"),
    _item("tapa-de-asado", "Tapa de asado x kg", "carnes", "kg",
          dia="279530", carrefour="674621"),
    _item("tapa-de-nalga", "Tapa de nalga x kg", "carnes", "kg",
          coto="sku00048128", dia="279531", carrefour="678580"),
    _item("tortuguita", "Tortuguita x kg", "carnes", "kg",
          coto="sku00042294", dia="163845", carrefour="662853"),
    _item("vacio", "Vacío x kg", "carnes", "kg",
          coto="sku00047980", dia="162846",
          carrefour="627287"),  # Coto dice "del centro"
    _item("azotillo", "Azotillo x kg", "carnes", "kg",
          coto="sku00041457", carrefour="678570"),
    _item("aranita", "Arañita x kg", "carnes", "kg",
          coto="sku00042660", carrefour="681818"),
    _item("lengua", "Lengua vacuna x kg", "carnes", "kg",
          coto="sku00000082", carrefour="730438"),
    _item("milanesa-de-nalga", "Milanesa de nalga x kg", "carnes", "kg",
          dia="279506", carrefour="662847"),
    _item("milanesa-de-bola-de-lomo", "Milanesa de bola de lomo x kg", "carnes", "kg",
          dia="279502", carrefour="662845"),
    _item("milanesa-de-cuadrada", "Milanesa de cuadrada x kg", "carnes", "kg",
          dia="279504", carrefour="662846"),
    _item("bondiola", "Bondiola de cerdo x kg", "carnes", "kg",
          coto="sku00000943", dia="279500", carrefour="687691"),
    _item("carre-de-cerdo", "Carré de cerdo x kg", "carnes", "kg",
          coto="sku00017162", dia="279523", carrefour="687687"),
    _item("peceto-de-cerdo", "Peceto de cerdo x kg", "carnes", "kg",
          coto="sku00017725", dia="90174"),
    _item("matambre-de-cerdo", "Matambre de cerdo x kg", "carnes", "kg",
          coto="sku00000335", carrefour="687696"),  # Carrefour lo llama "matambrito"
    _item("pechito-de-cerdo", "Pechito de cerdo x kg", "carnes", "kg",
          coto="sku00017410", carrefour="687694"),  # Coto especifica "con manta"

    # ------------------------------------------------------------------- pollo
    _item("pollo-entero", "Pollo entero x kg", "pollo", "kg",
          dia="90150", carrefour="700475"),  # Día tiene otro igual, "Pollo Entero" (90164)
    _item("pata-muslo", "Pata muslo de pollo x kg", "pollo", "kg",
          dia="162805", carrefour="704564"),  # Carrefour lo llama "cuarto trasero"
    _item("pata-de-pollo", "Pata de pollo x kg", "pollo", "kg",
          dia="162803", carrefour="704566"),
    _item("suprema", "Suprema de pollo x kg", "pollo", "kg",
          dia="162808", carrefour="704568"),
)


# (store_id, store_sku) -> ítem. Se arma una vez; los tests garantizan que no hay
# claves repetidas, así que no hay última escritura que gane.
_INDEX = {
    (STORE_IDS[store], sku): item
    for item in FRESH_ITEMS
    for store, sku in item.skus.items()
}


def fresh_item_for(store_id: str, store_sku: str) -> FreshItem | None:
    return _INDEX.get((store_id, store_sku))


def resolve_identity(store_id: str, prod: dict) -> dict:
    """
    Los campos de `unified_products` que dependen de la identidad del producto.

    Para un SKU de la tabla, todo sale del ítem canónico —el nombre deja de ser el
    de la última cadena que escribió—. Para el resto, el camino de siempre: por
    EAN si hay uno, y si no, un id por tienda.
    """
    item = fresh_item_for(store_id, prod['store_sku'])
    if item is not None:
        unit_type, weight = UNIT_MEASURES[item.unit]
        return {
            "unified_id": item.unified_id,
            "ean": None,
            "name": item.label,
            "brand": None,
            "unit_type": unit_type,
            "total_volume_weight": weight,
        }

    ean = prod['ean']
    return {
        "unified_id": f"prod_{ean}" if ean else f"{store_id}_{prod['store_sku']}",
        "ean": ean,
        "name": prod['name'],
        "brand": prod['brand'],
        "unit_type": prod['unit_type'],
        "total_volume_weight": prod['total_volume_weight'],
    }
