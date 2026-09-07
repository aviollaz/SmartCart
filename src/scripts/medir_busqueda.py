"""
Línea de base de la calidad de `/search`, en un comando.

Uso:
    python -m src.scripts.medir_busqueda
    python -m src.scripts.medir_busqueda --modelo paraphrase-multilingual-MiniLM-L12-v2

Existe por el ítem 4 de `docs/TODO.md`, que dice "medir antes de migrar" y hasta
ahora no tenía con qué. Mide lo único que le importa al usuario —si los
resultados son del tipo de producto que pidió— y no la distancia coseno, que es
la trampa de este ítem: un modelo puede bajar todas las distancias y equivocarse
en los mismos casos.

El criterio de acierto es la góndola (`unified_products.shelf`), que sirve
justamente porque es independiente del modelo: sale de `src/shelves.py` y la
escriben los tres scrapers por igual.

**Ojo con `--modelo`.** Compara un modelo nuevo contra embeddings generados con
el VIEJO, así que el resultado no significa nada por sí solo: sirve para el paso
de migración, después de regenerar la columna. Para la línea de base se corre sin
argumentos.
"""
import argparse
import os

import psycopg
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

from src.schema import resolve_conn_string

# Diez queries de una palabra, que es como la gente busca en un supermercado, y
# la góndola que cualquiera esperaría de vuelta. Ocho las acierta el modelo
# actual; `leche` y `arroz` son las que fallan, y no por casualidad: son las dos
# palabras que aparecen dentro del nombre de productos de OTRA góndola ("dulce
# de leche", "alfajor de arroz"). Si se agregan queries, que sea con ese criterio
# —casos donde la respuesta correcta es obvia— y no buscando bajar el promedio.
QUERIES = [
    ("leche", "leches"),
    ("arroz", "arroz-y-legumbres"),
    ("fideos", "pastas-secas"),
    ("aceite", "aceites-y-aderezos"),
    ("yerba", "yerba-mate"),
    ("cafe", "cafe"),
    ("cerveza", "cervezas"),
    ("yogur", "yogures"),
    ("queso", "quesos"),
    ("galletitas", "galletitas"),
]

TOP_N = 10

# El mismo pool y el mismo ef_search que usa /search, para que lo que se mide sea
# lo que el usuario recibe. Ver los comentarios de SEARCH_POOL_SIZE en src/api.py.
SQL = """
    WITH pool AS (
        SELECT id, name, shelf, name_embedding <=> %s AS distance
        FROM unified_products
        WHERE name_embedding IS NOT NULL
        ORDER BY distance ASC
        LIMIT 100
    )
    SELECT name, shelf, distance FROM pool ORDER BY distance LIMIT %s
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Mide la relevancia de /search.")
    parser.add_argument("--modelo", default="all-MiniLM-L6-v2",
                        help="Modelo de sentence-transformers a usar para la query.")
    parser.add_argument("--verbose", action="store_true",
                        help="Muestra los 3 primeros resultados de cada query.")
    args = parser.parse_args()

    load_dotenv()
    modelo = SentenceTransformer(args.modelo)

    aciertos_totales = 0
    print(f"modelo: {args.modelo}\n")

    with psycopg.connect(resolve_conn_string()) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('hnsw.ef_search', '200', false)")

            for query, gondola in QUERIES:
                vector = modelo.encode(query)
                literal = "[" + ",".join(map(str, vector)) + "]"
                cur.execute(SQL, (literal, TOP_N))
                filas = cur.fetchall()

                aciertos = sum(1 for _, shelf, _ in filas if shelf == gondola)
                aciertos_totales += aciertos
                marca = "  " if aciertos >= TOP_N - 1 else "<-"
                print(f"{marca} {query:12} {aciertos:2}/{TOP_N} en '{gondola}'"
                      f"   d@1={filas[0][2]:.3f}   {filas[0][0][:44]}")

                if args.verbose:
                    for name, shelf, dist in filas[:3]:
                        print(f"       {dist:.3f}  [{shelf}] {name[:52]}")

    total = len(QUERIES) * TOP_N
    print(f"\ntotal: {aciertos_totales}/{total} ({aciertos_totales / total:.0%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
