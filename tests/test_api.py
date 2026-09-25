# tests/test_api.py
import logging
from fastapi.testclient import TestClient
from src.api import app  # Importación limpia gracias a pytest.ini

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def test_fastapi_endpoints():
    logger.info("Inicializando TestClient para FastAPI...")
    # El bloque with asegura que los manejadores lifespan (startup y shutdown) se ejecuten,
    # cargando el modelo SentenceTransformer en memoria.
    with TestClient(app) as client:
        # 1. Test Root endpoint
        logger.info("Probando endpoint de salud (GET /)...")
        response = client.get("/")
        assert response.status_code == 200, "Root endpoint falló"
        data = response.json()
        logger.info(f"Respuesta GET /: {data}")
        assert data["status"] == "online"
        assert data["model_loaded"] is True

        # 2. Test Search endpoint
        query = "Leche Descremada"
        logger.info(f"Probando endpoint de búsqueda (GET /search?q={query})...")
        response = client.get(f"/search?q={query}")
        assert response.status_code == 200, "Search endpoint falló"
        results = response.json()
        
        logger.info(f"Se obtuvieron {len(results)} resultados de la búsqueda.")
        assert len(results) > 0, "No se retornó ningún resultado de búsqueda semántica"
        
        # Mostrar el primer resultado estructurado
        first_item = results[0]
        logger.info(f"Primer resultado mapeado:")
        logger.info(f"  - ID: {first_item['unified_id']}")
        logger.info(f"  - EAN: {first_item['ean']}")
        logger.info(f"  - Nombre: {first_item['brand']} {first_item['name']}")
        logger.info(f"  - Distancia: {first_item['distance']:.4f}")
        logger.info(f"  - Info Unidad: {first_item['unit_info']}")
        logger.info(f"  - Ofertas en Tiendas:")
        for store in first_item['available_at_stores']:
            logger.info(f"    * {store['store_id']}: ${store['base_price']} | En Stock: {store['in_stock']} | Promos: {len(store['promotions'])}")
            for promo in store['promotions']:
                logger.info(f"      - {promo['description']} (Tipo: {promo['type']})")

        # Validaciones de la especificación.
        #
        # min_price, image_url y unit_price se assertean explícitamente porque
        # /search era el único endpoint que NO pasaba por
        # _build_product_response() y no los mandaba. Que este test no los
        # mirara es por qué el hueco sobrevivió tanto: la respuesta era válida
        # contra el modelo Pydantic (los tres son Optional) y simplemente venía
        # incompleta.
        for campo in ("unified_id", "ean", "name", "shelf", "shelf_label",
                      "min_price", "image_url", "unit_info", "unit_price",
                      "distance", "store_count", "available_at_stores"):
            assert campo in first_item, f"/search no manda '{campo}'"

        assert first_item["min_price"] is not None
        assert first_item["shelf"], "el producto quedó sin góndola"

        logger.info("¡Todas las pruebas del API pasaron con éxito!")

def test_precio_de_membresia_solo_para_quien_la_declaro():
    """
    `_build_store_offer` no toca la base: se prueba sobre una fila armada a
    mano. La asimetría que protege es la de siempre — a quien no declaró Mi
    Carrefour no se le anuncia el precio de Mi Carrefour; a quien sí, se le
    muestra el mismo que después cobra el optimizador.
    """
    import json
    from src.api import _build_store_offer

    fila = {
        "store_id": "carrefour_online",
        "product_url": None,
        "base_price": 4599,
        "in_stock": True,
        "image_url": None,
        "promotions_json": json.dumps([{
            "promo_id": "crf-1",
            "type": "direct_discount",
            "description": "80% Off con Mi Carrefour",
            "discount_price_per_unit": 900,
            "requires_membership": "mi_carrefour",
        }]),
    }

    anonima = _build_store_offer(fila)
    assert anonima["promo_unit_price"] is None

    con_otra = _build_store_offer(fila, ["club_dia"])
    assert con_otra["promo_unit_price"] is None

    socio = _build_store_offer(fila, ["mi_carrefour"])
    assert socio["promo_unit_price"] == 900


def test_deals_ordenado_por_descuento():
    """Necesita Postgres poblado, igual que test_fastapi_endpoints."""
    with TestClient(app) as client:
        response = client.get("/deals?limit=8")
        assert response.status_code == 200
        deals = response.json()
        assert deals, "Un catálogo poblado siempre tiene algún descuento directo"

        descuentos = [d["discount_pct"] for d in deals]
        assert all(0 < d < 1 for d in descuentos)
        assert descuentos == sorted(descuentos, reverse=True)
        # El descuento tiene que verse en alguna oferta del producto: si no, la
        # card mostraría un "-60%" sin ningún precio tachado que lo respalde.
        for d in deals:
            assert any(o["promo_unit_price"] for o in d["available_at_stores"])
