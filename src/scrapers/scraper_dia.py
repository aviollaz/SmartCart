import httpx
import logging
import time
import random

from src.database import SmartCartDB
from src.dietary_parser import detect_dietary_flags
from src.ean import normalize_ean
from src.scrapers.errors import CategoryScrapeError
from src.scrapers.vtex import extract_search_payload, read_availability
from src.shelves import keys_for_store, shelf_for_key
from src.taxonomy import category_path
from src.size_parser import extract_real_volume, normalize_magnitude

logger = logging.getLogger(__name__)

# Las góndolas que se barren viven en src/shelves.py, alineadas con las de Coto y
# Carrefour: el catálogo sólo sirve para comparar precios si las tres tiendas
# barrieron el mismo estante. Ampliar es agregar una fila allá, no una lista acá.
MVP_CATEGORIES = keys_for_store("dia")

# Tope duro de páginas por categoría. Es una red de seguridad, no el criterio de
# corte: el corte real es la página sin productos. Sin esto un endpoint que
# ignore el `from` y repita el primer tramo deja el barrido en bucle — es
# exactamente el riesgo por el que el workflow nocturno lleva `timeout-minutes`.
# Mismo rol que el MAX_PAGES de scraper_carrefour.py.
MAX_PAGES = 60

class DiaScraper:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:152.0) Gecko/20100101 Firefox/152.0",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Content-Type": "application/json",
            "Referer": "https://diaonline.supermercadosdia.com.ar/"
        }
        self.client = httpx.Client(headers=self.headers, http2=True, timeout=15.0)

    def scrape_category_slice(self, category_query: str, from_idx: int, to_idx: int):
        url = "https://diaonline.supermercadosdia.com.ar/_v/segment/graphql/v1?workspace=master&maxAge=short&appsEtag=remove&domain=store&locale=es-AR"
        
        payload = {
            "operationName": "productSearchV3",
            "variables": {
                "hideUnavailableItems": True,
                "skusFilter": "FIRST_AVAILABLE",
                "simulationBehavior": "default",
                "installmentCriteria": "MAX_WITHOUT_INTEREST",
                "productOriginVtex": True,
                "map": "c,c" if "/" in category_query else "c",
                "query": category_query,
                "orderBy": "OrderByScoreDESC",
                "from": from_idx,
                "to": to_idx,
                "selectedFacets": [{"key": "c", "value": v} for v in category_query.split("/")],
                "operator": "and",
                "fuzzy": "0",
                "searchState": None,
                "facetsBehavior": "Static",
                "categoryTreeBehavior": "default",
                "withFacets": False
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

        # Los errores LEVANTAN en vez de devolver None. Devolviéndolo, el
        # llamador terminaba con una lista vacía de productos y su regla de
        # "página vacía = fin de categoría" lo leía como un barrido exitoso: un
        # 500 pasajero en la página 3 de 6 cerraba la categoría con dos páginas,
        # `_run_store` la contaba OK y el pruning borraba las otras cuatro como
        # discontinuadas. Es el mismo bug que ya se corrigió en Coto.
        try:
            response = self.client.post(url, json=payload)
        except Exception as exc:
            logger.exception("[DÍA] Excepción en request POST.")
            raise CategoryScrapeError(
                f"[DÍA] Falló el POST de la sección {from_idx}-{to_idx}: {exc}"
            ) from exc

        if response.status_code != 200:
            logger.error("[DÍA] Error %s en la sección %s-%s",
                         response.status_code, from_idx, to_idx)
            raise CategoryScrapeError(
                f"[DÍA] HTTP {response.status_code} en la sección {from_idx}-{to_idx}."
            )

        try:
            return response.json()
        except Exception as exc:
            raise CategoryScrapeError(
                f"[DÍA] La sección {from_idx}-{to_idx} no devolvió JSON: {exc}"
            ) from exc

    def process_products(self, response_json, shelf: str | None = None,
                         taxonomy_path: str | None = None,
                         source_category: str | None = None):
        # `extract_search_payload` levanta si la respuesta no es un resultado de
        # búsqueda válido — el caso del sha256Hash rotado, que contesta 200 con
        # `errors` y sin `data`. Día no tenía esa distinción: leía el JSON con
        # `.get()` encadenados, así que una persisted query vencida rendía cero
        # productos y se reportaba como categoría agotada.
        search = extract_search_payload(response_json, "DÍA")

        products_data = search.get("products") or []
        parsed_products = []

        for p in products_data:
            items = p.get("items", [])
            if not items:
                continue
                
            first_item = items[0]
            sellers = first_item.get("sellers", [])
            # `base_price` se resetea por producto. Se asignaba SÓLO dentro del
            # `if sellers:`, así que un producto sin sellers heredaba en
            # silencio el precio del producto anterior del lote — y el primero
            # de la página levantaba NameError. Carrefour ya lo hacía bien.
            base_price = 0.0
            if sellers:
                comm_comm = sellers[0].get("commertialOffer", {})
                base_price = float(comm_comm.get("ListPrice", 0.0))

            precio_por_und = None
            unidad_medida = "un"

            # Buscar las properties en el JSON de VTEX
            for prop in p.get("properties", []):
                if prop["name"] == "PrecioPorUnd":
                    precio_por_und = float(prop["values"][0])
                if prop["name"] == "UnidaddeMedida":
                    unidad_medida = prop["values"][0].lower()

            # Fuente primaria: parsear el tamaño real del nombre del producto
            # (ej. "250 Ml", "400 Gr") - la property VTEX "UnidaddeMedida" no
            # siempre viene informada y cae al genérico "un".
            total_volume_weight, unit_type = extract_real_volume(p.get("productName"))

            # Fallback: usar el precio por unidad de VTEX cuando el nombre no trae talla.
            if unit_type == "un" and base_price > 0 and precio_por_und is not None and precio_por_und > 0:
                total_volume_weight = round(base_price / precio_por_und, 3)

                # Estas dos ramas deciden la MAGNITUD: un cociente menor a 1
                # significa que `precio_por_und` venía por litro/kilo y no por
                # mililitro/gramo. No tocarlas sin datos nuevos de VTEX.
                if "lt" in unidad_medida or "l" in unidad_medida:
                    if total_volume_weight < 1.0:
                        total_volume_weight = total_volume_weight * 1000
                        unidad_medida = "ml"
                elif "kg" in unidad_medida:
                    if total_volume_weight < 1.0:
                        total_volume_weight = total_volume_weight * 1000
                        unidad_medida = "g"

                # Y esto decide el VOCABULARIO, que es otra cosa. Sin esta
                # llamada, `unidad_medida` viajaba crudo desde la property de
                # VTEX: un producto en "gr" o en "kg" quedaba guardado con esa
                # etiqueta y dejaba de ser comparable contra las filas en "g",
                # desapareciendo en silencio de las sugerencias y de la
                # heurística de cierre de tienda.
                total_volume_weight, unit_type = normalize_magnitude(
                    total_volume_weight, unidad_medida
                )

            images = first_item.get("images", [])
            image_url = images[0].get("imageUrl") if images else None

            # Solo fuentes que describen ESTE producto: nombre, marca, ruta de
            # categoría y los campos estructurados que la tienda le asigna
            # (property "Otros" suele traer "Sin Tacc"). `clusterHighlights` y
            # `properties` pueden no venir —la query es persisted, con hash
            # fijo— así que se leen de forma defensiva.
            #
            # `description`/`metaTagDescription` quedan EXCLUIDOS a propósito:
            # son copy de marketing de la marca y enumeran productos hermanos.
            # El "Ketchup Hellmann's Regular" traía "...mayonesa hellmann's
            # light, clásica, suave, vegana, oliva..." y se marcaba como vegano.
            # Medido sobre 196 productos, el texto libre aportaba +5 detecciones
            # de gluten y 1 sola de vegano, que era justamente ese falso positivo.
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
                # El SKU real de VTEX, que es lo que espera
                # /checkout/cart/add?sku=. Acá coincide con el productId, pero se
                # guarda igual: el link de carrito lo exige explícitamente para
                # no depender de esa coincidencia (en Carrefour no se da).
                "store_item_id": first_item.get("itemId"),
                # Sin normalizar, esto pasaba el valor de VTEX crudo (ni
                # siquiera str()): la misma truncación que rompe a Coto,
                # esperando un payload distinto. Ver src/ean.py.
                "ean": normalize_ean(first_item.get("ean")),
                "name": p.get("productName"),
                "brand": p.get("brand"),
                # La góndola canónica: la única noción de categoría del proyecto
                # (ver src/shelves.py).
                "shelf": shelf,
                "url": p.get("link"),
                "image_url": image_url,
                "base_price": base_price,
                "in_stock": read_availability(first_item),
                "total_volume_weight": total_volume_weight,
                "unit_type": unit_type,
                "is_gluten_free": is_gluten_free,
                "is_vegan": is_vegan,
                "raw_promos": sellers[0].get("commertialOffer", {}) if sellers else []
            }
            parsed_products.append(product)
            
        return parsed_products

    def scrape_entire_category(self, category_query: str):
        """
        Página de forma automática iterando los índices 'from' y 'to'
        hasta que VTEX no devuelva más productos.
        """
        step = 16  # use a batch of 16
        from_idx = 0
        to_idx = step - 1
        all_category_products = []
        seen_skus = set()

        # La góndola canónica de este slug (src/shelves.py) es la categoría con
        # la que se guarda el producto: idéntica en las tres cadenas, que es lo
        # que hace comparables sus catálogos. La ruta de taxonomía se resuelve
        # para usarla como evidencia dietaria, no se persiste.
        shelf = shelf_for_key("dia", category_query)
        taxonomy_path = category_path("dia", category_query)

        for _ in range(MAX_PAGES):
            logger.info("[DÍA] Recopilando %s - Índices %s a %s...", category_query, from_idx, to_idx)
            raw_data = self.scrape_category_slice(category_query, from_idx, to_idx)
            products = self.process_products(raw_data, shelf, taxonomy_path,
                                             category_query)

            if not products:
                logger.info("[DÍA] Final de la categoría '%s' alcanzado.", category_query)
                break

            nuevos = [p for p in products if p["store_sku"] not in seen_skus]
            if not nuevos:
                # El endpoint dejó de respetar el `from`: no sabemos qué parte de
                # la categoría falta, así que esto es un fallo, no un final.
                raise CategoryScrapeError(
                    f"[DÍA] La página {from_idx}-{to_idx} de '{category_query}' repite "
                    f"productos ya vistos: la paginación dejó de avanzar."
                )

            seen_skus.update(p["store_sku"] for p in nuevos)
            all_category_products.extend(nuevos)

            from_idx += step
            to_idx += step
            time.sleep(random.uniform(1.5, 3.0)) # Delay to prevent blocking
        else:
            # Agotar el tope significa que el corte por página vacía nunca llegó:
            # la categoría queda recorrida a medias y no hay forma de saber
            # cuánto falta. Reportarla OK habilitaría el pruning sobre un barrido
            # trunco.
            raise CategoryScrapeError(
                f"[DÍA] Se alcanzó el tope de {MAX_PAGES} páginas en '{category_query}' "
                f"sin llegar al final de la categoría."
            )

        return all_category_products

if __name__ == "__main__":
    # Corriendo standalone nadie configuró el logging: sin esto, el progreso del
    # scrapeo (que ahora va por logger) no se ve. Bajo el orquestador este bloque
    # no corre y manda su configuración, que además escribe a archivo.
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    scraper = DiaScraper()
    db = SmartCartDB()
    
    print("\n--- INICIANDO PROCESO GLOBAL SMARTCART (DÍA ONLINE) ---")

    for cat_query in MVP_CATEGORIES:
        print(f"\n=== ARRANCANDO BARRIDO DE CATEGORÍA: {cat_query} ===")
        productos_dia = scraper.scrape_entire_category(cat_query)
        
        if productos_dia:
            # Tu lógica persistirá esto de forma nativa discriminando que es de Día
            db.save_store_products(productos_dia, "dia_online")
            
        print(f"--- FIN DE CATEGORÍA {cat_query} ---\n")
        time.sleep(3.5)  # Delay amigable para evitar blocks
        
    print("\n[FIN DEL PROCESO] Datos de Día Online impactados en Postgres.")