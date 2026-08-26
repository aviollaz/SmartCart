import httpx
import logging
import time
import random

from src.database import SmartCartDB
from src.dietary_parser import detect_dietary_flags
from src.scrapers.errors import CategoryScrapeError
from src.scrapers.vtex import extract_search_payload
from src.shelves import keys_for_store, shelf_for_key
from src.taxonomy import category_path
from src.size_parser import extract_real_volume, normalize_magnitude

logger = logging.getLogger(__name__)

# Carrefour corre sobre VTEX IO igual que Día, así que se le pega a la misma
# operación `productSearchV3` con persisted query. Se manda por POST con el JSON
# en el body en vez del GET con las variables en Base64 en la URL: es el mismo
# endpoint y evita tener que codificar/escapar el payload.
GRAPHQL_URL = "https://www.carrefour.com.ar/_v/segment/graphql/v1?workspace=master"

BASE_URL = "https://www.carrefour.com.ar"

# Las góndolas que se barren viven en src/shelves.py, alineadas con las de Coto y
# Día: el catálogo sólo sirve para comparar precios si las tres tiendas
# barrieron el mismo estante. Ampliar es agregar una fila allá, no una lista acá.
MVP_CATEGORIES = keys_for_store("carrefour")

# Tamaño de la grilla del sitio. VTEX pagina por índices absolutos [from, to].
PAGE_SIZE = 16

# Tope duro de páginas por categoría. Es una red de seguridad, no el criterio de
# corte: si el endpoint empezara a devolver siempre la misma página (o ignorara
# el `from`), el corte por "página vacía" no llegaría nunca.
MAX_PAGES = 60


def build_carrefour_url(link: str | None) -> str | None:
    """
    URL absoluta a partir del `link` que devuelve VTEX.

    El campo viene relativo ("/vinagre-de-alcohol-alcazar-1-lt-100650/p"), así
    que guardarlo crudo deja links rotos en la ficha del producto — el mismo
    problema que en su momento tuvo Coto y que resolvió build_coto_url().
    """
    if not link:
        return None

    if link.startswith("http"):
        return link

    return f"{BASE_URL}/{link.lstrip('/')}"


