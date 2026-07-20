import httpx
import time
import random

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
                # Extraemos el nombre de la categoría del primer grupo disponible
                category_name = "Sin Categoría"
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
                    prices_list = prod_data.get("price", [])
                    
                    if isinstance(prices_list, list):
                        for p_store in prices_list:
                            if p_store.get("store") == "200":
                                base_price = float(p_store.get("listPrice", 0))
                                break
                    
                    if base_price == 0.0:
                        base_price = float(prod_data.get("product_list_price", 0))
                    
                    product = {
                        "store_sku": prod_data.get("sku_id"),
                        "ean": str(prod_data.get("product_main_ean")) if prod_data.get("product_main_ean") else None,
                        "name": item.get("value"),
                        "brand": prod_data.get("product_brand"),
                        "category": category_name,  
                        "url": f"https://www.cotodigital.com.ar{prod_data.get('url')}" if prod_data.get('url') else None,
                        "image_url": prod_data.get("image_url"),
                        "base_price": base_price,
                        "in_stock": prod_data.get("in_stock", True),
                        "is_weighable": bool(prod_data.get("product_weighable", 0)),
                        "unit_type": prod_data.get("product_unit_of_measure"), 
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
    import sys
    import os
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from database import SmartCartDB
    
    scraper = CotoScraper()
    db = SmartCartDB()
    
    categorias_mvp = ["catv00001412", "catv00003266", "catv00001413", "catv00003250", "catv00003596"]
    
    print("\n--- INICIANDO PROCESO GLOBAL SMARTCART ---")
    
    for cat_id in categorias_mvp:
        productos_recolectados = scraper.scrape_category(cat_id)
        
        if productos_recolectados:
            db.save_store_products(productos_recolectados, "coto_online")
            
        print(f"--- FIN DE CATEGORÍA {cat_id} ---\n")
        time.sleep(2.0)