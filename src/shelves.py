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

from src.stores import STORE_IDS

# Las tiendas salen del registro de src/stores.py; se reexportan acá porque
# las columnas de SHELVES están indexadas por su `key`.
STORES = tuple(STORE_IDS)

# Los niveles superiores del mega-menú, en el orden en que se muestran. Son
# etiquetas, no una jerarquía real de ninguna cadena: agrupan las góndolas para
# que el menú sea navegable, y nada del backend depende de ellas.
SECTIONS = ("Almacén", "Frescos", "Frutas y verduras", "Carnes", "Desayuno y merienda",
            "Bebidas", "Congelados", "Limpieza", "Perfumería")


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
# al corte usan códigos internos por tienda y no unifican por EAN.
#
# La verdulería y la carnicería son la excepción, y entran por otra puerta: sus
# productos se emparejan a mano en `src/fresh_items.py`, una tabla curada que les
# da un unified_id canónico. Lo que la tabla no lista queda como oferta de una
# sola tienda, igual que cualquier producto sin EAN.
_SHELF_LIST = (
    _shelf(
        "aceites-y-aderezos", "Aceites y aderezos", "Almacén",
        coto=("catv00001264", "catv00002212"),
        dia=("almacen/aceites-y-aderezos",),
        carrefour=("almacen/aceites-y-vinagres",
                   "almacen/sal-aderezos-y-saborizadores"),
        vea=("almacen/aceites-y-vinagres", "almacen/aderezos", "almacen/sal-pimienta-y-especias"),
    ),
    _shelf(
        "harinas", "Harinas", "Almacén",
        coto=("catv00001412", "catv00001411"),
        dia=("almacen/harinas-y-reposteria/harinas-de-trigo",
             "almacen/harinas-y-reposteria/harina-de-maiz-y-otras-harinas"),
        carrefour=("almacen/harinas",),
        vea=("almacen/harinas",),
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
        vea=("almacen/arroz-y-legumbres",),
    ),
    _shelf(
        "pastas-secas", "Pastas secas", "Almacén",
        coto=("catv00002794",),
        dia=("almacen/pastas-y-arroces/fideos-secos",
             "almacen/pastas-y-arroces/pastas-rellenas"),
        carrefour=("almacen/pastas-secas",),
        vea=(
            "almacen/pastas-secas-y-salsas/pastas-secas-guiseras",
            "almacen/pastas-secas-y-salsas/pastas-secas-largas",
        ),
    ),
    _shelf(
        "salsas-de-tomate", "Salsas de tomate", "Almacén",
        coto=("catv00002933", "catv00002937"),
        dia=("almacen/conservas-y-latas/tomates-y-salsas",),
        carrefour=("almacen/enlatados-y-conservas/conservas-y-salsas-de-tomate",),
        vea=("almacen/pastas-secas-y-salsas/salsas",),
    ),
    _shelf(
        "conservas-de-pescado", "Conservas de pescado", "Almacén",
        coto=("catv00001401",),
        dia=("almacen/conservas-y-latas/conservas-de-pescados",),
        carrefour=("almacen/enlatados-y-conservas/conservas-de-pescado",),
        vea=("almacen/conservas/conservas-de-pescado",),
    ),
    _shelf(
        "snacks", "Snacks", "Almacén",
        coto=("catv00003639", "catv00003636"),
        # Las hojas y no `almacen/picadas`: ese nivel 2 también contiene
        # `aceitunas-y-encurtidos`, que ahora es su propia góndola.
        dia=("almacen/picadas/papas-fritas", "almacen/picadas/snacks"),
        carrefour=("almacen/snacks",),
        vea=(
            "almacen/snacks/mani",
            "almacen/snacks/nachos",
            "almacen/snacks/palitos-de-maiz",
            "almacen/snacks/palitos-salados",
            "almacen/snacks/papas-fritas",
            "almacen/snacks/pochoclos",
            "almacen/snacks/snacks",
        ),
    ),
    _shelf(
        "leches", "Leches", "Frescos",
        coto=("catv00003266",),
        dia=("frescos/leches",),
        carrefour=("lacteos-y-productos-frescos/leches",),
        vea=("lacteos/leches", "almacen/desayuno-y-merienda/leches"),
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
        dia=("frescos/lacteos/yogures",),
        carrefour=("lacteos-y-productos-frescos/yogures",),
        vea=("lacteos/yogures",),
    ),
    _shelf(
        "quesos", "Quesos", "Frescos",
        coto=("catv00003273", "catv00003803"),
        # El viejo `frescos/fiambreria` mezclaba quesos con fiambres, patés y
        # salchichas, y como la góndola habilita una sustitución el optimizador
        # podía ofrecer un salame por un queso. Desde oct-2026 Día separa
        # `frescos/quesos`, que es sólo queso (138 productos), y se toma entero.
        dia=("frescos/quesos",),
        carrefour=("lacteos-y-productos-frescos/quesos",),
        vea=("quesos-y-fiambres/quesos",),
    ),
    _shelf(
        "dulce-de-leche", "Dulce de leche", "Desayuno y merienda",
        coto=("catv00003250",),
        dia=("desayuno-y-merienda/dulces-y-untables/dulces-de-leche",),
        carrefour=("desayuno-y-merienda/mermeladas-y-otros-dulces/dulce-de-leche",),
        vea=("lacteos/dulce-de-leche",),
    ),
    _shelf(
        "mermeladas-y-miel", "Mermeladas y miel", "Desayuno y merienda",
        coto=("catv00001408", "catv00001407"),
        dia=("desayuno-y-merienda/dulces-y-untables/mermeladas-y-dulces",
             "desayuno-y-merienda/dulces-y-untables/miel"),
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
        vea=("almacen/desayuno-y-merienda/mermeladas-y-jaleas", "quesos-y-fiambres/dulces"),
    ),
    _shelf(
        "galletitas", "Galletitas", "Desayuno y merienda",
        coto=("catv00004082", "catv00003534"),
        dia=("desayuno-y-merienda/galletitas/galletitas-dulces",
             "desayuno-y-merienda/galletitas/galletitas-saladas"),
        carrefour=("desayuno-y-merienda/galletitas-bizcochitos-y-tostadas",),
        vea=(
            "almacen/desayuno-y-merienda/galletitas-dulces",
            "almacen/desayuno-y-merienda/galletitas-saladas",
        ),
    ),
    _shelf(
        "alfajores", "Alfajores", "Desayuno y merienda",
        coto=("catv00003596",),
        dia=("almacen/golosinas-y-alfajores/alfajores",),
        carrefour=("desayuno-y-merienda/golosinas-y-chocolates/alfajores",),
        vea=("almacen/golosinas-y-chocolates/alfajores",),
    ),
    _shelf(
        "chocolates", "Chocolates", "Desayuno y merienda",
        coto=("catv00003600", "catv00003606"),
        dia=("almacen/golosinas-y-alfajores/chocolates",),
        carrefour=("desayuno-y-merienda/golosinas-y-chocolates/chocolates",),
        vea=("almacen/golosinas-y-chocolates/chocolates", "almacen/golosinas-y-chocolates/bombones"),
    ),
    _shelf(
        "cafe", "Café", "Desayuno y merienda",
        coto=("catv00001420",),
        dia=("desayuno-y-merienda/infusiones/cafe",),
        carrefour=("desayuno-y-merienda/cafe",),
        vea=("almacen/desayuno-y-merienda/cafes",),
    ),
    _shelf(
        "yerba-mate", "Yerba y mate", "Desayuno y merienda",
        coto=("catv00001416",),
        dia=("desayuno-y-merienda/infusiones/yerba-mate",),
        carrefour=("desayuno-y-merienda/yerba",),
        vea=("almacen/desayuno-y-merienda/yerbas",),
    ),
    _shelf(
        "azucar-y-endulzantes", "Azúcar y endulzantes", "Desayuno y merienda",
        coto=("catv00002784", "catv00002785"),
        dia=("desayuno-y-merienda/endulzantes/azucar",
             "desayuno-y-merienda/endulzantes/edulcorantes"),
        carrefour=("desayuno-y-merienda/azucar-y-endulzantes",),
        vea=("almacen/desayuno-y-merienda/azucar-y-edulcorantes",),
    ),
    _shelf(
        "gaseosas", "Gaseosas", "Bebidas",
        coto=("catv00001540",),
        dia=("bebidas/gaseosas",),
        carrefour=("bebidas/gaseosas",),
        vea=("bebidas/gaseosas",),
    ),
    _shelf(
        "aguas", "Aguas", "Bebidas",
        coto=("catv00004086",),
        dia=("bebidas/aguas-y-sodas/aguas-sin-gas", "bebidas/aguas-y-sodas/aguas-con-gas",
             "bebidas/aguas-y-sodas/aguas-saborizadas"),
        carrefour=("bebidas/aguas",),
        vea=("bebidas/aguas",),
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

    # ---------------------------------------------------------------- Almacén
    _shelf(
        "conservas-de-vegetales", "Conservas de vegetales", "Almacén",
        coto=("catv00001400",),
        dia=("almacen/conservas-y-latas/conservas-de-vegetales",),
        carrefour=("almacen/enlatados-y-conservas/conservas-de-legumbres-y-vegetales",),
        vea=("almacen/conservas/conservas-de-verduras-y-legumbres",),
    ),
    _shelf(
        "encurtidos-y-aceitunas", "Encurtidos y aceitunas", "Almacén",
        coto=("catv00002860", "catv00002872"),
        dia=("almacen/picadas/aceitunas-y-encurtidos",),
        carrefour=("almacen/enlatados-y-conservas/aceitunas-y-encurtidos",),
        vea=("quesos-y-fiambres/encurtidos-aceitunas-y-pickles",),
    ),
    _shelf(
        "caldos-y-sopas", "Caldos y sopas", "Almacén",
        coto=("catv00001271", "catv00002809"),
        dia=("almacen/caldos-sopas-y-pure/caldos-y-saborizadores",
             "almacen/caldos-sopas-y-pure/sopas",
             "almacen/caldos-sopas-y-pure/pure-instantaneo"),
        carrefour=("almacen/caldos-sopas-y-pure",),
        vea=(
            "almacen/caldos-sopas-pure-y-bolsas-para-horno/pure",
            "almacen/caldos-sopas-pure-y-bolsas-para-horno/sopas",
            "almacen/caldos-sopas-pure-y-bolsas-para-horno/caldos",
        ),
    ),
    _shelf(
        "reposteria", "Repostería", "Almacén",
        coto=("catv00001277", "catv00002360"),
        dia=("almacen/harinas-y-reposteria/coberturas",
             "almacen/harinas-y-reposteria/insumos-de-reposteria",
             "almacen/harinas-y-reposteria/postres-y-gelatinas",
             "almacen/harinas-y-reposteria/premezclas-y-bizcochuelos"),
        carrefour=("almacen/reposteria-y-postres",),
        vea=("almacen/para-preparar",),
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
        vea=(
            "almacen/golosinas-y-chocolates/caramelos-y-chicles",
            "almacen/golosinas-y-chocolates/turrones-y-grageas",
            "almacen/golosinas-y-chocolates/bocaditos-y-postres",
        ),
    ),

    # ------------------------------------------------- Desayuno y merienda
    _shelf(
        "cereales", "Cereales y granolas", "Desayuno y merienda",
        coto=("catv00003559", "catv00003555", "catv00003560", "catv00003556",
              "catv00003564", "catv00003557"),
        dia=("desayuno-y-merienda/cereales-y-barras/cereales",
             "desayuno-y-merienda/cereales-y-barras/avena-y-granola",
             "desayuno-y-merienda/cereales-y-barras/barras-de-cereal"),
        carrefour=("desayuno-y-merienda/cereales-y-barritas",),
        vea=("almacen/desayuno-y-merienda/cereales",),
    ),
    _shelf(
        "te-e-infusiones", "Té e infusiones", "Desayuno y merienda",
        coto=("catv00001415", "catv00001417", "catv00005756"),
        dia=("desayuno-y-merienda/infusiones/te-y-mate-cocido",),
        carrefour=("desayuno-y-merienda/infusiones/te",
                   "desayuno-y-merienda/infusiones/mate-cocido"),
        vea=("almacen/desayuno-y-merienda/tes",),
    ),
    _shelf(
        "cacao-y-chocolatadas", "Cacao y chocolatadas", "Desayuno y merienda",
        coto=("catv00001421",),
        dia=("desayuno-y-merienda/infusiones/cacao-y-polvos",),
        carrefour=("desayuno-y-merienda/infusiones/cacao",),
        vea=("almacen/desayuno-y-merienda/cacao-y-saborizantes",),
    ),
    _shelf(
        "panificados", "Pan y panificados", "Desayuno y merienda",
        coto=("catv00003540", "catv00003531"),
        # Las hojas de `almacen/panaderia`: el nivel 2 también trae budines, que
        # son su propia góndola, y pan rallado, que es otra cosa.
        dia=("almacen/panaderia-y-panificados/panes-lactales-y-de-mesa",
             "almacen/panaderia-y-panificados/pan-de-hamburguesa-y-pancho",
             "almacen/panaderia-y-panificados/facturas-y-medialunas"),
        carrefour=("panaderia/panificados",),
        vea=(
            "almacen/panificados/lacteados",
            "almacen/panificados/pan-para-hamburguesas-y-panchos",
            "almacen/panificados/integral-y-salvado",
        ),
    ),
    _shelf(
        "budines-y-bizcochuelos", "Budines y bizcochuelos", "Desayuno y merienda",
        coto=("catv00003550", "catv00003532"),
        dia=("almacen/panaderia-y-panificados/pan-dulce-y-budines",),
        carrefour=("desayuno-y-merienda/budines-y-magdalenas",
                   "panaderia/bizcochuelos-y-piononos"),
        vea=(
            "almacen/desayuno-y-merienda/bizcochuelos-budines-y-magdalenas",
            "almacen/desayuno-y-merienda/piononos",
        ),
    ),

    # ---------------------------------------------------------------- Frescos
    _shelf(
        "manteca-y-margarina", "Manteca y margarina", "Frescos",
        coto=("catv00003277",),
        dia=("frescos/lacteos/mantecas-y-margarinas",),
        carrefour=("lacteos-y-productos-frescos/mantecas-margarinas-y-levaduras",),
        vea=("lacteos/mantecas-y-margarinas",),
    ),
    _shelf(
        "cremas-de-leche", "Cremas de leche", "Frescos",
        coto=("catv00003274",),
        dia=("frescos/lacteos/cremas-de-leche",),
        carrefour=("lacteos-y-productos-frescos/cremas-de-leche",),
        vea=("lacteos/cremas",),
    ),
    _shelf(
        "postres-y-flanes", "Postres y flanes", "Frescos",
        coto=("catv00003278",),
        dia=("frescos/lacteos/postres-lacteos",),
        carrefour=("lacteos-y-productos-frescos/postres",),
        vea=("lacteos/postres",),
    ),
    _shelf(
        "huevos", "Huevos", "Frescos",
        coto=("catv00004084", "catv00004083"),
        # Día los archiva bajo frutas y verduras, no bajo lácteos.
        dia=("frutas-y-verduras/huevos",),
        carrefour=("lacteos-y-productos-frescos/huevos",),
        vea=("frutas-y-verduras/huevos",),
    ),
    _shelf(
        "fiambres", "Fiambres", "Frescos",
        coto=("catv00003333",),
        dia=("frescos/fiambres-y-embutidos/fiambres-feteados",
             "frescos/fiambres-y-embutidos/salames-y-longanizas"),
        carrefour=("lacteos-y-productos-frescos/fiambres",),
        vea=("quesos-y-fiambres/fiambres",),
    ),
    _shelf(
        "salchichas", "Salchichas", "Frescos",
        coto=("catv00001521",),
        # Día (oct-2026) junta salchichas con patés, picadillo y leberwurst en una
        # sola hoja (`frescos/fiambres-y-embutidos/salchichas-y-pates`): archivarla
        # acá dejaría al optimizador ofrecer un leberwurst de 200 g por salchichas.
        dia=(),
        carrefour=("lacteos-y-productos-frescos/salchichas",),
        vea=("quesos-y-fiambres/salchichas",),
    ),
    _shelf(
        "pastas-frescas", "Pastas frescas", "Frescos",
        coto=("catv00001864", "catv00001869"),
        dia=("frescos/pastas-y-masas/pastas-frescas",
             "frescos/pastas-y-masas/pastas-rellenas-frescas",
             "frescos/pastas-y-masas/noquis",
             "frescos/pastas-y-masas/tapas-de-empanada-y-pascualina"),
        carrefour=("lacteos-y-productos-frescos/tapas-y-pastas-frescas",),
        vea=(
            "lacteos/pastas-y-tapas/fideos-y-noquis",
            "lacteos/pastas-y-tapas/pastas-rellenas",
            "lacteos/pastas-y-tapas/tapas",
            "pastas-frescas/simples",
        ),
    ),

    # ---------------------------------------------------------------- Bebidas
    _shelf(
        "jugos", "Jugos", "Bebidas",
        coto=("catv00001542",),
        dia=("bebidas/jugos-y-energizantes/jugos-listos-y-concentrados",
             "bebidas/jugos-y-energizantes/jugos-en-polvo",
             "bebidas/jugos-y-energizantes/jugos-naturales"),
        carrefour=("bebidas/jugos",),
        vea=("bebidas/jugos",),
    ),
    _shelf(
        "energizantes-e-isotonicas", "Energizantes e isotónicas", "Bebidas",
        coto=("catv00001539", "catv00002071"),
        dia=("bebidas/jugos-y-energizantes/bebidas-deportivas",
             "bebidas/jugos-y-energizantes/energizantes"),
        carrefour=("bebidas/bebidas-energizantes", "bebidas/bebidas-isotonicas"),
        vea=("bebidas/energizantes", "bebidas/isotonicas"),
    ),
    _shelf(
        "cervezas", "Cervezas", "Bebidas",
        coto=("catv00001527",),
        dia=("bebidas/cervezas",),
        carrefour=("bebidas/cervezas",),
        vea=("bebidas/cervezas",),
    ),
    _shelf(
        "vinos", "Vinos", "Bebidas",
        coto=("catv00001532",),
        # Las hojas de `bebidas/bodega`: ese nivel 2 también tiene espumantes y
        # sidras, que son la góndola de abajo.
        dia=("bebidas/bodega/vino-tinto", "bebidas/bodega/vinos-blancos-y-dulces",
             "bebidas/bodega/vino-rosado"),
        carrefour=("bebidas/vinos",),
        vea=("bebidas/vinos",),
    ),
    _shelf(
        "espumantes-y-sidras", "Espumantes y sidras", "Bebidas",
        coto=("catv00001528", "catv00001543"),
        dia=("bebidas/bodega/espumantes", "bebidas/bodega/sidras"),
        carrefour=("bebidas/espumantes-y-sidras",),
        vea=("bebidas/espumantes", "bebidas/sidras"),
    ),
    _shelf(
        "aperitivos-y-licores", "Aperitivos y licores", "Bebidas",
        coto=("catv00001524", "catv00001529", "catv00001525"),
        dia=("bebidas/aperitivos-y-destilados",),
        carrefour=("bebidas/fernet-y-aperitivos", "bebidas/bebidas-blancas"),
        vea=("bebidas/aperitivos", "bebidas/bebidas-blancas", "bebidas/licores", "bebidas/whiskys"),
    ),

    # ------------------------------------------------------------- Congelados
    _shelf(
        "papas-congeladas", "Papas congeladas", "Congelados",
        coto=("catv00003195", "catv00003194", "catv00003197", "catv00003196",
              "catv00003193"),
        dia=("congelados/vegetales-frutas-y-papas/papas-fritas-congeladas",),
        carrefour=("congelados/papas",),
        vea=("congelados/papas",),
    ),
    _shelf(
        "hamburguesas-congeladas", "Hamburguesas y milanesas", "Congelados",
        coto=("catv00003159", "catv00003149"),
        # Día movió las hamburguesas a `comidas-preparadas-y-rebozados` y dejó el
        # nodo viejo con 1 producto: se barren los dos para no perder ese uno.
        dia=("congelados/comidas-preparadas-y-rebozados/hamburguesas-y-milanesas",
             "congelados/hamburguesas-y-medallones"),
        carrefour=("congelados/hamburguesas-y-medallones",),
        vea=("congelados/hamburguesas-y-milanesas",),
    ),
    _shelf(
        "rebozados-congelados", "Nuggets y rebozados", "Congelados",
        coto=("catv00003172", "catv00004513", "catv00004514", "catv00004516",
              "catv00004515"),
        dia=("congelados/comidas-preparadas-y-rebozados/nuggets-patitas-y-bocaditos",
             "congelados/comidas-preparadas-y-rebozados/opciones-veganas-y-vegetarianas"),
        carrefour=("congelados/nuggets-y-rebozados",),
        vea=("congelados/pollo-y-carnes",),
    ),
    _shelf(
        "vegetales-congelados", "Vegetales congelados", "Congelados",
        coto=("catv00003162", "catv00003169", "catv00003161", "catv00003173",
              "catv00003163", "catv00003166", "catv00003209", "catv00005477",
              "catv00005480"),
        dia=("congelados/vegetales-frutas-y-papas/vegetales-congelados",),
        # El nivel 2 y no la hoja `vegetales-congelados`: la hoja devuelve 0 en
        # vivo aunque exista en el árbol (mismo caso que los yogures de Día), y el
        # padre trae 24. Cuesta que entre también algo de fruta congelada.
        carrefour=("congelados/frutas-y-vegetales-congelados",),
        vea=("congelados/vegetales",),
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
        dia=("congelados/comidas-preparadas-y-rebozados/pizzas-empanadas-y-panes",),
        carrefour=("congelados/comidas-y-panificados",),
        vea=("congelados/comidas-congeladas",),
    ),
    _shelf(
        "pescados-congelados", "Pescados congelados", "Congelados",
        coto=("catv00004499", "catv00004501", "catv00004500"),
        dia=("congelados/pescaderia-congelada",),
        carrefour=("congelados/pescados-y-mariscos",),
        vea=("congelados/pescados-y-mariscos",),
    ),
    _shelf(
        # Entró tarde: en el segundo tramo Carrefour devolvía 0. Su catálogo
        # público tiene ~27 helados en este nodo, pero el listado filtra los sin
        # stock (`hideUnavailableItems`) y a fin de invierno quedaba 1: es
        # estacional, no una rama distinta. En invierno esta clave puede volver a
        # cero y pintar el barrido de PARTIAL por categoría vacía — es la señal
        # funcionando, no un bug.
        "helados", "Helados", "Congelados",
        coto=("catv00003247", "catv00003248", "catv00003147", "catv00003183"),
        dia=("congelados/helados-y-postres",),
        carrefour=("congelados/helados-y-postres",),
        vea=("congelados/helados-y-postres",),
    ),

    # ------------------------------------------------ Frutas, verduras y carnes
    # Sin EAN que unifique: ver `src/fresh_items.py`. Vaca y cerdo comparten
    # góndola porque Coto los mezcla en una sola hoja (`catv00001460` trae
    # "Asado De Cerdo" junto al bife); separarlos inventaría una jerarquía que
    # Coto no tiene.
    _shelf(
        "frutas", "Frutas", "Frutas y verduras",
        coto=("catv00003286",),
        dia=("frutas-y-verduras/frutas/frutas-de-estacion-y-citricos",
             "frutas-y-verduras/frutas/otras-frutas"),
        carrefour=("frutas-y-verduras/frutas",),
        vea=("frutas-y-verduras/frutas/frutas-empaquetadas", "frutas-y-verduras/frutas/frutas-sueltas"),
    ),
    _shelf(
        "verduras", "Verduras", "Frutas y verduras",
        coto=("catv00003308",),
        dia=("frutas-y-verduras/verduras",),
        carrefour=("frutas-y-verduras/verduras",),
        vea=("frutas-y-verduras/verduras",),
    ),
    _shelf(
        "carnes", "Carne de vaca y cerdo", "Carnes",
        coto=("catv00001460",),
        dia=("carniceria/carne-vacuna", "carniceria/carne-de-cerdo"),
        carrefour=("carnes-y-pescados/carne-vacuna", "carnes-y-pescados/carne-de-cerdo"),
        vea=("carnes/carne-vacuna", "carnes/carne-de-cerdo"),
    ),
    _shelf(
        "pollo", "Pollo", "Carnes",
        coto=("catv00005187", "catv00005189"),
        dia=("carniceria/pollo-y-aves",),
        carrefour=("carnes-y-pescados/pollo-y-granja",),
        vea=("carnes/pollos/pollos",),
    ),

    # --------------------------------------------------------------- Limpieza
    # La primera sección que no es comida. Mismo criterio que el resto: marcas
    # envasadas con EAN, que es donde las tres cadenas coinciden. Quedan afuera
    # a propósito dos nodos de Día que mezclan otra góndola en la misma hoja:
    # `servilletas-y-panuelos` (pañuelos no es servilleta) y
    # `jabon-en-barra-y-aprestos` (un apresto no reemplaza a un jabón). Guardarlos
    # acá habilitaría al optimizador a ofrecer uno como sustituto del otro.
    _shelf(
        "papel-higienico", "Papel higiénico", "Limpieza",
        coto=("catv00003018",),
        dia=("limpieza/papeleria-y-descartables/papel-higienico",),
        carrefour=("limpieza/papeles-higienicos",),
        vea=("limpieza/papeles/papel-higienico",),
    ),
    _shelf(
        "rollos-y-servilletas", "Rollos de cocina y servilletas", "Limpieza",
        coto=("catv00003020", "catv00003021"),
        dia=("limpieza/papeleria-y-descartables/rollos-de-cocina",),
        carrefour=("limpieza/rollos-de-cocina-y-servilletas",),
        vea=("limpieza/papeles/rollos-de-cocina", "limpieza/papeles/servilletas"),
    ),
    _shelf(
        "detergente", "Detergente", "Limpieza",
        coto=("catv00003043",),
        dia=("limpieza/cocina-y-vajilla/detergentes",),
        carrefour=("limpieza/limpieza-de-cocina/detergentes",),
        vea=("limpieza/limpieza-de-cocina/detergentes",),
    ),
    _shelf(
        "jabon-para-ropa", "Jabón para la ropa", "Limpieza",
        coto=("catv00003026", "catv00005372", "catv00002756"),
        dia=("limpieza/ropa-y-lavado/jabon-en-polvo",
             "limpieza/ropa-y-lavado/jabon-liquido"),
        carrefour=("limpieza/limpieza-de-la-ropa/jabones-para-la-ropa",),
        vea=("limpieza/cuidado-para-la-ropa/detergente-para-ropa",),
    ),
    _shelf(
        "suavizantes", "Suavizantes", "Limpieza",
        coto=("catv00003027",),
        dia=("limpieza/ropa-y-lavado/suavizantes",),
        carrefour=("limpieza/limpieza-de-la-ropa/suavizantes-para-la-ropa",),
        vea=("limpieza/cuidado-para-la-ropa/suavizantes",),
    ),
    _shelf(
        "lavandina", "Lavandina", "Limpieza",
        coto=("catv00004753", "catv00004754"),
        dia=("limpieza/banos-pisos-y-superficies/lavandinas",),
        carrefour=("limpieza/lavandinas",),
        vea=("limpieza/lavandina",),
    ),

    # ------------------------------------------------------------- Perfumería
    # Higiene y cuidado personal de marca: el mismo Dove, Colgate o Rexona en las
    # tres cadenas, que es donde el EAN coincide. Cada clave se midió contra el
    # endpoint en vivo (sep-2026) y todas devolvieron productos de su góndola.
    # Quedan afuera a propósito: perfumes/colonias y maquillaje (Día no tiene un
    # nodo equivalente, así que no habría con qué comparar), pañales (cada cadena
    # los archiva en una sección de bebé distinta) y medicamentos.
    _shelf(
        "shampoo", "Shampoo", "Perfumería",
        # `catv00001589` es "Shampoo + Acondicionador" (1 producto): Día y
        # Carrefour archivan los 2 en 1 bajo shampoo.
        coto=("catv00001587", "catv00001589"),
        dia=("perfumeria/cuidado-del-pelo/shampoo",),
        carrefour=("perfumeria-y-farmacia/cuidado-del-cabello/shampoos",),
        vea=("perfumeria/cuidado-capilar/shampoo",),
    ),
    _shelf(
        "acondicionadores", "Acondicionadores", "Perfumería",
        coto=("catv00001590",),
        dia=("perfumeria/cuidado-del-pelo/acondicionadores",),
        carrefour=("perfumeria-y-farmacia/cuidado-del-cabello/acondicionadores",),
        vea=("perfumeria/cuidado-capilar/acondicionador",),
    ),
    _shelf(
        "coloracion", "Coloración", "Perfumería",
        coto=("catv00003481",),
        dia=("perfumeria/cuidado-del-pelo/coloracion",),
        carrefour=("perfumeria-y-farmacia/cuidado-del-cabello/coloracion",),
        vea=("perfumeria/cuidado-capilar/coloracion",),
    ),
    _shelf(
        # Día separa por género y Carrefour por formato; Coto, desodorante de
        # antitranspirante. Ninguno de los tres cortes es un estante distinto
        # para quien compra, así que la góndola es la unión.
        "desodorantes", "Desodorantes", "Perfumería",
        coto=("catv00003497", "catv00003498"),
        dia=("perfumeria/cuidado-corporal-y-bano/desodorantes-y-antitranspirantes",),
        carrefour=("perfumeria-y-farmacia/antitranspirantes-y-desodorantes/en-aerosol",
                   "perfumeria-y-farmacia/antitranspirantes-y-desodorantes/en-barra-y-roll-on"),
        vea=(
            "perfumeria/cuidado-personal/desodorantes-de-hombres",
            "perfumeria/cuidado-personal/desodorantes-de-mujer",
        ),
    ),
    _shelf(
        # En barra y líquidos juntos porque Coto los mezcla en una sola hoja.
        # Las hojas de Carrefour y no su nivel 2: éste trae además esponjas.
        "jabones", "Jabones de tocador", "Perfumería",
        coto=("catv00001576",),
        dia=("perfumeria/cuidado-corporal-y-bano/jabones-en-barra",
             "perfumeria/cuidado-corporal-y-bano/jabones-liquidos-y-geles"),
        carrefour=("perfumeria-y-farmacia/jabones/jabones-liquidos",
                   "perfumeria-y-farmacia/jabones/jabones-en-barra"),
        vea=("perfumeria/cuidado-personal/jabones",),
    ),
    _shelf(
        "pasta-dental", "Pasta dental", "Perfumería",
        coto=("catv00003508",),
        dia=("perfumeria/cuidado-bucal/pastas-dentales",),
        carrefour=("perfumeria-y-farmacia/cuidado-dental/pasta-dental",),
        vea=("perfumeria/cuidado-oral/pastas-dentales",),
    ),
    _shelf(
        "cepillos-de-dientes", "Cepillos de dientes", "Perfumería",
        coto=("catv00003507",),
        dia=("perfumeria/cuidado-bucal/cepillos-de-dientes",),
        carrefour=("perfumeria-y-farmacia/cuidado-dental/cepillos-de-dientes",),
        vea=("perfumeria/cuidado-oral/cepillos-dentales",),
    ),
    _shelf(
        "enjuague-bucal", "Enjuague bucal", "Perfumería",
        coto=("catv00003505",),
        dia=("perfumeria/cuidado-bucal/enjuagues-bucal",),
        carrefour=("perfumeria-y-farmacia/cuidado-dental/enjuagues-bucales",),
        vea=("perfumeria/cuidado-oral/enjuagues-bucales",),
    ),
    # Vea (`vea=()` en estas tres filas) tiene una sola hoja de protección
    # femenina que mezcla toallitas, protectores y tampones, y su árbol no baja
    # a un cuarto nivel. Archivarla en una góndola dejaría al optimizador
    # ofrecer un tampón por una toallita; mismo criterio que con las hojas
    # mixtas de Día en Limpieza.
    _shelf(
        "toallitas-femeninas", "Toallitas femeninas", "Perfumería",
        coto=("catv00003496",),
        dia=("perfumeria/proteccion-femenina/toallitas-femeninas",),
        carrefour=("perfumeria-y-farmacia/proteccion-femenina/toallitas-femeninas",),
        vea=(),
    ),
    _shelf(
        "protectores-diarios", "Protectores diarios", "Perfumería",
        coto=("catv00003494",),
        dia=("perfumeria/proteccion-femenina/protectores-diarios",),
        carrefour=("perfumeria-y-farmacia/proteccion-femenina/protectores-diarios",),
        vea=(),
    ),
    _shelf(
        "tampones", "Tampones", "Perfumería",
        coto=("catv00003495",),
        dia=("perfumeria/proteccion-femenina/tampones",),
        carrefour=("perfumeria-y-farmacia/proteccion-femenina/tampones",),
        vea=(),
    ),
    _shelf(
        # Máquinas, repuestos y espumas juntos: Coto no los separa. El nivel 2
        # de Día sí se puede usar entero porque ninguna otra clave vive abajo.
        "afeitado", "Afeitado", "Perfumería",
        coto=("catv00001548",),
        dia=("perfumeria/afeitado-y-depilacion/maquinas-y-repuestos-de-afeitar",),
        carrefour=("perfumeria-y-farmacia/cuidado-corporal/afeitado",),
        vea=("perfumeria/cuidado-personal/productos-para-afeitarse",),
    ),
    _shelf(
        "cremas-corporales", "Cremas corporales", "Perfumería",
        coto=("catv00001564",),
        # Día (oct-2026) mezcla perfumes y body splash con las cremas en
        # `cuidado-corporal-y-bano/cremas-y-lociones-corporales`, y los perfumes
        # quedan fuera del catálogo a propósito: un perfume de 100 ml sería
        # reemplazo de una crema de 150 ml.
        dia=(),
        carrefour=("perfumeria-y-farmacia/cuidado-de-la-piel/cremas-corporales",),
        vea=("perfumeria/cuidado-de-la-piel/cremas-corporales",),
    ),
    _shelf(
        # Estacional como `helados`: a fin de invierno Día trae 8 y Carrefour
        # 22. Si alguna vuelve a cero pinta el barrido de PARTIAL por categoría
        # vacía, que es la señal funcionando. Post solar junto al protector
        # porque Día los tiene en una sola hoja.
        "proteccion-solar", "Protección solar", "Perfumería",
        coto=("catv00003516", "catv00003515"),
        dia=("perfumeria/cuidado-corporal-y-bano/proteccion-solar",),
        carrefour=("perfumeria-y-farmacia/cuidado-de-la-piel/proteccion-solar",),
        vea=("perfumeria/cuidado-de-la-piel/solares-y-post-solares",),
    ),
    _shelf(
        "algodon-e-hisopos", "Algodón e hisopos", "Perfumería",
        coto=("catv00003452", "catv00003447"),
        dia=("perfumeria/farmacia-y-botiquin/algodon-e-hisopos",),
        carrefour=("perfumeria-y-farmacia/algodones-e-hisopos",),
        vea=("perfumeria/farmacia/algodon",),
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
