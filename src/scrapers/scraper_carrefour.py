import httpx
import time
import random

from src.category_tags import category_label, tags_for_category
from src.database import SmartCartDB
from src.dietary_parser import detect_dietary_flags
from src.size_parser import extract_real_volume, normalize_magnitude

# Carrefour corre sobre VTEX IO igual que Día, así que se le pega a la misma
# operación `productSearchV3` con persisted query. Se manda por POST con el JSON
# en el body en vez del GET con las variables en Base64 en la URL: es el mismo
# endpoint y evita tener que codificar/escapar el payload.
GRAPHQL_URL = "https://www.carrefour.com.ar/_v/segment/graphql/v1?workspace=master"

BASE_URL = "https://www.carrefour.com.ar"

# Categorías del MVP. Los slugs salen de carrefour_categories.json (generado por
# get_carrefour_categories.py) y están verificados contra ese dump: dos son de
# dos niveles y tres de tres, que es justamente lo que ejercita el `map`
# dinámico de _build_payload().
MVP_CATEGORIES = [
    "almacen/aceites-y-vinagres",
    "lacteos-y-productos-frescos/leches",
    "almacen/harinas/harinas-comunes-y-leudantes",
    "desayuno-y-merienda/mermeladas-y-otros-dulces/dulce-de-leche",
    "desayuno-y-merienda/golosinas-y-chocolates/alfajores",
]

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

        try:
            response = self.client.post(GRAPHQL_URL, json=payload)
            if response.status_code != 200:
                print(f"[CARREFOUR] Error {response.status_code} en la sección {from_idx}-{to_idx}")
                return None

            return response.json()
        except Exception as e:
            print(f"[CARREFOUR] Excepción en request POST: {e}")
            return None

    @staticmethod
    def extract_search_payload(response_json) -> dict | None:
        """
        Devuelve el bloque `productSearch`, o None si la respuesta no es una
        respuesta válida de búsqueda.

        No es paranoia: el hash de la persisted query está fijo y sale de una
        sesión del navegador. Si Carrefour lo rota, GraphQL contesta **HTTP 200**
        con un array `errors` (PERSISTED_QUERY_NOT_FOUND) y sin `data`. Sin esta
        distinción, el corte de paginación por "página vacía" lo interpreta como
        "la categoría se terminó" y el scrapeo cierra con 0 productos y sin un
        solo error a la vista.
        """
        if not isinstance(response_json, dict):
            return None

        errors = response_json.get("errors")
        if errors:
            mensajes = "; ".join(
                str(err.get("message", err)) for err in errors if isinstance(err, dict)
            ) or str(errors)
            print(f"[CARREFOUR] La API devolvió errores de GraphQL: {mensajes}")
            print("[CARREFOUR] Suele significar que el sha256Hash de la persisted query cambió.")
            return None

        data = response_json.get("data")
        if not isinstance(data, dict) or data.get("productSearch") is None:
            print("[CARREFOUR] Respuesta sin 'data.productSearch': no es un resultado de búsqueda válido.")
            return None

        return data["productSearch"]

    def process_products(self, response_json, category_tags: list[str] | None = None, taxonomy_label: str | None = None):
        search = self.extract_search_payload(response_json)
        if search is None:
            return []

        category_tags = category_tags or []
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

            # --- EXTRACCIÓN Y NORMALIZACIÓN DE CATEGORÍA ---
            # Igual que en Día: preferimos la hoja del dump de taxonomía (misma
            # fuente que los tags) y caemos al path que manda VTEX.
            category_name = taxonomy_label or "Sin Categoría"

            if not taxonomy_label:
                raw_categories = p.get("categories", [])
                if raw_categories:
                    # VTEX manda rutas como "/Almacén/Aceites y vinagres/Vinagres, acetos y limón/"
                    path_parts = [part for part in raw_categories[0].strip("/").split("/") if part]

                    if len(path_parts) >= 2:
                        category_name = path_parts[1]
                    elif len(path_parts) == 1:
                        category_name = path_parts[0]
            # -----------------------------------------------

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
                # `link` viene relativo en Carrefour, a diferencia de Día.
                "url": build_carrefour_url(p.get("link")),
                "image_url": image_url,
                "base_price": base_price,
                "in_stock": True,
                "is_weighable": False,
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

        # El dump de taxonomía está indexado por el mismo slug que recibimos acá,
        # así que la ruta jerárquica se resuelve una sola vez por categoría.
        category_tags = tags_for_category("carrefour", category_query)
        taxonomy_label = category_label("carrefour", category_query)

        if not category_tags:
            print(f"[CARREFOUR] Ojo: '{category_query}' no está en carrefour_categories.json (se guardará sin tags).")

        for page in range(MAX_PAGES):
            print(f"[CARREFOUR] Recopilando {category_query} - Índices {from_idx} a {to_idx}...")
            raw_data = self.scrape_category_slice(category_query, from_idx, to_idx)
            products = self.process_products(raw_data, category_tags, taxonomy_label)

            if not products:
                print(f"[CARREFOUR] Final de la categoría '{category_query}' alcanzado.")
                break

            # Si el endpoint deja de respetar el `from` y repite la primera
            # página, cortamos acá en vez de acumular duplicados hasta MAX_PAGES.
            nuevos = [p for p in products if p["store_sku"] not in seen_skus]
            if not nuevos:
                print(f"[CARREFOUR] La página {from_idx}-{to_idx} repite productos ya vistos; se corta.")
                break

            seen_skus.update(p["store_sku"] for p in nuevos)
            all_category_products.extend(nuevos)

            total_disponible = self.extract_search_payload(raw_data).get("recordsFiltered")
            if isinstance(total_disponible, int) and to_idx + 1 >= total_disponible:
                print(f"[CARREFOUR] Se recorrieron los {total_disponible} productos de '{category_query}'.")
                break

            from_idx += PAGE_SIZE
            to_idx += PAGE_SIZE
            time.sleep(random.uniform(1.5, 3.0))  # Delay para evitar bloqueos
        else:
            print(f"[CARREFOUR] Se alcanzó el tope de {MAX_PAGES} páginas en '{category_query}'.")

        return all_category_products


if __name__ == "__main__":
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
