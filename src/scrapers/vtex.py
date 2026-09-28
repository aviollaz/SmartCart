# src/scrapers/vtex.py
"""
Lo que Día y Carrefour comparten por correr sobre la misma plataforma.

Las dos tiendas le pegan a la misma operación `productSearchV3` de VTEX con la
misma persisted query, así que la lectura de la respuesta es idéntica y vivía
duplicada a medias: Carrefour tenía la validación y Día no tenía ninguna. Lo
mismo pasaba con el parseo de cada producto (`parse_vtex_offer` más abajo):
las dos tiendas repetían ~70 líneas prácticamente idénticas, con el riesgo de
que un fix a una (un nuevo caso de `unit_type`, un ajuste al parser dietario)
se aplicara a una copia y no a la otra.
"""
import html
import logging
import re
from urllib.parse import urlsplit

from src.dietary_parser import detect_dietary_flags
from src.ean import normalize_ean
from src.scrapers.errors import CategoryScrapeError
from src.size_parser import extract_real_volume, normalize_magnitude

logger = logging.getLogger(__name__)

# La plantilla con la que Carrefour rellena la descripción de su marca propia
# ("✅ Características Destacadas ✔️ Producto de la línea Carrefour, pensado para
# tus necesidades diarias. ✔️ Presentación: formato práctico..."). Es idéntica
# para un aceite y para unas formitas de merluza: no describe nada, y mostrarla
# en la ficha sería ruido con apariencia de dato.
_TEMPLATE_MARKERS = ("producto de la línea carrefour, pensado para tus necesidades",)

_TAG = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"\s+")
_ALNUM = re.compile(r"[^0-9a-záéíóúñü]+")


def clean_description(raw, name) -> str | None:
    """
    La `description` de VTEX lista para mostrar, o None si no aporta nada.

    Se guarda para la ficha del producto, **nunca** como evidencia dietaria: es
    copy de marketing y a veces habla de productos hermanos (ver el comentario de
    `dietary_sources` en `parse_vtex_offer`). Medido sobre 97 productos de las dos
    tiendas, ~41% trae texto; de eso, lo que no sirve tiene tres formas, y las
    tres se descartan acá:

      * la plantilla de marca propia de Carrefour (`_TEMPLATE_MARKERS`),
      * HTML sin texto (una descripción que es sólo un `<img>`),
      * el nombre del producto repetido ("NESTLE Chocotrio Pasta de maní x 90g").

    El HTML se aplana a texto plano en vez de guardarse: el frontend lo muestra
    como texto, y renderizar HTML de un tercero sería abrirle la puerta a lo que
    ese tercero quiera inyectar.
    """
    if not raw or not isinstance(raw, str):
        return None

    texto = html.unescape(_TAG.sub(" ", raw))
    texto = _SPACES.sub(" ", texto).strip().strip('"').strip()
    if not texto:
        return None

    bajo = texto.lower()
    if any(marca in bajo for marca in _TEMPLATE_MARKERS):
        return None

    if name:
        solo_texto = _ALNUM.sub("", bajo)
        solo_nombre = _ALNUM.sub("", str(name).lower())
        # "Es el nombre": o idéntico, o uno contiene al otro sin agregar casi
        # nada. Un texto largo que *empieza* con el nombre sí describe.
        if solo_texto and solo_nombre and (
            solo_texto == solo_nombre
            or (len(solo_texto) <= len(solo_nombre) + 8
                and (solo_nombre in solo_texto or solo_texto in solo_nombre))
        ):
            return None

    return texto


# El mensaje con que el gateway GraphQL de VTEX envuelve un 5xx (o 429) del
# servicio de búsqueda que tiene atrás, contestando igual HTTP 200.
_TRANSIENT_GRAPHQL_ERROR = re.compile(r"status code (429|5\d\d)\b")


