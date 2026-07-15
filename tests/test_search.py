# tests/test_search.py
import logging
import psycopg
from psycopg.rows import dict_row
from sentence_transformers import SentenceTransformer
from src.database import SmartCartDB  # Importación limpia gracias a pytest.ini

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def test_semantic_search_query():
    query_text = "Puré de papas"
    logger.info(f"Cargando modelo local...")
    model = SentenceTransformer("all-MiniLM-L6-v2")
    
    logger.info(f"Generando embedding para la consulta de prueba: '{query_text}'...")
    emb = model.encode(query_text)
    vector_str = f"[{','.join(map(str, emb))}]"
    
    db = SmartCartDB()
    logger.info("Buscando en la base de datos con distancia de coseno...")
    
    with psycopg.connect(db.conn_string, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            # Consultamos los 10 vecinos más cercanos
            cur.execute("""
                SELECT id, ean, name, brand, name_embedding <=> %s AS distance
                FROM unified_products
                WHERE name_embedding IS NOT NULL
                ORDER BY distance ASC
                LIMIT 10
            """, (vector_str,))
            
            rows = cur.fetchall()
            
    # Validación del test de búsqueda
    assert rows, "La consulta no retornó productos. Verificá si corriste el pipeline de embeddings y tenés datos cargados."
    
    logger.info("Resultados de la búsqueda semántica obtenidos exitosamente:")
    print(f"\nResultados para: '{query_text}'")
    print("-" * 80)
    for i, row in enumerate(rows, 1):
        print(f"{i:2d}. Distancia: {row['distance']:.4f} | EAN: {row['ean']} | {row['brand']} - {row['name']} (ID: {row['id']})")
        # Aseguramos que la distancia coseno se mantenga dentro de un rango matemático válido [0, 2]
        assert 0.0 <= row['distance'] <= 2.0, "La distancia de coseno calculada no es válida"
    print("-" * 80)