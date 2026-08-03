import httpx
import time
import random

from src.category_tags import category_label, tags_for_category
from src.database import SmartCartDB
from src.dietary_parser import detect_dietary_flags
from src.size_parser import extract_real_volume, normalize_magnitude

# Categorías del MVP. El catálogo es deliberadamente angosto; ampliar esta
# lista es la forma de scrapear más góndolas (los slugs salen de dia_categories.json).
MVP_CATEGORIES = [
    "almacen/harinas/harinas-de-trigo",
    "frescos/leches",
    "almacen/aceites-y-aderezos",
    "desayuno/para-untar/dulces-de-leche",
    "almacen/golosinas-y-alfajores/alfajores",
]

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

        try:
            response = self.client.post(url, json=payload)
            if response.status_code == 200:
                return response.json()
            else:
                print(f"[DÍA] Error {response.status_code} en la sección {from_idx}-{to_idx}")
                return None
        except Exception as e:
            print(f"[DÍA] Excepción en request POST: {e}")
            return None

    def process_products(self, response_json, category_tags: list[str] | None = None, taxonomy_label: str | None = None):
        if not response_json:
            return []

        category_tags = category_tags or []
        products_data = response_json.get("data", {}).get("productSearch", {}).get("products", [])
        parsed_products = []

        for p in products_data:
            items = p.get("items", [])
            if not items:
                continue
                
            first_item = items[0]
            sellers = first_item.get("sellers", [])
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

            # --- EXTRACCIÓN Y NORMALIZACIÓN DE CATEGORÍA ---
            # Preferimos la hoja del dump de taxonomía (misma fuente que los
            # tags); si el slug no está ahí, caemos al path que manda VTEX.
            category_name = taxonomy_label or "Sin Categoría"

            if not taxonomy_label:
                raw_categories = p.get("categories", [])
                if raw_categories:
                    # VTEX envía rutas como "/Frescos/Leches/Leches descremadas/"
                    # Tomamos la primera ruta, eliminamos las barras de los extremos y separamos por "/"
                    path_parts = [part for part in raw_categories[0].strip("/").split("/") if part]

                    # Intentamos agarrar el segundo nivel (ej: "Leches"), si no existe, agarramos el primero
                    if len(path_parts) >= 2:
                        category_name = path_parts[1]
                    elif len(path_parts) == 1:
                        category_name = path_parts[0]
            # -----------------------------------------------

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
                category_tags,
                p.get("clusterHighlights"),
                [prop.get("values") for prop in p.get("properties", [])],
            ]
            is_gluten_free, is_vegan = detect_dietary_flags(*dietary_sources)

            product = {
                "store_sku": p.get("productId"),
                "ean": first_item.get("ean"),
                "name": p.get("productName"),
                "brand": p.get("brand"),
                "category": category_name,
                "tags": category_tags,
                "url": p.get("link"),
                "image_url": image_url,
                "base_price": base_price,
                "in_stock": True,
                "is_weighable": False,
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

        # El dump de taxonomía está indexado por el mismo slug que recibimos
        # acá, así que la ruta jerárquica se resuelve una sola vez por categoría.
        category_tags = tags_for_category("dia", category_query)
        taxonomy_label = category_label("dia", category_query)

        while True:
            print(f"[DÍA] Recopilando {category_query} - Índices {from_idx} a {to_idx}...")
            raw_data = self.scrape_category_slice(category_query, from_idx, to_idx)
            products = self.process_products(raw_data, category_tags, taxonomy_label)

            if not products:
                print(f"[DÍA] Final de la categoría '{category_query}' alcanzado.")
                break

            all_category_products.extend(products)

            from_idx += step
            to_idx += step
            time.sleep(random.uniform(1.5, 3.0)) # Delay to prevent blocking

        return all_category_products

if __name__ == "__main__":
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