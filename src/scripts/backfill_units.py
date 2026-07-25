"""
Recalcula unit_type / total_volume_weight de los productos ya scrapeados,
parseando el tamaño real desde el nombre (ver src/size_parser.py).

Uso: python -m src.scripts.backfill_units
"""
import psycopg
from psycopg.rows import dict_row
from src.database import SmartCartDB
from src.size_parser import extract_real_volume


def backfill_units():
    db = SmartCartDB()
    updated = 0

    with psycopg.connect(db.conn_string, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, unit_type, total_volume_weight FROM unified_products")
            products = cur.fetchall()

            for p in products:
                new_weight, new_unit = extract_real_volume(p["name"])

                current_weight = float(p["total_volume_weight"]) if p["total_volume_weight"] is not None else None
                if new_unit == p["unit_type"] and current_weight == new_weight:
                    continue

                cur.execute(
                    "UPDATE unified_products SET unit_type = %s, total_volume_weight = %s WHERE id = %s",
                    (new_unit, new_weight, p["id"]),
                )
                updated += 1

        conn.commit()

    print(f"[BACKFILL] {updated}/{len(products)} productos actualizados.")


if __name__ == "__main__":
    backfill_units()
