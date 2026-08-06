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
        "Almacén": "Almacén",
        # Hojas tal como las escribe Carrefour. El match es exacto y sensible a
        # mayúsculas, así que sin estas entradas ("Dulce de leche" no es el
        # "Dulce de Leche" de arriba) sus productos caen a "Otros" y quedan
        # fuera de GET /category/{name}.
        "Dulce de leche": "Lácteos",
        "Aceites y vinagres": "Almacén",
        "Harinas comunes y leudantes": "Almacén"
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
            # El SKU de VTEX (`itemId`), que es lo que espera
            # /checkout/cart/add?sku= para armar un carrito por URL. Va aparte de
            # `store_sku` —que en las dos tiendas VTEX guarda el `productId`—
            # porque son identificadores distintos: en Carrefour el producto
            # 100650 es el item 17305. En Día coinciden por casualidad de su
            # catálogo, y confiar en esa coincidencia es lo que haría que la
            # próxima tienda VTEX arme carritos equivocados sin ningún síntoma.
            # NULL para las tiendas que no son VTEX (Coto).
            cur.execute("""
                ALTER TABLE store_products
                    ADD COLUMN IF NOT EXISTS store_item_id TEXT;
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
                        elif store_id == "carrefour_online":
                            # Carrefour también es VTEX: mismo 'commertialOffer' crudo,
                            # pero su hueco ListPrice/Price puede ser precio de socio
                            # (ver PromoTransformer.carrefour).
                            base_price, standardized_promos = PromoTransformer.carrefour(
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
                                -- unit_type va junto con total_volume_weight: los
                                -- dos salen de la misma llamada a
                                -- extract_real_volume() y describen una sola
                                -- medida. Actualizar el número sin la unidad
                                -- dejaba el peso nuevo pegado a la unidad vieja
                                -- del primer INSERT, y así quedaron en la base
                                -- cosas como "Fritolim 120 g" guardado en 'ml'.
                                -- Además congelaba en 'un' a todo producto cuyo
                                -- tamaño el parser no supo leer la primera vez,
                                -- volviendo inútil cualquier arreglo posterior
                                -- del parser sin borrar la tabla.
                                unit_type = EXCLUDED.unit_type,
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
                                unified_product_id, store_id, store_sku, store_item_id, product_url, base_price, in_stock, promotions_json, image_url
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (store_id, store_sku) DO UPDATE SET
                                store_item_id = EXCLUDED.store_item_id,
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
                            # Sólo lo mandan los scrapers VTEX. Va también en el
                            # DO UPDATE SET: una columna que falte ahí queda
                            # congelada en lo que escribió el primer INSERT, y un
                            # re-scrapeo es el único mecanismo del proyecto para
                            # corregir datos.
                            prod.get('store_item_id'),
                            prod['url'],
                            base_price,
                            prod['in_stock'],
                            json.dumps(standardized_promos),
                            prod.get('image_url')  # <-- Guardamos la URL de la imagen extraída del scraper
                        ))
            print("[DB] Guardado exitoso.")
        except Exception as e:
            print(f"[DB] Error: {e}")
    
    # Fracción de las filas de una tienda que un pruning puede borrar antes de
    # considerarse sospechoso. Un catálogo real se mueve de a poco; perder un
    # tercio de golpe es la firma de un scrapeo roto, no de productos discontinuados.
    MAX_PRUNE_RATIO = 0.30

    def prune_missing_store_products(self, store_id: str, seen_skus: set, dry_run: bool = False) -> dict:
        """
        Borra las filas de `store_id` cuyo SKU no apareció en el scrapeo actual.

        Sin esto un producto que la tienda discontinúa queda para siempre con
        `in_stock = TRUE`, y el optimizador lo sigue ofreciendo — incluso puede
        armar el split entero alrededor de algo que ya no se puede comprar.

        Sólo debe llamarse después de un scrapeo COMPLETO y exitoso de esa tienda:
        `seen_skus` tiene que ser el universo de lo que la tienda ofrece hoy. Con
        un recorrido parcial, todo lo que faltó recorrer parece discontinuado.

        Dos frenos, porque el costo de los dos errores no es simétrico: dejar una
        fila muerta de más molesta, borrar el catálogo entero rompe la app. (1) Un
        `seen_skus` vacío no borra nada — ese es exactamente el modo de falla que
        documenta CLAUDE.md, el hash de la persisted query de VTEX rotado
        devolviendo 200 con `errors` y cero productos. (2) Si el borrado se lleva
        más de MAX_PRUNE_RATIO de la tienda, se aborta y se avisa: es más probable
        que se haya roto el scraper a que la tienda haya discontinuado un tercio
        de su góndola.

        Devuelve {'deleted', 'orphans', 'skipped', 'reason'}.
        """
        resultado = {"deleted": 0, "orphans": 0, "skipped": False, "reason": None}

        if not seen_skus:
            resultado.update(skipped=True, reason="el scrapeo no devolvió ningún SKU")
            print(f"[DB] Pruning de '{store_id}' omitido: {resultado['reason']}.")
            return resultado

        try:
            with psycopg.connect(self.conn_string) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT count(*) FROM store_products WHERE store_id = %s", (store_id,)
                    )
                    total = cur.fetchone()[0]

                    cur.execute(
                        """
                        SELECT count(*) FROM store_products
                        WHERE store_id = %s AND store_sku <> ALL(%s)
                        """,
                        (store_id, list(seen_skus)),
                    )
                    obsoletas = cur.fetchone()[0]

                    if obsoletas == 0:
                        print(f"[DB] Pruning de '{store_id}': no hay filas obsoletas.")
                        return resultado

                    if total and (obsoletas / total) > self.MAX_PRUNE_RATIO:
                        resultado.update(
                            skipped=True,
                            reason=(f"borraría {obsoletas} de {total} filas "
                                    f"({obsoletas / total:.0%}), por encima del "
                                    f"{self.MAX_PRUNE_RATIO:.0%} permitido"),
                        )
                        print(f"[DB] ATENCIÓN: pruning de '{store_id}' abortado: "
                              f"{resultado['reason']}. Revisá el scraper antes de insistir.")
                        return resultado

                    cur.execute(
                        """
                        DELETE FROM store_products
                        WHERE store_id = %s AND store_sku <> ALL(%s)
                        """,
                        (store_id, list(seen_skus)),
                    )
                    resultado["deleted"] = cur.rowcount

                    # Un unified_product que se quedó sin ninguna oferta ya no lo
                    # vende nadie: dejarlo lo mantiene visible en /search y en el
                    # catálogo, con un precio que no existe.
                    cur.execute(
                        """
                        DELETE FROM unified_products u
                        WHERE NOT EXISTS (
                            SELECT 1 FROM store_products sp WHERE sp.unified_product_id = u.id
                        )
                        """
                    )
                    resultado["orphans"] = cur.rowcount

                    # El dry-run corre el borrado de verdad y lo deshace, en vez de
                    # estimarlo con un COUNT: así los dos números que informa son
                    # exactamente los que vería un run real. Contar los huérfanos
                    # sin borrar primero exigiría replicar en un SELECT la
                    # condición del DELETE, y esa copia es justo lo que haría que
                    # el dry-run mienta el día que alguien cambie una de las dos.
                    if dry_run:
                        conn.rollback()
                        print(f"[DB] Pruning de '{store_id}' (dry-run): borraría "
                              f"{resultado['deleted']} de {total} filas y "
                              f"{resultado['orphans']} productos sin ofertas.")
                        return resultado

            print(f"[DB] Pruning de '{store_id}': {resultado['deleted']} filas obsoletas "
                  f"borradas, {resultado['orphans']} productos sin ofertas eliminados.")
        except Exception as e:
            # Mismo criterio que save_store_products: no tumbar el scrapeo por
            # esto. Quedarse con filas de más es degradado, no roto.
            print(f"[DB] Error en el pruning de '{store_id}': {e}")
            resultado.update(skipped=True, reason=str(e))

        return resultado

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