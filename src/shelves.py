# src/shelves.py
"""
Las góndolas: la única taxonomía del proyecto.

Existe por una razón concreta: la unificación del catálogo es por EAN
(unified_id = "prod_" + ean), así que un producto sólo es comparable entre
tiendas si las tres barrieron *la misma góndola*. Tres listas `MVP_CATEGORIES`
independientes cumplían eso por casualidad y se desincronizaban en silencio —
nada falla cuando Coto scrapea yerba y Día no, simplemente el optimizador deja
de tener con qué comparar. Acá la alineación es la estructura del dato: una fila
por góndola, y las claves de las tres tiendas al lado.

**Una fila alcanza para todo.** El slug se guarda en `unified_products.shelf` y
es lo que resuelve, sin ninguna otra tabla:

  * qué categorías barre cada scraper (`keys_for_store`),
  * qué categoría tiene un producto (`GET /category/{slug}`),
  * qué productos son sustituibles entre sí (`src/substitutions.py` compara
    `shelf` por igualdad),
  * y qué muestra el mega-menú (`label` + `section`).

Antes eso eran tres representaciones distintas del mismo hecho, y las tres
peores. `unified_products.category` colapsaba la hoja de la taxonomía en 4
buckets vía un dict de 12 claves, con el 80% del catálogo cayendo en "Otros".
`unified_products.tags` guardaba la ruta completa de la tienda que hubiera
escrito último — al ser por EAN, un producto de las tres cadenas se quedaba con
el vocabulario de una sola. Y `category_tree.py` mergeaba por embeddings las
taxonomías COMPLETAS de Coto y Día para el mega-menú, o sea que casi todo lo que
el usuario clickeaba no tenía productos.

El slug canónico es además lo que hace utilizable la comparación entre tiendas.
Cada cadena nombra distinto el mismo estante —la yerba es "Mate" en Coto, "Yerba
mate" en Día y "Yerba" en Carrefour—, así que comparar por el vocabulario de la
tienda dejaba al producto sin ningún sustituto posible y nada lo avisaba. Medido
sobre esta tabla, sólo 7 de las 20 góndolas solapaban en los tres pares de
tiendas; con el slug canónico solapan las 20 por construcción.
"""
from dataclasses import dataclass, field

STORES = ("coto", "dia", "carrefour")

# El `store_id` con el que cada tienda se guarda en `store_products` y con el que
# la nombran el optimizador y el frontend. Vive acá para que agregar una tienda
# siga siendo una edición en un solo archivo del backend.
STORE_IDS = {
    "coto": "coto_online",
    "dia": "dia_online",
    "carrefour": "carrefour_online",
}

# Los niveles superiores del mega-menú, en el orden en que se muestran. Son
# etiquetas, no una jerarquía real de ninguna cadena: agrupan las góndolas para
# que el menú sea navegable, y nada del backend depende de ellas.
SECTIONS = ("Almacén", "Frescos", "Desayuno y merienda", "Bebidas", "Congelados")


@dataclass(frozen=True)
class Shelf:
    """
    Una góndola.

    `slug` es el valor que termina en `unified_products.shelf`: es la clave real
    del dato y no debería cambiar sin migrar la columna. `label` y `section` son
    presentación pura. `keys` mapea tienda -> claves de SU taxonomía.
    """
    slug: str
    label: str
    section: str
    keys: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def keys_for(self, store: str) -> tuple[str, ...]:
        return self.keys.get(store, ())


def _shelf(slug: str, label: str, section: str, **keys: tuple[str, ...]) -> Shelf:
    return Shelf(slug=slug, label=label, section=section, keys=dict(keys))


