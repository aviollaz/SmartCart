# src/shelves.py
"""
Las góndolas que se scrapean, alineadas entre las tres tiendas.

Existe por una razón concreta: la unificación del catálogo es por EAN
(unified_id = "prod_" + ean), así que un producto sólo es comparable entre
tiendas si las tres barrieron *la misma góndola*. Tres listas `MVP_CATEGORIES`
independientes cumplían eso por casualidad y se desincronizaban en silencio —
nada falla cuando Coto scrapea yerba y Día no, simplemente el optimizador deja
de tener con qué comparar. Acá la alineación es la estructura del dato: una fila
por góndola, y las claves de las tres tiendas al lado.

Cada tienda aporta una LISTA de claves porque las tres taxonomías tienen
granularidad distinta. Coto sólo expone hojas de nivel 3 y muy finas ("Papas
Fritas", "Mani"), mientras que Día y Carrefour tienen nodos de nivel 2 que ya
agrupan el estante entero ("almacen/snacks"). Forzar una clave por tienda
obligaría a elegir entre no cubrir la góndola o inventar una jerarquía que la
tienda no tiene.

Sobre el tag canónico, ver `shelf_tags()`: es el diccionario de alias que
CLAUDE.md pide en la etapa 7 para el filtro de góndola.
"""
from src.category_tags import tags_for_category

STORES = ("coto", "dia", "carrefour")

# Góndola canónica -> {tienda: [claves de esa tienda]}.
#
# Las claves son las mismas con las que se indexa cada dump de taxonomía: id
# `catv…` en Coto, slug de URL en Día y Carrefour. Agregar una góndola es una
# fila; agregar una tienda a una góndola existente es una entrada en su dict.
#
# El criterio de selección fue producto ENVASADO DE MARCA: es donde el EAN
# coincide de verdad entre cadenas. La fruta suelta, la carnicería y la
# fiambrería al corte usan códigos internos por tienda y no unifican, así que
# barrerlas suma catálogo pero no suma comparaciones.
SHELVES: dict[str, dict[str, list[str]]] = {
    "aceites-y-aderezos": {
        "coto": ["catv00001264", "catv00002212"],
        "dia": ["almacen/aceites-y-aderezos"],
        "carrefour": ["almacen/aceites-y-vinagres",
                      "almacen/sal-aderezos-y-saborizadores"],
    },
    "harinas": {
        "coto": ["catv00001412", "catv00001411"],
        "dia": ["almacen/harinas"],
        "carrefour": ["almacen/harinas"],
    },
    "arroz-y-legumbres": {
        "coto": ["catv00001279", "catv00001276"],
        "dia": ["almacen/pastas-y-arroce"],
        "carrefour": ["almacen/arroz-y-legumbres"],
    },
    "pastas-secas": {
        "coto": ["catv00002794"],
        "dia": ["almacen/pastas-seca"],
        "carrefour": ["almacen/pastas-secas"],
    },
    "salsas-de-tomate": {
        "coto": ["catv00002933", "catv00002937"],
        "dia": ["almacen/conservas/tomates-y-salsas"],
        "carrefour": ["almacen/enlatados-y-conservas/conservas-y-salsas-de-tomate"],
    },
    "conservas-de-pescado": {
        "coto": ["catv00001401"],
        "dia": ["almacen/conservas/conservas-de-pescados"],
        "carrefour": ["almacen/enlatados-y-conservas/conservas-de-pescado"],
    },
    "snacks": {
        "coto": ["catv00003639", "catv00003636"],
        "dia": ["almacen/picadas"],
        "carrefour": ["almacen/snacks"],
    },
    "leches": {
        "coto": ["catv00003266"],
        "dia": ["frescos/leches"],
        "carrefour": ["lacteos-y-productos-frescos/leches"],
    },
    "yogures": {
        "coto": ["catv00003251"],
        "dia": ["frescos/lacteos/yogures-enteros",
                "frescos/lacteos/yogures-descremados"],
        "carrefour": ["lacteos-y-productos-frescos/yogures"],
    },
    "quesos": {
        "coto": ["catv00003273", "catv00003803"],
        "dia": ["frescos/fiambreria"],
        "carrefour": ["lacteos-y-productos-frescos/quesos"],
    },
    "dulce-de-leche": {
        "coto": ["catv00003250"],
        "dia": ["desayuno/para-untar/dulces-de-leche"],
        "carrefour": ["desayuno-y-merienda/mermeladas-y-otros-dulces/dulce-de-leche"],
    },
    "mermeladas-y-miel": {
        "coto": ["catv00001408", "catv00001407"],
        "dia": ["desayuno/para-untar/mermeladas", "desayuno/para-untar/miel"],
        "carrefour": ["desayuno-y-merienda/mermeladas-y-otros-dulces"],
    },
    "galletitas": {
        "coto": ["catv00004082", "catv00003534"],
        "dia": ["desayuno/galletitas-y-cereales/galletitas-dulces",
                "desayuno/galletitas-y-cereales/galletitas-saladas"],
        "carrefour": ["desayuno-y-merienda/galletitas-bizcochitos-y-tostadas"],
    },
    "alfajores": {
        "coto": ["catv00003596"],
        "dia": ["almacen/golosinas-y-alfajores/alfajores"],
        "carrefour": ["desayuno-y-merienda/golosinas-y-chocolates/alfajores"],
    },
    "chocolates": {
        "coto": ["catv00003600", "catv00003606"],
        "dia": ["almacen/golosinas-y-alfajores/chocolates"],
        "carrefour": ["desayuno-y-merienda/golosinas-y-chocolates/chocolates"],
    },
    "cafe": {
        "coto": ["catv00001420"],
        "dia": ["desayuno/infusiones-y-endulzantes/cafe"],
        "carrefour": ["desayuno-y-merienda/cafe"],
    },
    "yerba-mate": {
        "coto": ["catv00001416"],
        "dia": ["desayuno/infusiones-y-endulzantes/yerba-mate"],
        "carrefour": ["desayuno-y-merienda/yerba"],
    },
    "azucar-y-endulzantes": {
        "coto": ["catv00002784", "catv00002785"],
        "dia": ["desayuno/infusiones-y-endulzantes/azucar",
                "desayuno/infusiones-y-endulzantes/edulcorantes"],
        "carrefour": ["desayuno-y-merienda/azucar-y-endulzantes"],
    },
    "gaseosas": {
        "coto": ["catv00001540"],
        "dia": ["bebidas/gaseosas"],
        "carrefour": ["bebidas/gaseosas"],
    },
    "aguas": {
        "coto": ["catv00004086"],
        "dia": ["bebidas/aguas"],
        "carrefour": ["bebidas/aguas"],
    },
}


