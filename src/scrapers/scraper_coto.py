import httpx
import re
import time
import random

from src.category_tags import category_label, tags_for_category
from src.dietary_parser import detect_dietary_flags
from src.size_parser import extract_real_volume, normalize_magnitude


# Categorías del MVP. El catálogo es deliberadamente angosto; ampliar esta
# lista es la forma de scrapear más góndolas (los ids salen de coto_categories.json).
MVP_CATEGORIES = [
    "catv00001412",  # Almacén -> Harinas -> Harina de Trigo
    "catv00003266",  # Frescos -> Lácteos -> Leches
    "catv00001413",  # Almacén -> Harinas -> Sémola
    "catv00003250",  # Frescos -> Lácteos -> Dulce de Leche
    "catv00003596",  # Almacén -> Golosinas -> Alfajores
]


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

        # La ruta jerárquica de esta categoría ya está en el dump de taxonomía,
        # indexada por el mismo id que recibimos acá: se resuelve una sola vez
        # y se adjunta a cada producto como tags estrictos de góndola.
        category_tags = tags_for_category("coto", category_id)
        taxonomy_label = category_label("coto", category_id)

        while True:
            url = (
                f"https://api.coto.com.ar/api/v1/ms-digital-sitio-bff-web/api/v1/products/categories/{category_id}"
                f"?page={page}&key=key_r6xzz4IAoTWcipni&num_results_per_page=24"
                f"&pre_filter_expression=%7B%22name%22:%22store_availability%22,%22value%22:%22200%22%7D"
                f"&c=cio-fe-web-coto-3.5.2&i=5792d439-2540-4787-a25c-b6cf441f61c9&s=1"
                f"&origin_referrer=/sitios/cdigi/productos/categorias/{category_id}"
            )
            
            print(f"[COTO] Extrayendo {category_id} - Página {page}...")
            
            try:
                response = self.client.get(url)
                
                if response.status_code != 200:
                    print(f"[COTO] Error {response.status_code} al intentar acceder a la página {page}. Frenando.")
                    break
                    
                data = response.json()
                
                # --- EXTRACCIÓN DE CATEGORÍA ---
                # Preferimos la hoja de la taxonomía (estable y consistente con
                # los tags); el display_name de la respuesta queda de fallback
                # para ids que no estén en el dump.
                category_name = taxonomy_label or "Sin Categoría"
                if not taxonomy_label:
                    groups = data.get("response", {}).get("groups", [])
                    if groups:
                        category_name = groups[0].get("display_name", "Sin Categoría")
                # -------------------------------

                results = data.get("response", {}).get("results", [])
                
                if not results:
                    print(f"[COTO] Final de la categoría {category_id} alcanzado.")
                    break
                
                for item in results:
                    prod_data = item.get("data", {})
                    
                    base_price = 0.0
                    format_price = 0.0
                    
                    prices_list = prod_data.get("price", [])
                    
                    if isinstance(prices_list, list):
                        for p_store in prices_list:
                            if p_store.get("store") == "200":
                                base_price = float(p_store.get("listPrice", 0))
                                format_price = float(p_store.get("formatPrice", 0))
                                break
                    
                    if base_price == 0.0:
                        base_price = float(prod_data.get("product_list_price", 0))
                    
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
                    is_gluten_free, is_vegan = detect_dietary_flags(name, brand, category_tags)

                    product = {
                        "store_sku": prod_data.get("sku_id"),
                        "ean": str(prod_data.get("product_main_ean")) if prod_data.get("product_main_ean") else None,
                        "name": name,
                        "brand": brand,
                        "category": category_name,
                        "tags": category_tags,
                        "url": build_coto_url(name, resolve_coto_product_id(item, prod_data)),
                        "image_url": prod_data.get("image_url"),
                        "base_price": base_price,
                        "in_stock": prod_data.get("in_stock", True),
                        "is_weighable": bool(prod_data.get("product_weighable", 0)),
                        "total_volume_weight": total_volume_weight,
                        "unit_type": unit_type,
                        "is_gluten_free": is_gluten_free,
                        "is_vegan": is_vegan,
                        "raw_promos": prod_data.get("discounts", [])
                    }
                    all_products.append(product)
                
                time.sleep(random.uniform(1.5, 3.0))
                page += 1
                
            except Exception as e:
                print(f"[COTO] Ocurrió una excepción en la página {page}: {e}")
                break
                
        return all_products

if __name__ == "__main__":
    from src.database import SmartCartDB

    scraper = CotoScraper()
    db = SmartCartDB()
    
    print("\n--- INICIANDO PROCESO GLOBAL SMARTCART ---")

    for cat_id in MVP_CATEGORIES:
        productos_recolectados = scraper.scrape_category(cat_id)
        
        if productos_recolectados:
            db.save_store_products(productos_recolectados, "coto_online")
            
        print(f"--- FIN DE CATEGORÍA {cat_id} ---\n")
        time.sleep(2.0)