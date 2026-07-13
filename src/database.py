import psycopg
from psycopg.rows import dict_row
import json

class SmartCartDB:
    def __init__(self):
        # Usamos las mismas credenciales que configuramos en el docker-compose
        self.conn_string = "host=localhost port=5432 dbname=smartcart user=smartuser password=smartpassword"

    def save_store_products(self, products: list, store_id: str):
        """
        Persiste los productos en PostgreSQL vinculándolos al store_id correspondiente.
        """
        if not products:
            return

        print(f"[DB] Persistiendo {len(products)} productos en la tienda '{store_id}'...")
        try:
            with psycopg.connect(self.conn_string) as conn:
                with conn.cursor() as cur:
                    for prod in products:
                        # Identificador unificado
                        unified_id = f"prod_{prod['ean']}" if prod['ean'] else f"{store_id}_{prod['store_sku']}"
                        
                        cur.execute("""
                            INSERT INTO unified_products (id, ean, name, brand, unit_type)
                            VALUES (%s, %s, %s, %s, %s)
                            ON CONFLICT (id) DO UPDATE SET
                                name = EXCLUDED.name, brand = EXCLUDED.brand
                        """, (unified_id, prod['ean'], prod['name'], prod['brand'], prod['unit_type']))

                        cur.execute("""
                            INSERT INTO store_products (
                                unified_product_id, store_id, store_sku, product_url, base_price, in_stock, promotions_json
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (store_id, store_sku) DO UPDATE SET
                                base_price = EXCLUDED.base_price,
                                in_stock = EXCLUDED.in_stock,
                                last_updated = CURRENT_TIMESTAMP
                        """, (
                            unified_id,
                            store_id, # <-- AHORA ES DINÁMICO ('coto_online' o 'dia_online')
                            prod['store_sku'],
                            prod['url'],
                            prod['base_price'],
                            prod['in_stock'],
                            json.dumps(prod['raw_promos'])
                        ))
            print("[DB] Guardado exitoso.")
        except Exception as e:
            print(f"[DB] Error: {e}")

if __name__ == "__main__":
    # Prueba rápida de conexión
    try:
        db = SmartCartDB()
        with psycopg.connect(db.conn_string) as conn:
            print("[DB] Conexión exitosa a PostgreSQL en Docker!")
    except Exception as e:
        print(f"[DB] Error de conexión: {e}")