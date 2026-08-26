import time
import logging
from typing import List, Tuple
import psycopg
from sentence_transformers import SentenceTransformer
from src.database import SmartCartDB
from src.schema import ensure_schema

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
        Aplica el DDL idempotente de src/schema.py, que incluye la extensión
        pgvector, la columna `name_embedding` y su índice HNSW.

        Antes esas tres sentencias vivían acá sueltas. Se movieron con el resto del
        esquema: el DDL repartido era lo que hacía que ninguna parte del repo
        pudiera contestar qué columnas tiene la base.
        """
        logger.info("Asegurando el esquema (pgvector, name_embedding, indice HNSW)...")
        try:
            with psycopg.connect(self.db.conn_string) as conn:
                ensure_schema(conn)
            logger.info("Esquema al dia.")
        except Exception as e:
            logger.error(f"Error al asegurar el esquema: {e}")
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

    def generate_and_save_embeddings(self, batch_size: int = 64) -> dict:
        """
        Genera los embeddings para todos los productos pendientes y los persiste por lotes (batches).

        Devuelve {'pending', 'embedded', 'batches_ok', 'batches_failed'}. Los
        errores por lote se siguen tolerando (un lote caído no aborta el resto),
        pero ahora se cuentan: sin ese número, "no había nada pendiente" y
        "fallaron los doce lotes" se ven exactamente igual desde afuera, y el
        síntoma —productos en la base que GET /search no encuentra— aparece
        recién días después.
        """
        stats = {"pending": 0, "embedded": 0, "batches_ok": 0, "batches_failed": 0}

        # Primero aseguramos extensión e índice
        self.ensure_vector_extension_and_index()

        pending_products = self.get_products_pending_embeddings()
        if not pending_products:
            logger.info("No hay productos pendientes para generar embeddings.")
            return stats

        total_products = len(pending_products)
        stats["pending"] = total_products
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
                
                stats["batches_ok"] += 1
                stats["embedded"] += len(batch)
                logger.info(f"Lote {i // batch_size + 1} guardado correctamente ({len(batch)} productos).")
            except Exception as e:
                stats["batches_failed"] += 1
                logger.error(f"Error procesando lote {i // batch_size + 1}: {e}")
                logger.info("Intentando continuar con el siguiente lote para tolerancia a fallos...")
                time.sleep(1)

        logger.info(
            "Pipeline de embeddings finalizado: %d/%d productos embebidos, %d lote(s) fallidos.",
            stats["embedded"], stats["pending"], stats["batches_failed"],
        )
        return stats

if __name__ == "__main__":
    pipeline = EmbeddingPipeline()
    # Ejecutamos la generación y persistencia de embeddings
    pipeline.generate_and_save_embeddings(batch_size=64)