# La tabla. Agregar una góndola es una fila; agregar una tienda a una góndola
# existente es un argumento más en su fila.
#
# Cada tienda mapea a una TUPLA de claves, no a una sola, porque las tres
# taxonomías anidan a distinta profundidad: Coto sólo expone hojas de nivel 3 y
# muy finas ("Papas Fritas", "Mani") mientras que Día y Carrefour tienen nodos de
# nivel 2 que ya cubren el estante entero ("almacen/snacks"). Forzar una clave por
# tienda obligaría a elegir entre no cubrir la góndola o inventar una jerarquía
# que la tienda no tiene.
#
# El criterio de selección fue producto ENVASADO DE MARCA: es donde el EAN
# coincide de verdad entre cadenas. La fruta suelta, la carnicería y la fiambrería
# al corte usan códigos internos por tienda y no unifican, así que barrerlas suma
# catálogo pero no suma comparaciones.
_SHELF_LIST = (
    _shelf(
        "aceites-y-aderezos", "Aceites y aderezos", "Almacén",
        coto=("catv00001264", "catv00002212"),
        dia=("almacen/aceites-y-aderezos",),
        carrefour=("almacen/aceites-y-vinagres",
                   "almacen/sal-aderezos-y-saborizadores"),
    ),
    _shelf(
        "harinas", "Harinas", "Almacén",
        coto=("catv00001412", "catv00001411"),
        dia=("almacen/harinas",),
        carrefour=("almacen/harinas",),
    ),
    # Día reorganizó estas dos góndolas y las claves viejas quedaron VIVAS en el
    # árbol de categorías pero con cero productos: `almacen/pastas-y-arroce`
    # (singular) pasó a `almacen/pastas-y-arroces` y `almacen/pastas-seca` se
    # fusionó adentro de ella. Como `tests/test_shelves.py` sólo verifica que la
    # clave exista en el dump, las dos góndolas quedaron vacías para Día sin que
    # nada fallara: 24/24 categorías OK todas las noches, 93 productos que no
    # entraban. Se usan las HOJAS y no el nivel 2 para que las dos góndolas no
    # compartan un ancestro — ver la regla de anidamiento en `keys_for_store`.
    _shelf(
        "arroz-y-legumbres", "Arroz y legumbres", "Almacén",
        coto=("catv00001279", "catv00001276"),
        dia=("almacen/pastas-y-arroces/arroces",
             "almacen/pastas-y-arroces/legumbres-y-semillas"),
        carrefour=("almacen/arroz-y-legumbres",),
    ),
    _shelf(
        "pastas-secas", "Pastas secas", "Almacén",
        coto=("catv00002794",),
        dia=("almacen/pastas-y-arroces/fideos-secos",
             "almacen/pastas-y-arroces/pastas-rellenas"),
        carrefour=("almacen/pastas-secas",),
    ),
    _shelf(
        "salsas-de-tomate", "Salsas de tomate", "Almacén",
        coto=("catv00002933", "catv00002937"),
        dia=("almacen/conservas/tomates-y-salsas",),
        carrefour=("almacen/enlatados-y-conservas/conservas-y-salsas-de-tomate",),
    ),
    _shelf(
        "conservas-de-pescado", "Conservas de pescado", "Almacén",
        coto=("catv00001401",),
        dia=("almacen/conservas/conservas-de-pescados",),
        carrefour=("almacen/enlatados-y-conservas/conservas-de-pescado",),
    ),
    _shelf(
        "snacks", "Snacks", "Almacén",
        coto=("catv00003639", "catv00003636"),
        # Las hojas y no `almacen/picadas`: ese nivel 2 también contiene
        # `aceitunas-y-encurtidos`, que ahora es su propia góndola.
        dia=("almacen/picadas/papas-fritas", "almacen/picadas/snacks"),
        carrefour=("almacen/snacks",),
    ),
    _shelf(
        "leches", "Leches", "Frescos",
        coto=("catv00003266",),
        dia=("frescos/leches",),
        carrefour=("lacteos-y-productos-frescos/leches",),
    ),
    _shelf(
        "yogures", "Yogures", "Frescos",
        coto=("catv00003251",),
        # Una sola clave a propósito: VTEX devuelve resultados IDÉNTICOS para
        # `yogures-enteros` y `yogures-descremados` (mismos 108 productos, mismos
        # ids, verificado contra el endpoint), o sea que no filtra por esa hoja.
        # Con las dos, la segunda pisaba el `source_category` de la primera vía el
        # ON CONFLICT y la dejaba en cero filas: una clave viva que no escribía
        # nada, y 108 productos traídos dos veces por noche.
        dia=("frescos/lacteos/yogures-descremados",),
        carrefour=("lacteos-y-productos-frescos/yogures",),
    ),
    _shelf(
        "quesos", "Quesos", "Frescos",
        coto=("catv00003273", "catv00003803"),
        # `frescos/fiambreria` entero traía 201 productos a esta góndola, pero ese
        # nivel 2 tiene diez hojas y sólo seis son queso: las otras son fiambres,
        # patés, salchichas y pizzas. No se perdía nada, se archivaba mal — y como
        # la góndola es lo que habilita una sustitución, el optimizador podía
        # ofrecer un salame en lugar de un queso. Sólo las hojas de queso (139).
        dia=("frescos/fiambreria/quesos-duros-y-semiduros",
             "frescos/fiambreria/quesos-blandos",
             "frescos/fiambreria/quesos-en-fetas-y-cubos",
             "frescos/fiambreria/rallados-y-en-hebras",
             "frescos/fiambreria/queso-crema-y-untables",
             "frescos/fiambreria/ricotta"),
        carrefour=("lacteos-y-productos-frescos/quesos",),
    ),
    _shelf(
        "dulce-de-leche", "Dulce de leche", "Desayuno y merienda",
        coto=("catv00003250",),
        dia=("desayuno/para-untar/dulces-de-leche",),
        carrefour=("desayuno-y-merienda/mermeladas-y-otros-dulces/dulce-de-leche",),
    ),
    _shelf(
        "mermeladas-y-miel", "Mermeladas y miel", "Desayuno y merienda",
        coto=("catv00001408", "catv00001407"),
        dia=("desayuno/para-untar/mermeladas", "desayuno/para-untar/miel"),
        # Las HOJAS, no el nivel 2. La clave de nivel 2 contenía a la de
        # `dulce-de-leche`, y como los scrapers recorren las góndolas en orden,
        # el barrido del padre pisaba `shelf` y `source_category` de los 27
        # dulces de leche vía el ON CONFLICT: no se perdían, quedaban archivados
        # en la góndola equivocada y `dulce-de-leche` figuraba vacía para
        # Carrefour. Las cuatro hojas parten al padre exacto (23+27+109+16=175).
        # `pasta-de-mani-y-crema-de-avellanas` (16) queda deliberadamente afuera:
        # no es mermelada ni miel, y meterla acá la habilitaría como sustituto de
        # una mermelada. Día excluye la suya por el mismo criterio.
        carrefour=("desayuno-y-merienda/mermeladas-y-otros-dulces/miel",
                   "desayuno-y-merienda/mermeladas-y-otros-dulces/mermeladas-dulces-y-jaleas"),
    ),
    _shelf(
        "galletitas", "Galletitas", "Desayuno y merienda",
        coto=("catv00004082", "catv00003534"),
        dia=("desayuno/galletitas-y-cereales/galletitas-dulces",
             "desayuno/galletitas-y-cereales/galletitas-saladas"),
        carrefour=("desayuno-y-merienda/galletitas-bizcochitos-y-tostadas",),
    ),
    _shelf(
        "alfajores", "Alfajores", "Desayuno y merienda",
        coto=("catv00003596",),
        dia=("almacen/golosinas-y-alfajores/alfajores",),
        carrefour=("desayuno-y-merienda/golosinas-y-chocolates/alfajores",),
    ),
    _shelf(
        "chocolates", "Chocolates", "Desayuno y merienda",
        coto=("catv00003600", "catv00003606"),
        dia=("almacen/golosinas-y-alfajores/chocolates",),
        carrefour=("desayuno-y-merienda/golosinas-y-chocolates/chocolates",),
    ),
    _shelf(
        "cafe", "Café", "Desayuno y merienda",
        coto=("catv00001420",),
        dia=("desayuno/infusiones-y-endulzantes/cafe",),
        carrefour=("desayuno-y-merienda/cafe",),
    ),
    _shelf(
        "yerba-mate", "Yerba y mate", "Desayuno y merienda",
        coto=("catv00001416",),
        dia=("desayuno/infusiones-y-endulzantes/yerba-mate",),
        carrefour=("desayuno-y-merienda/yerba",),
    ),
    _shelf(
        "azucar-y-endulzantes", "Azúcar y endulzantes", "Desayuno y merienda",
        coto=("catv00002784", "catv00002785"),
        dia=("desayuno/infusiones-y-endulzantes/azucar",
             "desayuno/infusiones-y-endulzantes/edulcorantes"),
        carrefour=("desayuno-y-merienda/azucar-y-endulzantes",),
    ),
    _shelf(
        "gaseosas", "Gaseosas", "Bebidas",
        coto=("catv00001540",),
        dia=("bebidas/gaseosas",),
        carrefour=("bebidas/gaseosas",),
    ),
    _shelf(
        "aguas", "Aguas", "Bebidas",
        coto=("catv00004086",),
        dia=("bebidas/aguas",),
        carrefour=("bebidas/aguas",),
    ),

    # ======================================================================
    # Segundo tramo: el resto de las góndolas de alimentos.
    #
    # Las 20 de arriba eran el MVP. Éstas 29 completan las secciones de comida
    # de las tres cadenas (Almacén, Frescos, Desayuno, Bebidas y Congelados).
    #
    # Criterio, el mismo de siempre y ahora medido clave por clave contra los
    # endpoints en vivo antes de escribirlas acá:
    #
    #   * **Las tres tiendas o no entra.** No es purismo: la unificación es por
    #     EAN, así que una góndola que le falta a una cadena suma catálogo y cero
    #     comparaciones, que es lo único que el optimizador consume. Es también
    #     lo que afirma tests/test_shelves.py.
    #   * **Producto envasado de marca.** Quedan afuera, a propósito, la
    #     verdulería, la carnicería, la pescadería fresca y la panadería propia:
    #     se venden por peso con códigos internos de cada tienda, no tienen EAN y
    #     no unifican nunca. Barrerlas engorda la base y baja el porcentaje del
    #     catálogo que sirve para comparar.
    #   * **Ninguna clave adentro de otra** (ver el test homónimo): por eso varias
    #     de acá usan hojas donde el nivel 2 hubiera alcanzado.
    #
    # Una que se relevó y NO entró: `helados`. Coto tiene 150 productos y Día 48,
    # pero `congelados/helados-y-postres` de Carrefour devuelve 0 en vivo, así que
    # la góndola no cumple la regla de las tres tiendas. Está anotada en
    # docs/TODO.md para revisarla en verano.

    # ---------------------------------------------------------------- Almacén
    _shelf(
        "conservas-de-vegetales", "Conservas de vegetales", "Almacén",
        coto=("catv00001400",),
        dia=("almacen/conservas/conservas-de-vegetales",),
        carrefour=("almacen/enlatados-y-conservas/conservas-de-legumbres-y-vegetales",),
    ),
    _shelf(
        "encurtidos-y-aceitunas", "Encurtidos y aceitunas", "Almacén",
        coto=("catv00002860", "catv00002872"),
        dia=("almacen/picadas/aceitunas-y-encurtidos",),
        carrefour=("almacen/enlatados-y-conservas/aceitunas-y-encurtidos",),
    ),
    _shelf(
        "caldos-y-sopas", "Caldos y sopas", "Almacén",
        coto=("catv00001271", "catv00002809"),
        dia=("almacen/comidas-listas/caldos", "almacen/comidas-listas/sopas",
             "almacen/comidas-listas/pure"),
        carrefour=("almacen/caldos-sopas-y-pure",),
    ),
    _shelf(
        "reposteria", "Repostería", "Almacén",
        coto=("catv00001277", "catv00002360"),
        dia=("almacen/reposteria",),
        carrefour=("almacen/reposteria-y-postres",),
    ),
    _shelf(
        "golosinas", "Golosinas", "Almacén",
        # Sin alfajores ni chocolates: ya tienen su propia góndola más arriba.
        coto=("catv00003598", "catv00003599", "catv00003603", "catv00003597",
              "catv00003605"),
        dia=("almacen/golosinas-y-alfajores/caramelos-y-gomitas",
             "almacen/golosinas-y-alfajores/chicles-y-chupetines",
             "almacen/golosinas-y-alfajores/turrones-obleas-y-confitados"),
        carrefour=("desayuno-y-merienda/golosinas-y-chocolates/caramelos-gomitas-y-chupetines",
                   "desayuno-y-merienda/golosinas-y-chocolates/chicles",
                   "desayuno-y-merienda/golosinas-y-chocolates/bocaditos-confites-y-turrones"),
    ),

    # ------------------------------------------------- Desayuno y merienda
    _shelf(
        "cereales", "Cereales y granolas", "Desayuno y merienda",
        coto=("catv00003559", "catv00003555", "catv00003560", "catv00003556",
              "catv00003564", "catv00003557"),
        dia=("desayuno/galletitas-y-cereales/cereales",
             "desayuno/galletitas-y-cereales/avena-y-granola",
             "desayuno/galletitas-y-cereales/barras-de-cereal"),
        carrefour=("desayuno-y-merienda/cereales-y-barritas",),
    ),
    _shelf(
        "te-e-infusiones", "Té e infusiones", "Desayuno y merienda",
        coto=("catv00001415", "catv00001417", "catv00005756"),
        dia=("desayuno/infusiones-y-endulzantes/te",
             "desayuno/infusiones-y-endulzantes/mate-cocido"),
        carrefour=("desayuno-y-merienda/infusiones/te",
                   "desayuno-y-merienda/infusiones/mate-cocido"),
    ),
    _shelf(
        "cacao-y-chocolatadas", "Cacao y chocolatadas", "Desayuno y merienda",
        coto=("catv00001421",),
        dia=("desayuno/infusiones-y-endulzantes/cacao",),
        carrefour=("desayuno-y-merienda/infusiones/cacao",),
    ),
    _shelf(
        "panificados", "Pan y panificados", "Desayuno y merienda",
        coto=("catv00003540", "catv00003531"),
        # Las hojas de `almacen/panaderia`: el nivel 2 también trae budines, que
        # son su propia góndola, y pan rallado, que es otra cosa.
        dia=("almacen/panaderia/panes", "almacen/panaderia/pan-de-molde",
             "almacen/panaderia/pan-de-hamburguesa-y-pancho",
             "almacen/panaderia/facturas-y-medialunas"),
        carrefour=("panaderia/panificados",),
    ),
    _shelf(
        "budines-y-bizcochuelos", "Budines y bizcochuelos", "Desayuno y merienda",
        coto=("catv00003550", "catv00003532"),
        dia=("almacen/panaderia/budines-y-magdalenas",),
        carrefour=("desayuno-y-merienda/budines-y-magdalenas",
                   "panaderia/bizcochuelos-y-piononos"),
    ),

    # ---------------------------------------------------------------- Frescos
    _shelf(
        "manteca-y-margarina", "Manteca y margarina", "Frescos",
        coto=("catv00003277",),
        dia=("frescos/lacteos/mantecas-y-margarinas",),
        carrefour=("lacteos-y-productos-frescos/mantecas-margarinas-y-levaduras",),
    ),
    _shelf(
        "cremas-de-leche", "Cremas de leche", "Frescos",
        coto=("catv00003274",),
        dia=("frescos/lacteos/cremas-de-leche",),
        carrefour=("lacteos-y-productos-frescos/cremas-de-leche",),
    ),
    _shelf(
        "postres-y-flanes", "Postres y flanes", "Frescos",
        coto=("catv00003278",),
        dia=("frescos/lacteos/postres-y-flanes",),
        carrefour=("lacteos-y-productos-frescos/postres",),
    ),
    _shelf(
        "huevos", "Huevos", "Frescos",
        coto=("catv00004084", "catv00004083"),
        # Día los archiva bajo frutas y verduras, no bajo lácteos.
        dia=("frescos/frutas-y-verduras/huevos",),
        carrefour=("lacteos-y-productos-frescos/huevos",),
    ),
    _shelf(
        "fiambres", "Fiambres", "Frescos",
        coto=("catv00003333",),
        dia=("frescos/fiambreria/fiambres", "frescos/fiambreria/pates"),
        carrefour=("lacteos-y-productos-frescos/fiambres",),
    ),
    _shelf(
        "salchichas", "Salchichas", "Frescos",
        coto=("catv00001521",),
        dia=("frescos/fiambreria/salchichas",),
        carrefour=("lacteos-y-productos-frescos/salchichas",),
    ),
    _shelf(
        "pastas-frescas", "Pastas frescas", "Frescos",
        coto=("catv00001864", "catv00001869"),
        dia=("frescos/pastas-frescas",),
        carrefour=("lacteos-y-productos-frescos/tapas-y-pastas-frescas",),
    ),

    # ---------------------------------------------------------------- Bebidas
    _shelf(
        "jugos", "Jugos", "Bebidas",
        coto=("catv00001542",),
        dia=("bebidas/jugos-e-isotonicas/jugos-listos",
             "bebidas/jugos-e-isotonicas/jugos-en-polvo",
             "bebidas/jugos-e-isotonicas/jugos-naturales"),
        carrefour=("bebidas/jugos",),
    ),
    _shelf(
        "energizantes-e-isotonicas", "Energizantes e isotónicas", "Bebidas",
        coto=("catv00001539", "catv00002071"),
        dia=("bebidas/jugos-e-isotonicas/isotonicas-y-energizantes",),
        carrefour=("bebidas/bebidas-energizantes", "bebidas/bebidas-isotonicas"),
    ),
    _shelf(
        "cervezas", "Cervezas", "Bebidas",
        coto=("catv00001527",),
        dia=("bebidas/cervezas",),
        carrefour=("bebidas/cervezas",),
    ),
    _shelf(
        "vinos", "Vinos", "Bebidas",
        coto=("catv00001532",),
        # Las hojas de `bebidas/bodega`: ese nivel 2 también tiene espumantes y
        # sidras, que son la góndola de abajo.
        dia=("bebidas/bodega/vino-tinto", "bebidas/bodega/vino-blanco",
             "bebidas/bodega/vino-rosado"),
        carrefour=("bebidas/vinos",),
    ),
    _shelf(
        "espumantes-y-sidras", "Espumantes y sidras", "Bebidas",
        coto=("catv00001528", "catv00001543"),
        dia=("bebidas/bodega/espumantes", "bebidas/bodega/sidras"),
        carrefour=("bebidas/espumantes-y-sidras",),
    ),
    _shelf(
        "aperitivos-y-licores", "Aperitivos y licores", "Bebidas",
        coto=("catv00001524", "catv00001529", "catv00001525"),
        dia=("bebidas/aperitivos", "bebidas/bebidas-blancas-y-licores"),
        carrefour=("bebidas/fernet-y-aperitivos", "bebidas/bebidas-blancas"),
    ),

    # ------------------------------------------------------------- Congelados
    _shelf(
        "papas-congeladas", "Papas congeladas", "Congelados",
        coto=("catv00003195", "catv00003194", "catv00003197", "catv00003196",
              "catv00003193"),
        dia=("congelados/papas-congeladas",),
        carrefour=("congelados/papas",),
    ),
    _shelf(
        "hamburguesas-congeladas", "Hamburguesas y milanesas", "Congelados",
        coto=("catv00003159", "catv00003149"),
        dia=("congelados/hamburguesas-y-medallones",),
        carrefour=("congelados/hamburguesas-y-medallones",),
    ),
    _shelf(
        "rebozados-congelados", "Nuggets y rebozados", "Congelados",
        coto=("catv00003172", "catv00004513", "catv00004514", "catv00004516",
              "catv00004515"),
        dia=("congelados/rebozados",),
        carrefour=("congelados/nuggets-y-rebozados",),
    ),
    _shelf(
        "vegetales-congelados", "Vegetales congelados", "Congelados",
        coto=("catv00003162", "catv00003169", "catv00003161", "catv00003173",
              "catv00003163", "catv00003166", "catv00003209", "catv00005477",
              "catv00005480"),
        dia=("congelados/vegetales-congelados",),
        # El nivel 2 y no la hoja `vegetales-congelados`: la hoja devuelve 0 en
        # vivo aunque exista en el árbol (mismo caso que los yogures de Día), y el
        # padre trae 24. Cuesta que entre también algo de fruta congelada.
        carrefour=("congelados/frutas-y-vegetales-congelados",),
    ),
    _shelf(
        # No es "pizzas congeladas": la única clave que Carrefour tiene acá es
        # `comidas-y-panificados`, que trae empanadas, tartas y panificados junto
        # con las pizzas. Estrechar el nombre a "pizzas" habría archivado 64
        # productos de Carrefour en una góndola que no es la suya —el mismo error
        # que tenía `quesos` con `frescos/fiambreria`— y habilitado que el
        # optimizador ofrezca una tarta como reemplazo de una pizza. Se ensancha
        # la góndola a lo que las tres tiendas realmente separan.
        "comidas-congeladas", "Comidas congeladas", "Congelados",
        coto=("catv00003211", "catv00003235", "catv00003184", "catv00003236",
              "catv00003214"),
        dia=("congelados/comidas-congeladas",),
        carrefour=("congelados/comidas-y-panificados",),
    ),
    _shelf(
        "pescados-congelados", "Pescados congelados", "Congelados",
        coto=("catv00004499", "catv00004501", "catv00004500"),
        dia=("congelados/pescaderia",),
        carrefour=("congelados/pescados-y-mariscos",),
    ),
)

