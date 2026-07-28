# src/database.py
import psycopg
from psycopg.rows import dict_row
import json
from src.promotion_parser import PromoTransformer

class SmartCartDB:
    # Diccionario de normalización (Mapea categorías crudas de los supers a las tuyas maestras)
    CATEGORY_MAP = {
        "Leches": "Lácteos",
        "Lácteos y Frescos": "Lácteos",
        "Quesos": "Lácteos",
        "Dulce de Leche": "Lácteos",
        "Alfajores": "Golosinas",
        "Golosinas y Chocolates": "Golosinas",
        "Harinas": "Almacén",
        "Aceites": "Almacén",
        "Almacén": "Almacén"
    }

    def __init__(self):
        self.conn_string = "host=localhost port=5432 dbname=smartcart user=smartuser password=smartpassword"
        self._schema_ready = False

    def _ensure_schema(self, conn):
        """
        Agrega de forma idempotente las columnas de tags y atributos dietarios.
        Mismo patrón ad-hoc que usa EmbeddingPipeline para name_embedding: el
        esquema base se creó a mano y no hay migraciones en el proyecto.
        """
        if self._schema_ready:
            return

        with conn.cursor() as cur:
            cur.execute("""
                ALTER TABLE unified_products
                    ADD COLUMN IF NOT EXISTS tags TEXT[],
                    ADD COLUMN IF NOT EXISTS is_gluten_free BOOLEAN DEFAULT FALSE,
                    ADD COLUMN IF NOT EXISTS is_vegan BOOLEAN DEFAULT FALSE;
            """)
            # GIN es el índice que soporta el operador de solapamiento (&&)
            # con el que api.py filtra "misma góndola".
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_unified_products_tags
                ON unified_products USING gin (tags);
            """)

        self._schema_ready = True

    def save_store_products(self, products: list, store_id: str):
        if not products:
            return

        print(f"[DB] Estandarizando y guardando {len(products)} productos en '{store_id}'...")
        try:
            with psycopg.connect(self.conn_string) as conn:
                self._ensure_schema(conn)
                with conn.cursor() as cur:
                    for prod in products:
                        # 1. Resolver identificador único
                        unified_id = f"prod_{prod['ean']}" if prod['ean'] else f"{store_id}_{prod['store_sku']}"
                        
                        # 2. TRANSFORMACIÓN: Normalizamos precio y promos según el origen
                        base_price = prod['base_price']
                        standardized_promos = []

                        if store_id == "coto_online":
                            standardized_promos = PromoTransformer.coto(prod['raw_promos'])
                        elif store_id == "dia_online":
                            # Para día, raw_promos contiene el 'commertialOffer' crudo de VTEX
                            base_price, standardized_promos = PromoTransformer.dia(
                                prod['raw_promos'], 
                                prod['store_sku']
                            )

                        # 2.5 TRANSFORMACIÓN: Normalizar la categoría del producto
                        raw_category = prod.get('category', 'Sin Categoría')
                        normalized_category = self.CATEGORY_MAP.get(raw_category, "Otros")

                        # 3. Guardar el Producto Unificado (Incluye la categoría normalizada)
                        # Los flags dietarios se PISAN en cada scrapeo en vez de
                        # acumularse con OR. Acumular preservaba la evidencia de
                        # ambas tiendas, pero volvía los flags monotónicos: un
                        # falso positivo no se podía corregir nunca, ni siquiera
                        # arreglando el parser. Para un campo del que depende
                        # alguien celíaco eso es inaceptable, y la asimetría
                        # juega a favor de pisar: un FALSE de más solo significa
                        # "sin evidencia" (seguro), mientras que un TRUE de más
                        # es el error peligroso.
                        cur.execute("""
                            INSERT INTO unified_products (
                                id, ean, name, brand, unit_type, category, total_volume_weight,
                                tags, is_gluten_free, is_vegan
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (id) DO UPDATE SET
                                name = EXCLUDED.name,
                                brand = EXCLUDED.brand,
                                category = EXCLUDED.category,
                                total_volume_weight = EXCLUDED.total_volume_weight,
                                tags = EXCLUDED.tags,
                                is_gluten_free = EXCLUDED.is_gluten_free,
                                is_vegan = EXCLUDED.is_vegan
                        """, (
                            unified_id,
                            prod['ean'],
                            prod['name'],
                            prod['brand'],
                            prod['unit_type'],
                            normalized_category,
                            prod['total_volume_weight'],
                            prod.get('tags') or None,
                            bool(prod.get('is_gluten_free', False)),
                            bool(prod.get('is_vegan', False))))

                        # 4. Guardar la Instancia Comercial con el JSON de promos y la IMAGEN
                        cur.execute("""
                            INSERT INTO store_products (
                                unified_product_id, store_id, store_sku, product_url, base_price, in_stock, promotions_json, image_url
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (store_id, store_sku) DO UPDATE SET
                                product_url = EXCLUDED.product_url,
                                base_price = EXCLUDED.base_price,
                                in_stock = EXCLUDED.in_stock,
                                promotions_json = EXCLUDED.promotions_json,
                                image_url = EXCLUDED.image_url,
                                last_updated = CURRENT_TIMESTAMP
                        """, (
                            unified_id,
                            store_id,
                            prod['store_sku'],
                            prod['url'],
                            base_price,  
                            prod['in_stock'],
                            json.dumps(standardized_promos),  
                            prod.get('image_url')  # <-- Guardamos la URL de la imagen extraída del scraper
                        ))
            print("[DB] Guardado exitoso.")
        except Exception as e:
            print(f"[DB] Error: {e}")
    
    def get_market_prices_for_cart(self, unified_ids: list) -> list:
        """
        Retorna la información de precios base, stock, promociones y fotos
        de todas las tiendas disponibles para una lista de productos unificados.
        """
        if not unified_ids:
            return []

        query = """
            SELECT 
                unified_product_id,
                store_id,
                base_price,
                in_stock,
                promotions_json,
                image_url
            FROM store_products
            WHERE unified_product_id = ANY(%s) AND in_stock = TRUE;
        """
        
        try:
            with psycopg.connect(self.conn_string, row_factory=dict_row) as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (unified_ids,))
                    return cur.fetchall()
        except Exception as e:
            print(f"[DB] Error al recuperar precios para el carrito: {e}")
            return []