def is_transient_graphql_error(response) -> bool:
    """
    True si la respuesta es un 200 cuyo `errors` describe SÓLO fallas pasajeras
    del backend de VTEX ("Request failed with status code 500/504").

    Es el predicado `is_retryable` de `request_with_retry`. Exige que **todos**
    los errores sean de ese tipo: un PERSISTED_QUERY_NOT_FOUND (hash rotado) no
    se arregla reintentando y tiene que llegar a `extract_search_payload` al
    primer intento, como siempre. Cualquier cosa que no se pueda leer como JSON
    devuelve False: decidir qué es ese error sigue siendo trabajo del llamador.
    """
    if response.status_code != 200:
        return False
    try:
        errors = response.json().get("errors")
    except Exception:
        return False
    if not errors or not isinstance(errors, list):
        return False
    return all(
        isinstance(err, dict) and _TRANSIENT_GRAPHQL_ERROR.search(str(err.get("message", "")))
        for err in errors
    )


def extract_search_payload(response_json, label: str) -> dict:
    """
    Devuelve el bloque `productSearch` de una respuesta de `productSearchV3`.

    LEVANTA `CategoryScrapeError` si la respuesta no es un resultado de búsqueda
    válido. No es paranoia: el `sha256Hash` de la persisted query está fijo y
    salió de una sesión del navegador, así que cuando la tienda lo rota GraphQL
    contesta **HTTP 200** con un array `errors` (PERSISTED_QUERY_NOT_FOUND) y sin
    `data`. Devolver `None` ahí —lo que hacía la versión anterior— terminaba en
    cero productos, que la regla de "página vacía = fin de categoría" lee como un
    barrido exitoso: la categoría se reportaba OK y el pruning borraba todo lo
    que no se alcanzó a recorrer.

    Una categoría realmente agotada NO pasa por acá: es un payload válido con
    `products: []`, y eso se devuelve normalmente. Esa es toda la distinción que
    este módulo existe para hacer.
    """
    if not isinstance(response_json, dict):
        raise CategoryScrapeError(
            f"[{label}] La respuesta no es un objeto JSON: {type(response_json).__name__}."
        )

    errors = response_json.get("errors")
    if errors:
        mensajes = "; ".join(
            str(err.get("message", err)) for err in errors if isinstance(err, dict)
        ) or str(errors)
        logger.error("[%s] La API devolvió errores de GraphQL: %s", label, mensajes)
        logger.error("[%s] Suele significar que el sha256Hash de la persisted query cambió.", label)
        raise CategoryScrapeError(f"[{label}] Errores de GraphQL: {mensajes}")

    data = response_json.get("data")
    if not isinstance(data, dict) or data.get("productSearch") is None:
        raise CategoryScrapeError(
            f"[{label}] Respuesta sin 'data.productSearch': no es un resultado de búsqueda válido."
        )

    return data["productSearch"]


def read_availability(first_item: dict) -> bool:
    """
    Disponibilidad declarada por VTEX para una oferta, con default seguro.

    Antes esto era un `"in_stock": True` literal en los dos scrapers. Medido
    contra el endpoint en vivo (Carrefour, 6 combinaciones de categoría y
    filtros), con los parámetros que el proyecto manda hoy
    —`hideUnavailableItems: True` + `skusFilter: "ALL_AVAILABLE"`— VTEX filtra
    lo agotado del lado del servidor y **todo** lo que vuelve trae
    `AvailableQuantity: 10000`. O sea que ese `True` no era una mentira: era
    verdad por construcción, y leer el campo hoy da exactamente lo mismo.

    Se lee igual, y el motivo es la trampa que dejaba montada. Con
    `hideUnavailableItems: False` la misma categoría devuelve 50 productos de
    los cuales **14 tienen `AvailableQuantity: 0`**. Aflojar ese filtro es un
    cambio de una palabra y una idea razonable (amplía el catálogo), y con el
    `True` hardcodeado habría marcado esas 14 filas como comprables sin que
    nada fallara. El flag pasa a decir lo que la tienda dijo.

    El default es `True` a propósito, no por optimismo: el `sha256Hash` de la
    persisted query fija el conjunto de campos del lado del servidor, así que
    si la tienda lo rota y `AvailableQuantity` desaparece, un default `False`
    marcaría el catálogo entero como agotado y el optimizador no podría armar
    ningún carrito. Ausencia significa "la tienda no dijo", y el proyecto ya
    resuelve esa clase de duda hacia el lado que no rompe.

    Ojo con lo que esto NO arregla: la disponibilidad de VTEX es la de la
    región por defecto, porque el pedido no manda `regionId` ni segment. Un
    producto puede volver disponible acá y que el checkout de la tienda diga
    "no tiene inventario para tu dirección" — que es exactamente lo que pasa.
    Eso es un ítem aparte en docs/TODO.md, no algo que este helper pueda ver.
    """
    for seller in first_item.get("sellers") or []:
        offer = seller.get("commertialOffer") or {}
        if "AvailableQuantity" in offer:
            try:
                return float(offer["AvailableQuantity"]) > 0
            except (TypeError, ValueError):
                return True

    return True