SHELVES: dict[str, Shelf] = {shelf.slug: shelf for shelf in _SHELF_LIST}

# Índice inverso clave-de-tienda -> slug, armado una vez. `shelf_for_key` se llama
# una vez por categoría scrapeada, pero `save_store_products` no lo llama nunca
# (recibe el slug ya resuelto), así que el costo es irrelevante: el índice está
# para que una clave repetida entre góndolas sea un error detectable y no un
# resultado que depende del orden de iteración.
_KEY_TO_SHELF: dict[tuple[str, str], str] = {}
for _shelf_row in _SHELF_LIST:
    for _store, _keys in _shelf_row.keys.items():
        for _key in _keys:
            _KEY_TO_SHELF[(_store, _key)] = _shelf_row.slug


def keys_for_store(store: str) -> list[str]:
    """
    Las claves de categoría que le tocan a una tienda, en el orden de la tabla.

    Es lo que consume `MVP_CATEGORIES` en cada scraper. Se deduplica preservando
    el orden por si dos góndolas comparten una clave: repetirla sólo gastaría un
    barrido entero para reescribir las mismas filas.
    """
    vistas: dict[str, None] = {}
    for shelf in _SHELF_LIST:
        for key in shelf.keys_for(store):
            vistas.setdefault(key, None)
    return list(vistas)


