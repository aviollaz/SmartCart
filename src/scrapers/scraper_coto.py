import httpx
import logging
import re
import time
import random

from src.dietary_parser import detect_dietary_flags
from src.ean import normalize_ean
from src.scrapers.errors import CategoryScrapeError
from src.shelves import keys_for_store, shelf_for_key
from src.taxonomy import category_path
from src.size_parser import extract_real_volume, normalize_magnitude

logger = logging.getLogger(__name__)


# Las góndolas que se barren viven en src/shelves.py, alineadas con las de Día y
# Carrefour: el catálogo sólo sirve para comparar precios si las tres tiendas
# barrieron el mismo estante. Ampliar es agregar una fila allá, no una lista acá.
MVP_CATEGORIES = keys_for_store("coto")

# Tope duro de páginas por categoría. Es una red de seguridad, no el criterio de
# corte: el corte real es la página sin resultados. Si el endpoint dejara de
# respetar el `page` y devolviera siempre el mismo tramo, sin este tope el
# barrido no termina nunca — y bajo cron eso se come la ventana entera del
# watchdog y deja el lock tomado para el día siguiente. Mismo rol que el
# MAX_PAGES de scraper_carrefour.py.
MAX_PAGES = 60


def _as_price(value) -> float:
    """
    Precio de Coto como float, tolerando lo que el payload manda de verdad.

    `float(d.get("formatPrice", 0))` no alcanza: la clave EXISTE con valor
    `null` en parte del catálogo, así que el default nunca se aplica y el
    `float(None)` levanta TypeError. Eso no se veía con 5 categorías, y cuando
    aparece rompe de la peor forma posible — el `except` del bucle de páginas lo
    atrapa y hace `break`, así que la categoría termina temprano con los
    productos que alcanzó a juntar y se reporta como exitosa. Un precio ausente
    es 0.0, que es lo que el resto del código ya sabe interpretar.
    """
    if value is None:
        return 0.0

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def build_coto_url(value: str, product_id: str) -> str | None:
    """
    Arma la URL pública de una ficha de producto de Coto.

    El campo `url` que devuelve la API es un fragmento relativo sin barra
    inicial ("_/R-00539894-00539894-200"), así que concatenarlo al dominio
    producía links rotos del tipo "https://www.cotodigital.com.ar_/R-...".

    Formato real: el slug es decorativo y lo que resuelve la página es el
    código R-. Ej. ("Paleta Cocida Feteada Paladini Xkg", "00307037") ->
    https://www.coto.com.ar/productos/paleta-cocida-feteada-paladini-xkg-/_/R-00307037-00307037-200
    """
    if not value or not product_id:
        return None

    slug = value.lower().replace(" ", "-") + "-"
    return f"https://www.coto.com.ar/productos/{slug}/_/R-{product_id}-{product_id}-200"


def resolve_coto_product_id(item: dict, prod_data: dict) -> str | None:
    """
    Obtiene el id numérico que va en el código R- de la URL.

    Se resuelve en cascada porque no hay un fixture del payload de Coto en el
    repo para confirmar dónde vive el `id`. Los tres caminos rinden el mismo
    número: el sku_id es el id con el prefijo "sku" (sku00539894 -> 00539894),
    y el `url` viejo ya traía el código R- armado.
    """
    raw_id = item.get("id")
    if raw_id:
        return str(raw_id)

    sku_id = prod_data.get("sku_id")
    if sku_id:
        return str(sku_id).removeprefix("sku")

    legacy_url = prod_data.get("url") or ""
    match = re.search(r"R-(\d+)-", legacy_url)
    return match.group(1) if match else None