def keys_for_store(store: str) -> list[str]:
    """
    Las claves de categoría que le tocan a una tienda, en el orden de la tabla.

    Es lo que consume `MVP_CATEGORIES` en cada scraper. Se deduplica preservando
    el orden por si dos góndolas comparten una clave: repetirla sólo gastaría un
    barrido entero para reescribir las mismas filas.
    """
    vistas: dict[str, None] = {}
    for gondola in SHELVES.values():
        for key in gondola.get(store, []):
            vistas.setdefault(key, None)
    return list(vistas)


def shelf_for_key(store: str, category_key: str) -> str | None:
    """La góndola canónica a la que pertenece una clave, o None si no está."""
    for shelf, gondola in SHELVES.items():
        if category_key in gondola.get(store, []):
            return shelf
    return None


def shelf_tags(store: str, category_key: str) -> list[str]:
    """
    Tags de un producto: su ruta en la taxonomía de la tienda MÁS el slug de la
    góndola canónica.

    El agregado es lo que hace utilizable la comparación entre tiendas. El
    filtro de misma góndola usa el operador de solapamiento de Postgres (`&&`)
    sobre `filter_tags()`, y cada cadena nombra distinto el mismo estante: la
    yerba es "Mate" en Coto, "Yerba mate" en Día y "Yerba" en Carrefour, así que
    los tres conjuntos no se tocan y el producto queda sin sustituto posible.
    Medido sobre esta tabla, sólo 7 de las 20 góndolas solapaban en los tres
    pares de tiendas; con el tag canónico solapan las 20 por construcción.

    Es el diccionario de alias que CLAUDE.md señala como la forma correcta de
    arreglo — y no aflojar el `&&` a un umbral de similaridad, que es lo que
    volvería a mezclar mayonesa con condimento para carne.

    El slug va al final y sólo si no está ya: para góndolas donde la hoja de la
    tienda ya coincide con el nombre canónico (`alfajores`, `leches`) duplicarlo
    no aporta nada.
    """
    tags = tags_for_category(store, category_key)

    shelf = shelf_for_key(store, category_key)
    if shelf and shelf not in tags:
        tags.append(shelf)

    return tags