def shelf_for_key(store: str, category_key: str) -> str | None:
    """
    El slug de la góndola a la que pertenece una clave, o None si no está.

    None sólo puede pasar barriendo una categoría de fuera de la tabla (el
    `__main__` suelto de un scraper). En el camino normal los scrapers iteran
    `keys_for_store()`, así que toda clave está — y `tests/test_shelves.py`
    verifica que además exista en la taxonomía de su tienda.
    """
    return _KEY_TO_SHELF.get((store, category_key))


def shelf_label(slug: str | None) -> str | None:
    """La etiqueta legible de una góndola, o None si el slug no está en la tabla."""
    shelf = SHELVES.get(slug or "")
    return shelf.label if shelf else None


def sections() -> list[dict]:
    """
    Las góndolas agrupadas por sección, en el orden de `SECTIONS` y de la tabla.

    Es lo que sirve `GET /categories` y con lo que el frontend dibuja el mega-menú:
    dos niveles, y cada hoja tiene productos por construcción. Se arma desde la
    tabla, sin tocar la base — no hay ningún estado que consultar.
    """
    por_seccion: dict[str, list[Shelf]] = {name: [] for name in SECTIONS}
    for shelf in _SHELF_LIST:
        por_seccion.setdefault(shelf.section, []).append(shelf)

    return [
        {
            "section": name,
            "shelves": [
                {"slug": s.slug, "label": s.label} for s in por_seccion[name]
            ],
        }
        for name in por_seccion
        if por_seccion[name]
    ]
