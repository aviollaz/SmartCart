import logging
import sys
import psycopg
from psycopg.rows import dict_row
from sentence_transformers import SentenceTransformer
from src.database import SmartCartDB

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def test_search(query_text: str):
    logger.info(f"Cargando modelo local...")
    model = SentenceTransformer("all-MiniLM-L6-v2")
    
    logger.info(f"Generando embedding para la consulta: '{query_text}'...")
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
            
    if not rows:
        logger.warning("No se encontraron productos indexados. ¿Corriste el pipeline de embeddings primero?")
        return
        
    logger.info("Resultados de la búsqueda semántica:")
    print(f"\nResultados para: '{query_text}'")
    print("-" * 80)
    for i, row in enumerate(rows, 1):
        print(f"{i:2d}. Distancia: {row['distance']:.4f} | EAN: {row['ean']} | {row['brand']} - {row['name']} (ID: {row['id']})")
    print("-" * 80)

if __name__ == "__main__":
    query = "Leche Descremada"
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
    test_search(query)
