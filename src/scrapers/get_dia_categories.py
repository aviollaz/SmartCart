import httpx
import json
from urllib.parse import urlparse


def slug_from_url(url: str) -> str:
    """
    La ruta de la URL de una categoría, sin dominio.

    Se parsea la URL en vez de recortar el dominio con `replace()`, que es lo que
    hacía antes. VTEX dejó de devolver el dominio de la tienda en este árbol y
    ahora contesta `https://diaio.myvtex.com/almacen/...` — su dominio interno—,
    así que el `replace("https://diaonline.supermercadosdia.com.ar/", "")` no
    recortaba nada y la clave quedaba siendo la URL entera. Regenerar el dump con
    esa versión no fallaba: escribía 586 claves que ningún scraper puede usar, y
    `tests/test_shelves.py` habría empezado a rechazar TODAS las claves de Día a
    la vez, sin ninguna pista de por qué.

    Cualquier dominio sirve, que es justamente el punto: la clave es la ruta.
    """
    return urlparse(url).path.strip("/")


def get_dia_categories_rest():
    # Public VTEX REST API  
    url = "https://diaonline.supermercadosdia.com.ar/api/catalog_system/pub/category/tree/3"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:152.0) Gecko/20100101 Firefox/152.0",
        "Accept": "application/json",
        "Referer": "https://diaonline.supermercadosdia.com.ar/"
    }

    categories_map = {}

    try:
        print("[DÍA] Solicitando árbol de categorías mediante API REST pública...")
        with httpx.Client(headers=headers, http2=True, timeout=20.0) as client:
            response = client.get(url)
            
            if response.status_code != 200:
                print(f"[ERROR] La API respondió con código HTTP {response.status_code}")
                return None
                
            categories_list = response.json()
            
            # The catalog is a nested tree
            for level1 in categories_list:
                l1_name = level1.get("name", "")
                
                # Level 2
                children_l2 = level1.get("children", []) or []
                for level2 in children_l2:
                    l2_name = level2.get("name", "")
                    
                    # Level 3
                    children_l3 = level2.get("children", []) or []
                    for level3 in children_l3:
                        l3_name = level3.get("name", "")
                        url_completa = level3.get("url", "")
                        
                        if url_completa:
                            slug_match = slug_from_url(url_completa)

                            if slug_match:
                                categories_map[slug_match] = f"{l1_name} -> {l2_name} -> {l3_name}"
                                
                    url_l2 = level2.get("url", "")
                    if url_l2:
                        slug_l2 = slug_from_url(url_l2)
                        if slug_l2 and slug_l2 not in categories_map:
                            categories_map[slug_l2] = f"{l1_name} -> {l2_name}"

        return categories_map

    except Exception as e:
        print(f"[ERROR EXCEPCIÓN]: No se pudo procesar el catálogo REST: {e}")
        return None

if __name__ == "__main__":
    menu_mapeado = get_dia_categories_rest()
    
    if menu_mapeado:
        print(f"\n[ÉXITO] Se descubrieron {len(menu_mapeado)} rutas de categorías en el árbol de Día Online.")
        with open("src/scrapers/dia_categories.json", "w", encoding="utf-8") as f:
            json.dump(menu_mapeado, f, indent=2, ensure_ascii=False)
        print("[INFO] Archivo generado con éxito en 'src/scrapers/dia_categories.json'.")
