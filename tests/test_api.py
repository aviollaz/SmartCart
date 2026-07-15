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

        # Validaciones de la especificación
        assert "unified_id" in first_item
        assert "ean" in first_item
        assert "name" in first_item
        assert "unit_info" in first_item
        assert "distance" in first_item
        assert "available_at_stores" in first_item

        logger.info("¡Todas las pruebas del API pasaron con éxito!")