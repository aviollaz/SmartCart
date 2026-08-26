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
SECTIONS = ("Almacén", "Frescos", "Desayuno y merienda", "Bebidas")


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
    _shelf(
        "arroz-y-legumbres", "Arroz y legumbres", "Almacén",
        coto=("catv00001279", "catv00001276"),
        dia=("almacen/pastas-y-arroce",),
        carrefour=("almacen/arroz-y-legumbres",),
    ),
    _shelf(
        "pastas-secas", "Pastas secas", "Almacén",
        coto=("catv00002794",),
        dia=("almacen/pastas-seca",),
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
        dia=("almacen/picadas",),
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
        dia=("frescos/lacteos/yogures-enteros",
             "frescos/lacteos/yogures-descremados"),
        carrefour=("lacteos-y-productos-frescos/yogures",),
    ),
    _shelf(
        "quesos", "Quesos", "Frescos",
        coto=("catv00003273", "catv00003803"),
        dia=("frescos/fiambreria",),
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
        carrefour=("desayuno-y-merienda/mermeladas-y-otros-dulces",),
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
