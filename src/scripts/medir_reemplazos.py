"""
Los reemplazos por defecto de /compare, góndola por góndola, para revisarlos a ojo.

Uso:
    python -m src.scripts.medir_reemplazos                  # todas las góndolas
    python -m src.scripts.medir_reemplazos --gondola leches --muestra 10

Por cada góndola toma una muestra de productos y, por cada súper que no los
vende, imprime el reemplazo que elegiría /compare (`find_replacements`, el
mismo código). Existe para decidir qué góndolas necesitan atributos en
src/attributes.py: una góndola donde los reemplazos salen bien no necesita
tabla. Solo lee.
"""
import argparse

from dotenv import load_dotenv

from src.database import SmartCartDB
from src.db_pool import connection
from src.flattener import flatten_cart_prices
from src.shelves import SHELVES
from src.store_comparison import find_replacements
from src.stores import STORES


def main() -> int:
    parser = argparse.ArgumentParser(description="Lista los reemplazos por defecto de /compare.")
    parser.add_argument("--gondola", choices=sorted(SHELVES), help="una sola góndola (default: todas)")
    parser.add_argument("--muestra", type=int, default=5, help="productos por góndola (default: 5)")
    args = parser.parse_args()

    load_dotenv()
    stores = [s.id for s in STORES]
    with connection(SmartCartDB().conn_string) as conn, conn.cursor() as cur:
        cur.execute("SELECT setseed(0.42)")
        for shelf in [args.gondola] if args.gondola else sorted(SHELVES):
            # Productos que le faltan a algún súper: los únicos que se reemplazan.
            cur.execute("""
                SELECT u.id, u.name FROM unified_products u
                JOIN store_products sp ON sp.unified_product_id = u.id AND sp.in_stock
                WHERE u.shelf = %s
                GROUP BY u.id, u.name HAVING count(*) < %s
                ORDER BY random() LIMIT %s
            """, (shelf, len(stores), args.muestra))
            sample = cur.fetchall()
            if not sample:
                continue
            print(f"\n=== {shelf}")
            cart = [{"unified_id": row["id"], "quantity": 1} for row in sample]
            flat = flatten_cart_prices(cart)
            options = find_replacements(cur, cart, flat, stores)
            for row in sample:
                print(f"  {row['name']}")
                for store in stores:
                    if store in flat.get(row["id"], {}):
                        continue
                    chosen = (options.get(store, {}).get(row["id"]) or [None])[0]
                    print(f"      {store:18} -> {chosen['name'] if chosen else '(no lo tiene)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
