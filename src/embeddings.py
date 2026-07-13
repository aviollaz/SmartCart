import time
import logging
from typing import List, Tuple
import psycopg
from sentence_transformers import SentenceTransformer
from src.database import SmartCartDB

# Configuración de Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

class EmbeddingPipeline:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        logger.info("Inicializando SmartCartDB...")
        self.db = SmartCartDB()
        logger.info(f"Cargando modelo local '{model_name}' con sentence-transformers...")
        # Carga local del modelo (descarga automáticamente la primera vez y lo cachea)
        self.model = SentenceTransformer(model_name)
        logger.info("Modelo cargado exitosamente.")

    def ensure_vector_extension_and_index(self):
        """
        Asegura que la extensión vector esté habilitada y que exista el índice HNSW para búsquedas rápidas.
        """
        logger.info("Asegurando la existencia de la extensión pgvector y el índice HNSW...")
        try:
            with psycopg.connect(self.db.conn_string) as conn:
                with conn.cursor() as cur:
                    # Habilitar la extensión pgvector
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                    
                    # Asegurar que la columna name_embedding exista (ya existe pero por las dudas)
                    cur.execute("""
                        ALTER TABLE unified_products 
                        ADD COLUMN IF NOT EXISTS name_embedding vector(384);
                    """)
                    
                    # Crear el índice espacial HNSW con distancia coseno
                    logger.info("Creando o verificando índice HNSW en unified_products(name_embedding)...")
                    cur.execute("""
                        CREATE INDEX IF NOT EXISTS idx_unified_products_name_embedding_hnsw
                        ON unified_products USING hnsw (name_embedding vector_cosine_ops);
                    """)
                conn.commit()
            logger.info("Extensión e índice configurados correctamente.")
        except Exception as e:
            logger.error(f"Error al asegurar extensión e índice: {e}")
            raise

    def get_products_pending_embeddings(self) -> List[Tuple[str, str, str]]:
        """
        Obtiene los productos unificados que no tienen embedding generado.
        Retorna una lista de tuplas (id, name, brand).
        """
        logger.info("Buscando productos pendientes de embeddings...")
        try:
            with psycopg.connect(self.db.conn_string) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT id, name, brand 
                        FROM unified_products 
                        WHERE name_embedding IS NULL
                    """)
                    results = cur.fetchall()
            logger.info(f"Se encontraron {len(results)} productos pendientes.")
            return results
        except Exception as e:
            logger.error(f"Error al buscar productos pendientes: {e}")
            return []

    def generate_and_save_embeddings(self, batch_size: int = 64):
        """
        Genera los embeddings para todos los productos pendientes y los persiste por lotes (batches).
        """
        # Primero aseguramos extensión e índice
        self.ensure_vector_extension_and_index()

        pending_products = self.get_products_pending_embeddings()
        if not pending_products:
            logger.info("No hay productos pendientes para generar embeddings.")
            return

        total_products = len(pending_products)
        logger.info(f"Comenzando procesamiento de {total_products} productos en lotes de {batch_size}...")

        for i in range(0, total_products, batch_size):
            batch = pending_products[i:i + batch_size]
            logger.info(f"Procesando lote {i // batch_size + 1} (items {i} a {i + len(batch)})...")
            
            # Preparar textos para el modelo.
            # Combinamos marca y nombre para enriquecer el contexto semántico (ej: 'Paty Hamburguesas Clásicas')
            texts_to_embed = []
            batch_ids = []
            
            for prod_id, name, brand in batch:
                combined_text = f"{brand} {name}" if brand else name
                texts_to_embed.append(combined_text)
                batch_ids.append(prod_id)

            try:
                # Generar embeddings localmente
                embeddings = self.model.encode(texts_to_embed, show_progress_bar=False)
                
                # Guardar en la base de datos
                with psycopg.connect(self.db.conn_string) as conn:
                    with conn.cursor() as cur:
                        # Preparamos los datos para actualización por lotes
                        update_data = []
                        for prod_id, emb in zip(batch_ids, embeddings):
                            # Convertimos el array de numpy a un string formato pgvector "[val1, val2, ...]"
                            vector_str = f"[{','.join(map(str, emb))}]"
                            update_data.append((vector_str, prod_id))
                        
                        # Ejecutamos bulk update
                        cur.executemany("""
                            UPDATE unified_products
                            SET name_embedding = %s
                            WHERE id = %s
                        """, update_data)
                    conn.commit()
                
                logger.info(f"Lote {i // batch_size + 1} guardado correctamente ({len(batch)} productos).")
            except Exception as e:
                logger.error(f"Error procesando lote {i // batch_size + 1}: {e}")
                logger.info("Intentando continuar con el siguiente lote para tolerancia a fallos...")
                time.sleep(1)

        logger.info("Pipeline de embeddings finalizado.")

if __name__ == "__main__":
    pipeline = EmbeddingPipeline()
    # Ejecutamos la generación y persistencia de embeddings
    pipeline.generate_and_save_embeddings(batch_size=64)
