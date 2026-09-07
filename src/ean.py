"""
Normalización del código de barras antes de que llegue al ingest.

El EAN es la clave de unificación de todo el proyecto (`unified_id = f"prod_{ean}"`),
así que es la única forma que tiene un producto de Coto de compararse contra el
mismo producto en Día o Carrefour. Este módulo existe por una falla concreta y
repetida: Coto publica en `product_main_ean` el **GTIN-14 de la caja** en vez del
EAN-13 de la unidad de consumo, y `unified_products.ean` es VARCHAR(13). Como
`save_store_products` corre la categoría entera en una transacción, esas cinco
filas de más revertían las 80 de la góndola `catv00003603` ("Gomitas y Gelatinas")
todas las noches, con el barrido en PARTIAL y la góndola vacía en la base:

    catv00003603: StringDataRightTruncation: value too long for
                  type character varying(13)

Dos reglas, y las dos son deliberadas:

1. **Un código de 13 caracteres o menos se devuelve tal cual, sin validar nada.**
   La base tiene hoy 162 EAN de 8 dígitos, 105 de 11, 281 de 12 y 1 de 10: son UPC
   con los ceros a la izquierda comidos, y las tres cadenas los comen igual —
   ninguno colisiona con un EAN de 13 al zero-paddearlo, y los mismos largos cortos
   aparecen en Coto y en Carrefour, o sea que hoy unifican bien entre sí. Validar
   check digits acá le cambiaría el `unified_id` a cientos de productos, y el
   barrido de huérfanos borraría las filas viejas esa misma noche. Lo único que se
   toca es el caso que rompe: largo > 13.

2. **Un GTIN-14 válido se convierte al GTIN-13 que contiene**, no se guarda crudo
   ni se descarta. Guardarlo crudo (ensanchando la columna) lo dejaría conviviendo
   con el EAN-13 del mismo producto en otra cadena sin unificar nunca — un
   duplicado silencioso, la misma clase de agujero que ya costó el
   `unified_product_id` congelado. La conversión no es una heurística: es la
   derivación GS1 estándar (sacar el dígito indicador de empaque, recalcular el
   check digit sobre los 12 restantes), y se aplica SÓLO si el check digit del 14
   valida. Un 14 que no valida no es un GTIN-14 mal interpretado, es un dato que no
   sabemos leer, y ahí la respuesta correcta es None.

`None` no pierde el producto: `save_store_products` cae a
`unified_id = f"{store_id}_{store_sku}"`, así que entra al catálogo como oferta de
una sola tienda. Es la asimetría de siempre — no unificar cuesta una comparación,
unificar mal rompe la promesa del proyecto.
"""
import logging

logger = logging.getLogger(__name__)

# El largo de `unified_products.ean` (src/schema.py). Todo lo que lo exceda hay
# que resolverlo acá o explota en el INSERT, arrastrando la categoría entera.
MAX_EAN_LEN = 13


def _check_digit(body: str) -> str:
    """
    Check digit mod-10 de GS1 sobre el cuerpo de un código, sin su último dígito.

    Los pesos 3/1 se asignan DESDE LA DERECHA (el dígito más a la derecha del
    cuerpo pesa 3), que es lo que hace que la misma función sirva para EAN-13 y
    para GTIN-14 sin un caso especial por largo. Verificado contra datos reales:
    "789645190938" -> 1 (el EAN-13 7896451909381) y "7789645190938" -> 0, que es
    el último dígito del GTIN-14 77896451909380 que publica Coto.
    """
    total = sum(
        int(d) * (3 if i % 2 == 0 else 1)
        for i, d in enumerate(reversed(body))
    )
    return str((10 - total % 10) % 10)


def normalize_ean(raw) -> str | None:
    """
    Devuelve el EAN listo para persistir, o None si no hay uno usable.

    Se llama desde los scrapers y no desde `save_store_products` por la misma razón
    que `size_parser.normalize_magnitude()`: el scraper normaliza a la forma que el
    ingest exige, y el ingest sigue exigiendo con `prod['...']` en vez de reparar
    en silencio lo que le mandan.
    """
    if raw is None:
        return None

    code = str(raw).strip()
    if not code:
        return None

    if len(code) <= MAX_EAN_LEN:
        # Ver la regla 1 del docstring del módulo: acá NO se valida.
        return code

    if len(code) == 14 and code.isdigit() and _check_digit(code[:13]) == code[13]:
        base = code[1:13]
        return base + _check_digit(base)

    logger.warning(
        "EAN descartado por no ser convertible a %d caracteres: %r. "
        "El producto entra sin unificar, con su unified_id por tienda.",
        MAX_EAN_LEN, code,
    )
    return None
