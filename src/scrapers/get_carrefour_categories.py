import httpx
import json

def get_carrefour_categories_rest():
    # API REST pública de VTEX, la misma que expone Día (get_dia_categories.py).
    # El "/3" es la profundidad del árbol.
    url = "https://www.carrefour.com.ar/api/catalog_system/pub/category/tree/3"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:152.0) Gecko/20100101 Firefox/152.0",
        "Accept": "application/json",
        "Referer": "https://www.carrefour.com.ar/"
    }

    categories_map = {}

    try:
        print("[CARREFOUR] Solicitando árbol de categorías mediante API REST pública...")
        with httpx.Client(headers=headers, http2=True, timeout=20.0) as client:
            response = client.get(url)

            if response.status_code != 200:
                print(f"[ERROR] La API respondió con código HTTP {response.status_code}")
                return None

            categories_list = response.json()

            # El catálogo es un árbol anidado
            for level1 in categories_list:
                l1_name = level1.get("name", "")

                # Nivel 2
                children_l2 = level1.get("children", []) or []
                for level2 in children_l2:
                    l2_name = level2.get("name", "")

                    # Nivel 3
                    children_l3 = level2.get("children", []) or []
                    for level3 in children_l3:
                        l3_name = level3.get("name", "")
                        url_completa = level3.get("url", "")

                        if url_completa:
                            slug_match = url_completa.replace("https://www.carrefour.com.ar/", "").strip("/")

                            if slug_match:
                                categories_map[slug_match] = f"{l1_name} -> {l2_name} -> {l3_name}"

                    url_l2 = level2.get("url", "")
                    if url_l2:
                        slug_l2 = url_l2.replace("https://www.carrefour.com.ar/", "").strip("/")
                        if slug_l2 and slug_l2 not in categories_map:
                            categories_map[slug_l2] = f"{l1_name} -> {l2_name}"

        return categories_map

    except Exception as e:
        print(f"[ERROR EXCEPCIÓN]: No se pudo procesar el catálogo REST: {e}")
        return None

if __name__ == "__main__":
    menu_mapeado = get_carrefour_categories_rest()

    if menu_mapeado:
        print(f"\n[ÉXITO] Se descubrieron {len(menu_mapeado)} rutas de categorías en el árbol de Carrefour.")
        with open("src/scrapers/carrefour_categories.json", "w", encoding="utf-8") as f:
            json.dump(menu_mapeado, f, indent=2, ensure_ascii=False)
        print("[INFO] Archivo generado con éxito en 'src/scrapers/carrefour_categories.json'.")
