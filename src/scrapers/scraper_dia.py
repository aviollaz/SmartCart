import httpx
import json
import time
import random
import sys
import os

# Ajuste de ruta para poder importar database.py
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database import SmartCartDB

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

    def process_products(self, response_json):
        if not response_json:
            return []
            
        products_data = response_json.get("data", {}).get("productSearch", {}).get("products", [])
        parsed_products = []
        
        for p in products_data:
            items = p.get("items", [])
            if not items:
                continue
                
            first_item = items[0]
            sellers = first_item.get("sellers", [])
            price = 0.0
            if sellers:
                comm_comm = sellers[0].get("commertialOffer", {})
                price = float(comm_comm.get("Price", 0.0))

            product = {
                "store_sku": p.get("productId"),
                "ean": first_item.get("ean"),
                "name": p.get("productName"),
                "brand": p.get("brand"),
                "url": p.get("link"),
                "base_price": price,
                "in_stock": True,
                "is_weighable": False,
                "unit_type": first_item.get("measurementUnit", "un"),
                "raw_promos": sellers[0].get("commertialOffer", {}) if sellers else []
            }
            parsed_products.append(product)
            
        return parsed_products

    def scrape_entire_category(self, category_query: str):
        """
        Página de forma automática iterando los índices 'from' y 'to'
        hasta que VTEX no devuelva más productos.
        """
        step = 16  # Traemos bloques de 16 productos
        from_idx = 0
        to_idx = step - 1
        all_category_products = []

        while True:
            print(f"[DÍA] Recopilando {category_query} - Índices {from_idx} a {to_idx}...")
            raw_data = self.scrape_category_slice(category_query, from_idx, to_idx)
            products = self.process_products(raw_data)

            if not products:
                print(f"[DÍA] Final de la categoría '{category_query}' alcanzado.")
                break

            all_category_products.extend(products)

            # Siguiente bloque de productos
            from_idx += step
            to_idx += step
            time.sleep(random.uniform(1.5, 3.0)) # Delay defensivo anti-bloqueos

        return all_category_products

if __name__ == "__main__":
    scraper = DiaScraper()
    db = SmartCartDB()
    
    # Slugs reales y testeados para el motor de búsqueda de Día
    categorias_dia_mvp = [
        "almacen/harinas/harinas-de-trigo",       # Harina de Trigo (bien específico)
        "frescos/leches",                         # Leche
        "almacen/aceites-y-aderezos",              # Aceite (Trae aceites de girasol, oliva, blend, etc.)
        "desayuno/para-untar/dulces-de-leche"     # Dulce de Leche
    ]
    
    print("\n--- INICIANDO PROCESO GLOBAL SMARTCART (DÍA ONLINE) ---")
    
    for cat_query in categorias_dia_mvp:
        print(f"\n=== ARRANCANDO BARRIDO DE CATEGORÍA: {cat_query} ===")
        productos_dia = scraper.scrape_entire_category(cat_query)
        
        if productos_dia:
            # Tu lógica persistirá esto de forma nativa discriminando que es de Día
            db.save_store_products(productos_dia, "dia_online")
            
        print(f"--- FIN DE CATEGORÍA {cat_query} ---\n")
        time.sleep(3.5)  # Delay amigable para evitar blocks
        
    print("\n[FIN DEL PROCESO] Datos de Día Online impactados en Postgres.")