class CarrefourScraper:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:152.0) Gecko/20100101 Firefox/152.0",
            "Accept": "*/*",
            "Accept-Language": "es-AR,es;q=0.9",
            "Content-Type": "application/json",
            "Referer": f"{BASE_URL}/"
        }
        self.client = httpx.Client(headers=self.headers, http2=True, timeout=15.0)

    @staticmethod
    def _build_payload(category_query: str, from_idx: int, to_idx: int) -> dict:
        """
        Arma el body del POST para un tramo de una categoría.

        El `map` se deriva de la cantidad de segmentos (un "c" por facet) en vez
        de hardcodearse: las categorías del MVP tienen dos y tres niveles, y
        mandar menos "c" que `selectedFacets` es desalinear el contrato de VTEX.
        """
        parts = [part for part in category_query.split("/") if part]

        return {
            "operationName": "productSearchV3",
            "variables": {
                "skusFilter": "ALL_AVAILABLE",
                "simulationBehavior": "default",
                "installmentCriteria": "MAX_WITHOUT_INTEREST",
                "productOriginVtex": False,
                "map": ",".join(["c"] * len(parts)),
                "query": category_query,
                "orderBy": "OrderByScoreDESC",
                "from": from_idx,
                "to": to_idx,
                "selectedFacets": [{"key": "c", "value": part} for part in parts],
                "operator": "and",
                "fuzzy": "0",
                "searchState": None,
                "hideUnavailableItems": True,
                "facetsBehavior": "Static",
                "categoryTreeBehavior": "default",
                "withFacets": False,
                "variant": "null-null"
            },
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": "b398fc0a2fd04ea5d4f7a94c732c10fb1bf64f8f9a2b31c92aee6a5e796457c9",
                    "sender": "vtex.store-resources@0.x",
                    "provider": "vtex.search-graphql@0.x"
                }
            }
        }

    def scrape_category_slice(self, category_query: str, from_idx: int, to_idx: int):
        payload = self._build_payload(category_query, from_idx, to_idx)

        # Igual que en Día: un error LEVANTA. Devolver None dejaba al llamador
        # con cero productos, que su regla de "página vacía = fin de categoría"
        # lee como éxito, y el pruning después borra lo que no se recorrió.
        try:
            response = self.client.post(GRAPHQL_URL, json=payload)
        except Exception as exc:
            logger.exception("[CARREFOUR] Excepción en request POST.")
            raise CategoryScrapeError(
                f"[CARREFOUR] Falló el POST de la sección {from_idx}-{to_idx}: {exc}"
            ) from exc

        if response.status_code != 200:
            logger.error("[CARREFOUR] Error %s en la sección %s-%s",
                         response.status_code, from_idx, to_idx)
            raise CategoryScrapeError(
                f"[CARREFOUR] HTTP {response.status_code} en la sección {from_idx}-{to_idx}."
            )

        try:
            return response.json()
        except Exception as exc:
            raise CategoryScrapeError(
                f"[CARREFOUR] La sección {from_idx}-{to_idx} no devolvió JSON: {exc}"
            ) from exc

    def process_products(self, response_json, shelf: str | None = None,
                         taxonomy_path: str | None = None,
                         source_category: str | None = None):
        # La validación vive en src/scrapers/vtex.py, compartida con Día: las dos
        # tiendas corren la misma persisted query y fallan igual cuando el hash
        # se rota. Y ahora LEVANTA en vez de devolver None — detectar el problema
        # y después seguir con un `break` silencioso era la mitad del arreglo.
        search = extract_search_payload(response_json, "CARREFOUR")

        products_data = search.get("products") or []
        parsed_products = []

        for p in products_data:
            items = p.get("items", [])
            if not items:
                continue

            first_item = items[0]
            sellers = first_item.get("sellers", [])
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
            # (ej. "1 Lt", "400 Gr"), igual que en Día.
            total_volume_weight, unit_type = extract_real_volume(p.get("productName"))

            # Fallback: derivar el tamaño del precio por unidad de VTEX cuando el
            # nombre no trae talla.
            if unit_type == "un" and base_price > 0 and precio_por_und is not None and precio_por_und > 0:
                total_volume_weight = round(base_price / precio_por_und, 3)

                # Igual que en Día: estas dos ramas deciden la MAGNITUD (un
                # cociente menor a 1 significa que `precio_por_und` venía por
                # litro/kilo), y normalize_magnitude decide el VOCABULARIO.
                # Sin lo segundo, la etiqueta cruda de VTEX ("gr", "kg") queda
                # guardada y el producto deja de ser comparable contra las filas
                # en "g"/"ml".
                if "lt" in unidad_medida or "l" in unidad_medida:
                    if total_volume_weight < 1.0:
                        total_volume_weight = total_volume_weight * 1000
                        unidad_medida = "ml"
                elif "kg" in unidad_medida:
                    if total_volume_weight < 1.0:
                        total_volume_weight = total_volume_weight * 1000
                        unidad_medida = "g"

                total_volume_weight, unit_type = normalize_magnitude(
                    total_volume_weight, unidad_medida
                )

            images = first_item.get("images", [])
            image_url = images[0].get("imageUrl") if images else None

            # Sólo fuentes que describen ESTE producto: nombre, marca, ruta de
            # categoría y los campos estructurados que la tienda le asigna.
            # `description`/`metaTagDescription` quedan EXCLUIDOS a propósito —
            # son copy de marketing que enumera productos hermanos de la línea y
            # ya provocaron un falso "vegano" en un ketchup (ver scraper_dia.py).
            dietary_sources = [
                p.get("productName"),
                p.get("brand"),
                taxonomy_path,
                p.get("clusterHighlights"),
                [prop.get("values") for prop in p.get("properties", [])],
            ]
            is_gluten_free, is_vegan = detect_dietary_flags(*dietary_sources)

            product = {
                "store_sku": p.get("productId"),
                # La categoría con la que se barrió: es lo que le permite al
                # pruning acotarse a las que terminaron bien.
                "source_category": source_category,
                # El SKU real de VTEX, distinto del productId en este catálogo
                # (producto 100650 = item 17305). Es el que espera
                # /checkout/cart/add?sku= para armar el carrito por URL.
                "store_item_id": first_item.get("itemId"),
                "ean": first_item.get("ean"),
                "name": p.get("productName"),
                "brand": p.get("brand"),
                # La góndola canónica: la única noción de categoría del proyecto
                # (ver src/shelves.py).
                "shelf": shelf,
                # `link` viene relativo en Carrefour, a diferencia de Día.
                "url": build_carrefour_url(p.get("link")),
                "image_url": image_url,
                "base_price": base_price,
                "in_stock": True,
                "total_volume_weight": total_volume_weight,
                "unit_type": unit_type,
                "is_gluten_free": is_gluten_free,
                "is_vegan": is_vegan,
                "raw_promos": sellers[0].get("commertialOffer", {}) if sellers else {}
            }
            parsed_products.append(product)

        return parsed_products

    def scrape_entire_category(self, category_query: str):
        """
        Pagina de forma automática iterando los índices 'from' y 'to' hasta que
        VTEX no devuelva más productos.
        """
        from_idx = 0
        to_idx = PAGE_SIZE - 1
        all_category_products = []
        seen_skus = set()

        # La góndola canónica de este slug (src/shelves.py) es la categoría con
        # la que se guarda el producto: idéntica en las tres cadenas, que es lo
        # que hace comparables sus catálogos. La ruta de taxonomía se resuelve
        # para usarla como evidencia dietaria, no se persiste.
        shelf = shelf_for_key("carrefour", category_query)
        taxonomy_path = category_path("carrefour", category_query)

        if not shelf:
            logger.warning("[CARREFOUR] Ojo: '%s' no está en src/shelves.py; sus "
                           "productos quedarían sin góndola.", category_query)

        for page in range(MAX_PAGES):
            logger.info("[CARREFOUR] Recopilando %s - Índices %s a %s...",
                        category_query, from_idx, to_idx)
            raw_data = self.scrape_category_slice(category_query, from_idx, to_idx)
            products = self.process_products(raw_data, shelf, taxonomy_path,
                                             category_query)

            if not products:
                logger.info("[CARREFOUR] Final de la categoría '%s' alcanzado.", category_query)
                break

            nuevos = [p for p in products if p["store_sku"] not in seen_skus]
            if not nuevos:
                # El endpoint dejó de respetar el `from`: no sabemos qué parte de
                # la categoría falta, así que esto es un fallo, no un final.
                raise CategoryScrapeError(
                    f"[CARREFOUR] La página {from_idx}-{to_idx} de '{category_query}' repite "
                    f"productos ya vistos: la paginación dejó de avanzar."
                )

            seen_skus.update(p["store_sku"] for p in nuevos)
            all_category_products.extend(nuevos)

            total_disponible = extract_search_payload(raw_data, "CARREFOUR").get("recordsFiltered")
            if isinstance(total_disponible, int) and to_idx + 1 >= total_disponible:
                logger.info("[CARREFOUR] Se recorrieron los %s productos de '%s'.",
                            total_disponible, category_query)
                break

            from_idx += PAGE_SIZE
            to_idx += PAGE_SIZE
            time.sleep(random.uniform(1.5, 3.0))  # Delay para evitar bloqueos
        else:
            # Agotar el tope significa que ni el corte por página vacía ni el de
            # `recordsFiltered` llegaron: la categoría quedó recorrida a medias y
            # reportarla OK habilitaría el pruning sobre un barrido trunco.
            raise CategoryScrapeError(
                f"[CARREFOUR] Se alcanzó el tope de {MAX_PAGES} páginas en '{category_query}' "
                f"sin llegar al final de la categoría."
            )

        return all_category_products


if __name__ == "__main__":
    # Corriendo standalone nadie configuró el logging: sin esto, el progreso del
    # scrapeo (que ahora va por logger) no se ve. Bajo el orquestador este bloque
    # no corre y manda su configuración, que además escribe a archivo.
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    scraper = CarrefourScraper()
    db = SmartCartDB()

    print("\n--- INICIANDO PROCESO GLOBAL SMARTCART (CARREFOUR) ---")

    for cat_query in MVP_CATEGORIES:
        print(f"\n=== ARRANCANDO BARRIDO DE CATEGORÍA: {cat_query} ===")
        productos_carrefour = scraper.scrape_entire_category(cat_query)

        if productos_carrefour:
            db.save_store_products(productos_carrefour, "carrefour_online")

        print(f"--- FIN DE CATEGORÍA {cat_query} ---\n")
        time.sleep(3.5)  # Delay amigable para evitar blocks

    print("\n[FIN DEL PROCESO] Datos de Carrefour impactados en Postgres.")