class CotoScraper:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:152.0) Gecko/20100101 Firefox/152.0",
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://www.cotodigital.com.ar",
            "Referer": "https://www.cotodigital.com.ar/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "cross-site",
            "Sec-GPC": "1"
        }
        self.client = httpx.Client(headers=self.headers, http2=True, timeout=15.0)
        
    def scrape_category(self, category_id: str):
        page = 1
        all_products = []
        seen_ids = set()

        # La góndola canónica de este id (src/shelves.py) es la categoría con la
        # que se guarda el producto: idéntica en las tres cadenas, que es lo que
        # hace comparables sus catálogos. La ruta de taxonomía se resuelve para
        # usarla como evidencia dietaria, no se persiste.
        shelf = shelf_for_key("coto", category_id)
        taxonomy_path = category_path("coto", category_id)

        for _ in range(MAX_PAGES):
            url = (
                f"https://api.coto.com.ar/api/v1/ms-digital-sitio-bff-web/api/v1/products/categories/{category_id}"
                f"?page={page}&key=key_r6xzz4IAoTWcipni&num_results_per_page=24"
                f"&pre_filter_expression=%7B%22name%22:%22store_availability%22,%22value%22:%22200%22%7D"
                f"&c=cio-fe-web-coto-3.5.2&i=5792d439-2540-4787-a25c-b6cf441f61c9&s=1"
                f"&origin_referrer=/sitios/cdigi/productos/categorias/{category_id}"
            )
            
            logger.info("[COTO] Extrayendo %s - Página %s...", category_id, page)
            
            try:
                response = self.client.get(url)
                
                if response.status_code != 200:
                    # Cortaba con `break`, que es indistinguible del final de la
                    # categoría: el mismo agujero que el `except` de más abajo ya
                    # había cerrado relanzando. Un 500 pasajero en la página 3
                    # dejaba la categoría con dos páginas, contada OK, y el
                    # pruning borraba el resto como discontinuado.
                    logger.error("[COTO] Error %s al intentar acceder a la página %s.",
                                 response.status_code, page)
                    raise CategoryScrapeError(
                        f"[COTO] HTTP {response.status_code} en la página {page} "
                        f"de '{category_id}'."
                    )
                    
                data = response.json()
                
                results = data.get("response", {}).get("results", [])
                
                if not results:
                    logger.info("[COTO] Final de la categoría %s alcanzado.", category_id)
                    break
                
                nuevos_en_pagina = 0
                for item in results:
                    prod_data = item.get("data", {})
                    
                    base_price = 0.0
                    format_price = 0.0
                    
                    prices_list = prod_data.get("price", [])
                    
                    if isinstance(prices_list, list):
                        for p_store in prices_list:
                            if p_store.get("store") == "200":
                                base_price = _as_price(p_store.get("listPrice"))
                                format_price = _as_price(p_store.get("formatPrice"))
                                break
                    
                    if base_price == 0.0:
                        base_price = _as_price(prod_data.get("product_list_price"))
                    
                    # Fuente primaria: parsear el tamaño real del nombre del producto
                    # (ej. "250 Ml", "400 Gr") - la metadata de la tienda
                    # (product_unit_of_measure) casi siempre viene genérica ("UNI").
                    total_volume_weight, unit_type = extract_real_volume(item.get("value"))

                    # Fallback: productos pesables sin tamaño en el nombre (ej. "Tomate x Kg"),
                    # estimado a partir del precio por formato de venta.
                    #
                    # `formatPrice` es el precio del formato de venta (el kilo),
                    # así que el cociente ya viene en kilos y normalize_magnitude
                    # lo pasa a gramos. Antes esto emitía 'kg' tal cual cuando el
                    # cociente daba >= 1, y una fila en 'kg' no es comparable
                    # contra ninguna en 'g': el producto desaparecía en silencio
                    # de las sugerencias y de la heurística de swaps.
                    if unit_type == "un" and base_price > 0 and format_price > 0:
                        total_volume_weight, unit_type = normalize_magnitude(
                            round(base_price / format_price, 3), "kg"
                        )

                    name = item.get("value")
                    brand = prod_data.get("product_brand")

                    # Coto no expone descripción ni atributos en este payload,
                    # así que la evidencia dietaria disponible es el nombre,
                    # la marca y la ruta de categoría.
                    is_gluten_free, is_vegan = detect_dietary_flags(name, brand, taxonomy_path)

                    product = {
                        "store_sku": prod_data.get("sku_id"),
                        # La categoría con la que se barrió: es lo que le permite
                        # al pruning acotarse a las que terminaron bien.
                        "source_category": category_id,
                        # Coto publica acá el GTIN-14 de la caja en parte del
                        # catálogo, contra una columna de 13: cinco filas así
                        # revertían la categoría entera. Ver src/ean.py.
                        "ean": normalize_ean(prod_data.get("product_main_ean")),
                        "name": name,
                        "brand": brand,
                        # La góndola canónica: la única noción de categoría del
                        # proyecto (ver src/shelves.py).
                        "shelf": shelf,
                        "url": build_coto_url(name, resolve_coto_product_id(item, prod_data)),
                        "image_url": prod_data.get("image_url"),
                        "base_price": base_price,
                        "in_stock": prod_data.get("in_stock", True),
                        "total_volume_weight": total_volume_weight,
                        "unit_type": unit_type,
                        "is_gluten_free": is_gluten_free,
                        "is_vegan": is_vegan,
                        "raw_promos": prod_data.get("discounts", [])
                    }
                    # Sólo los nuevos: si el endpoint repite un tramo, guardar el
                    # duplicado no corrompe nada (el upsert es por store_sku) pero
                    # infla el conteo que reporta el barrido.
                    if product["store_sku"] in seen_ids:
                        continue
                    seen_ids.add(product["store_sku"])
                    nuevos_en_pagina += 1
                    all_products.append(product)
                
                if not nuevos_en_pagina:
                    # El endpoint dejó de respetar el `page`: no sabemos qué parte
                    # de la categoría falta, así que es un fallo, no un final.
                    raise CategoryScrapeError(
                        f"[COTO] La página {page} de '{category_id}' repite productos "
                        f"ya vistos: la paginación dejó de avanzar."
                    )

                time.sleep(random.uniform(1.5, 3.0))
                page += 1
                
            except CategoryScrapeError:
                # Ya trae su propio diagnóstico; sube tal cual.
                raise
            except Exception:
                # Se relanza en vez de cortar en silencio. Tragarse la excepción
                # devolvía los productos juntados hasta ahí y `_run_store` la
                # contaba como categoría OK, así que un fallo a mitad del barrido
                # terminaba con `StoreRunResult.complete = True` y habilitaba el
                # pruning: todo lo que faltó recorrer parece discontinuado y se
                # borra. Perder la categoría entera es preferible a borrar
                # catálogo vivo; `_run_store` la marca fallida y sigue con la
                # siguiente, que es donde vive la tolerancia a fallos.
                logger.exception("[COTO] Ocurrió una excepción en la página %s.", page)
                raise
        else:
            # Agotar el tope significa que el corte por página sin resultados
            # nunca llegó: la categoría quedó recorrida a medias, y reportarla OK
            # habilitaría el pruning sobre un barrido trunco.
            raise CategoryScrapeError(
                f"[COTO] Se alcanzó el tope de {MAX_PAGES} páginas en '{category_id}' "
                f"sin llegar al final de la categoría."
            )

        return all_products

if __name__ == "__main__":
    from src.database import SmartCartDB

    # Corriendo standalone nadie configuró el logging: sin esto, el progreso del
    # scrapeo (que ahora va por logger) no se ve. Bajo el orquestador este bloque
    # no corre y manda su configuración, que además escribe a archivo.
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    scraper = CotoScraper()
    db = SmartCartDB()
    
    print("\n--- INICIANDO PROCESO GLOBAL SMARTCART ---")

    for cat_id in MVP_CATEGORIES:
        productos_recolectados = scraper.scrape_category(cat_id)
        
        if productos_recolectados:
            db.save_store_products(productos_recolectados, "coto_online")
            
        print(f"--- FIN DE CATEGORÍA {cat_id} ---\n")
        time.sleep(2.0)