def storefront_url(link: str | None, base_url: str) -> str | None:
    """
    La URL pública de la ficha a partir del `link` de VTEX: su path (y query)
    sobre el dominio de la tienda, **ignorando el dominio que traiga**.

    Nunca se confía en el dominio del `link`. Carrefour lo manda relativo
    ("/aceite-123/p") y Día lo mandaba absoluto con su dominio público, hasta
    que VTEX empezó a devolver el interno (`diaio.vtexcommercestable.com.br`):
    ese dominio redirige al login del admin de VTEX ("confirm your identity"),
    así que todos los links de Día quedaron rotos sin que nada fallara. Es el
    segundo drift del mismo tipo — el primero rompió `get_dia_categories.py`
    con `diaio.myvtex.com`.
    """
    if not link:
        return None

    parts = urlsplit(link)
    path = "/" + parts.path.lstrip("/")
    query = f"?{parts.query}" if parts.query else ""
    return f"{base_url.rstrip('/')}{path}{query}"


def parse_vtex_offer(p: dict, shelf: str | None, taxonomy_path: str | None,
                      source_category: str | None, url: str | None) -> dict | None:
    """
    Convierte un producto crudo de `productSearchV3` en el dict que espera
    `SmartCartDB.save_store_products()`. Común a Día y Carrefour porque el JSON
    que devuelve VTEX para un producto es idéntico entre las dos — sólo cambia
    el dominio público de cada tienda, así que la `url` la arma el llamador con
    `storefront_url` y entra ya armada.

    Devuelve `None` cuando el producto no trae `items` (sin oferta, nada que
    guardar) — el llamador decide si eso es un `continue` o un error.
    """
    items = p.get("items", [])
    if not items:
        return None

    first_item = items[0]
    sellers = first_item.get("sellers", [])
    # `base_price` se resetea por producto: un producto sin sellers no debe
    # heredar en silencio el precio del anterior del lote.
    base_price = 0.0
    if sellers:
        commertial_offer = sellers[0].get("commertialOffer", {})
        base_price = float(commertial_offer.get("ListPrice", 0.0))

    precio_por_und = None
    unidad_medida = "un"

    # Buscar las properties en el JSON de VTEX
    for prop in p.get("properties", []):
        if prop.get("name") == "PrecioPorUnd" and prop.get("values"):
            precio_por_und = float(prop["values"][0])
        if prop.get("name") == "UnidaddeMedida" and prop.get("values"):
            unidad_medida = str(prop["values"][0]).lower()

    # Fuente primaria: parsear el tamaño real del nombre del producto
    # (ej. "250 Ml", "400 Gr") - la property VTEX "UnidaddeMedida" no siempre
    # viene informada y cae al genérico "un".
    total_volume_weight, unit_type = extract_real_volume(p.get("productName"))

    # Fallback: usar el precio por unidad de VTEX cuando el nombre no trae talla.
    if unit_type == "un" and base_price > 0 and precio_por_und is not None and precio_por_und > 0:
        total_volume_weight = round(base_price / precio_por_und, 3)

        # Estas dos ramas deciden la MAGNITUD: un cociente menor a 1 significa
        # que `precio_por_und` venía por litro/kilo y no por mililitro/gramo.
        # No tocarlas sin datos nuevos de VTEX.
        if "lt" in unidad_medida or "l" in unidad_medida:
            if total_volume_weight < 1.0:
                total_volume_weight = total_volume_weight * 1000
                unidad_medida = "ml"
        elif "kg" in unidad_medida:
            if total_volume_weight < 1.0:
                total_volume_weight = total_volume_weight * 1000
                unidad_medida = "g"

        # Y esto decide el VOCABULARIO, que es otra cosa. Sin esta llamada,
        # `unidad_medida` viajaba cruda desde la property de VTEX: un producto
        # en "gr" o en "kg" quedaba guardado con esa etiqueta y dejaba de ser
        # comparable contra las filas en "g", desapareciendo en silencio de las
        # sugerencias y de la heurística de cierre de tienda.
        total_volume_weight, unit_type = normalize_magnitude(
            total_volume_weight, unidad_medida
        )

    images = first_item.get("images", [])
    image_url = images[0].get("imageUrl") if images else None

    # Sólo fuentes que describen ESTE producto: nombre, marca, ruta de
    # categoría y los campos estructurados que la tienda le asigna (property
    # "Otros" suele traer "Sin Tacc"). `clusterHighlights` y `properties`
    # pueden no venir —la query es persisted, con hash fijo— así que se leen
    # de forma defensiva.
    #
    # `description`/`metaTagDescription` quedan EXCLUIDOS a propósito: son
    # copy de marketing de la marca y enumeran productos hermanos. El "Ketchup
    # Hellmann's Regular" traía "...mayonesa hellmann's light, clásica, suave,
    # vegana, oliva..." y se marcaba como vegano. Medido sobre 196 productos de
    # Día, el texto libre aportaba +5 detecciones de gluten y 1 sola de vegano,
    # que era justamente ese falso positivo.
    dietary_sources = [
        p.get("productName"),
        p.get("brand"),
        taxonomy_path,
        p.get("clusterHighlights"),
        [prop.get("values") for prop in p.get("properties", [])],
    ]
    is_gluten_free, is_vegan = detect_dietary_flags(*dietary_sources)

    return {
        "store_sku": p.get("productId"),
        # La categoría con la que se barrió: es lo que le permite al pruning
        # acotarse a las que terminaron bien.
        "source_category": source_category,
        # El SKU real de VTEX, que es lo que espera /checkout/cart/add?sku=.
        # En Día coincide con el productId; en Carrefour no (producto 100650 =
        # item 17305) — se guarda igual en los dos para no depender de esa
        # coincidencia.
        "store_item_id": first_item.get("itemId"),
        # Sin normalizar, esto pasaba el valor de VTEX crudo (ni siquiera
        # str()): la misma truncación que rompe a Coto, esperando un payload
        # distinto. Ver src/ean.py.
        "ean": normalize_ean(first_item.get("ean")),
        "name": p.get("productName"),
        "brand": p.get("brand"),
        # La góndola canónica: la única noción de categoría del proyecto (ver
        # src/shelves.py).
        "shelf": shelf,
        "url": url,
        "image_url": image_url,
        "base_price": base_price,
        "in_stock": read_availability(first_item),
        "total_volume_weight": total_volume_weight,
        "unit_type": unit_type,
        "is_gluten_free": is_gluten_free,
        "is_vegan": is_vegan,
        # Para mostrar en la ficha, no para decidir nada: ver clean_description().
        "description": clean_description(p.get("description"), p.get("productName")),
        # `{}` y no `[]`: viaja tal cual a `PromoTransformer.dia()`/`.carrefour()`,
        # que llaman `.get()` sobre esto. Día lo devolvía como `[]` cuando el
        # producto no tenía sellers, lo que reventaba esa llamada con
        # `AttributeError` en vez de simplemente no encontrar promociones.
        "raw_promos": sellers[0].get("commertialOffer", {}) if sellers else {},
    }
