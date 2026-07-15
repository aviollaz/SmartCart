# src/database.py
import psycopg
from psycopg.rows import dict_row
import json
from src.promotion_parser import PromoTransformer

class SmartCartDB:
    def __init__(self):
        self.conn_string = "host=localhost port=5432 dbname=smartcart user=smartuser password=smartpassword"

    def save_store_products(self, products: list, store_id: str):
        if not products:
            return

        print(f"[DB] Estandarizando y guardando {len(products)} productos en '{store_id}'...")
        try:
            with psycopg.connect(self.conn_string) as conn:
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

                        # 3. Guardar el Producto Unificado
                        cur.execute("""
                            INSERT INTO unified_products (id, ean, name, brand, unit_type)
                            VALUES (%s, %s, %s, %s, %s)
                            ON CONFLICT (id) DO UPDATE SET
                                name = EXCLUDED.name, brand = EXCLUDED.brand
                        """, (unified_id, prod['ean'], prod['name'], prod['brand'], prod['unit_type']))

                        # 4. Guardar la Instancia Comercial con el JSON de promos ya homogeneizado
                        cur.execute("""
                            INSERT INTO store_products (
                                unified_product_id, store_id, store_sku, product_url, base_price, in_stock, promotions_json
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (store_id, store_sku) DO UPDATE SET
                                base_price = EXCLUDED.base_price,
                                in_stock = EXCLUDED.in_stock,
                                promotions_json = EXCLUDED.promotions_json,
                                last_updated = CURRENT_TIMESTAMP
                        """, (
                            unified_id,
                            store_id,
                            prod['store_sku'],
                            prod['url'],
                            base_price,  # Guardamos el precio base limpio calculado
                            prod['in_stock'],
                            json.dumps(standardized_promos)  # Guardamos el formato unificado
                        ))
            print("[DB] Guardado exitoso.")
        except Exception as e:
            print(f"[DB] Error: {e}")