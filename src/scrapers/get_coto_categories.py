import httpx
import json

def get_coto_categories_map():
    url = "https://www.coto.com.ar/rest/model/atg/actors/cBackOfficeActor/constructorCategories?pushSite=CotoDigital&_dynSessConf=-4844092794822687620"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:152.0) Gecko/20100101 Firefox/152.0",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.coto.com.ar/",
        "Connection": "keep-alive"
    }
    
    # Espejamos las cookies que te dieron acceso en Firefox
    cookies = {
        "JSESSIONID": "Kfo9ARJWbLz5hUFiTTAvSpDPv29vMNBUC7CP-bBBZFOCwJOlERyD!464085810",
        "cookiesession1": "678A3E1E667EF3DEC24384F3219D4055"
    }
    
    categories_map = {}
    
    try:
        print("[COTO] Descargando mapa global de categorías...")
        with httpx.Client(headers=headers, cookies=cookies, http2=True, timeout=20.0) as client:
            response = client.get(url)
            
            if response.status_code != 200:
                print(f"[ERROR] Código de estado {response.status_code}")
                return None
                
            data = response.json()
            outputs = data.get("output", [])
            
            for item in outputs:
                top_level = item.get("topLevelCategory", {})
                top_name = top_level.get("displayName", "")
                
                # Ignoramos categorías que no tengan que ver con supermercado puro (Electro, Textil, Hogar)
                if top_name in ["Electro", "Textil y Calzado", "Hogar y Bazar", "Aire Libre y Automotor"]:
                    continue
                    
                sub_cats = top_level.get("subCategories", [])
                for sub1 in sub_cats:
                    sub2_cats = sub1.get("subCategories2", [])
                    
                    for sub2 in sub2_cats:
                        cat_id = sub2.get("categoryId")
                        cat_name = sub2.get("displayName")
                        
                        if cat_id and cat_name:
                            # Guardamos la relación amigable: código -> Nombre descriptivo
                            categories_map[cat_id] = f"{top_name} -> {sub1.get('displayName')} -> {cat_name}"
                            
        return categories_map

    except Exception as e:
        print(f"[ERROR] No se pudo mapear las categorías: {e}")
        return None

if __name__ == "__main__":
    menu_mapeado = get_coto_categories_map()
    
    if menu_mapeado:
        print(f"\n[ÉXITO] Se encontraron {len(menu_mapeado)} subcategorías finales de supermercado.")
        
        # Guardamos el mapa en un archivo local para que el scraper de productos lo consuma cuando quiera
        with open("src/scrapers/coto_categories.json", "w", encoding="utf-8") as f:
            json.dump(menu_mapeado, f, indent=2, ensure_ascii=False)
        print("[INFO] Archivo 'src/scrapers/coto_categories.json' generado con éxito.")