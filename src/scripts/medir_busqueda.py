"""
Línea de base de la calidad de `/search`, en un comando.

Uso:
    python -m src.scripts.medir_busqueda
    python -m src.scripts.medir_busqueda --modo hibrido
    python -m src.scripts.medir_busqueda --modelo paraphrase-multilingual-MiniLM-L12-v2

Existe por el ítem 4 de `docs/TODO.md`, que dice "medir antes de migrar" y hasta
ahora no tenía con qué. Mide lo único que le importa al usuario —si los
resultados son del tipo de producto que pidió— y no la distancia coseno, que es
la trampa de este ítem: un modelo puede bajar todas las distancias y equivocarse
en los mismos casos.

El criterio de acierto es la góndola (`unified_products.shelf`), que sirve
justamente porque es independiente del modelo: sale de `src/shelves.py` y la
escriben los tres scrapers por igual.

**Mide el mismo SQL que `/search`** (`src/search.py::search_rows`), bonus por
disponibilidad incluido. `--modo` elige entre el denso de siempre y el híbrido
(ítem de búsqueda híbrida del TODO); el gate para enchufar el híbrido es que no
pierda en el total ni rompa ninguna query que hoy da 10/10.

**Ojo con `--modelo`.** Compara un modelo nuevo contra embeddings generados con
el VIEJO, así que el resultado no significa nada por sí solo: sirve para el paso
de migración, después de regenerar la columna. Para la línea de base se corre sin
argumentos.
"""
import argparse
import os

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row
from sentence_transformers import SentenceTransformer

from src.embeddings import DEFAULT_EMBEDDING_MODEL
from src.schema import resolve_conn_string
from src.search import DEFAULT_SEARCH_MODE, SEARCH_MODES, search_rows

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

# Queries precisas —marca, a veces con tamaño—, que es donde se espera que la
# mitad léxica le gane al embedding: un nombre propio como "playadito" no tiene
# vecinos semánticos útiles. Van aparte para que el total de arriba siga siendo
# comparable contra las mediciones anteriores (79/100 con el modelo actual).
QUERIES_PRECISAS = [
    ("coca cola 2.25", "gaseosas"),
    ("oreo", "galletitas"),
    ("playadito", "yerba-mate"),
    ("quilmes", "cervezas"),
    ("fideos matarazzo", "pastas-secas"),
]

TOP_N = 10

def main() -> int:
    parser = argparse.ArgumentParser(description="Mide la relevancia de /search.")
    parser.add_argument("--modelo", default=DEFAULT_EMBEDDING_MODEL,
                        help="Modelo de sentence-transformers a usar para la query.")
    parser.add_argument("--modo", choices=SEARCH_MODES, default=DEFAULT_SEARCH_MODE,
                        help="denso (el de siempre) o hibrido (suma la mitad léxica).")
    parser.add_argument("--verbose", action="store_true",
                        help="Muestra los 3 primeros resultados de cada query.")
    args = parser.parse_args()

    load_dotenv()
    modelo = SentenceTransformer(args.modelo)

    print(f"modelo: {args.modelo}   modo: {args.modo}\n")

    with psycopg.connect(resolve_conn_string(), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            for titulo, queries in (("una palabra", QUERIES), ("precisas", QUERIES_PRECISAS)):
                aciertos_totales = 0
                print(f"-- {titulo}")
                for query, gondola in queries:
                    vector = modelo.encode(query)
                    literal = "[" + ",".join(map(str, vector)) + "]"
                    filas = search_rows(cur, literal, query, TOP_N, mode=args.modo)

                    aciertos = sum(1 for f in filas if f["shelf"] == gondola)
                    aciertos_totales += aciertos
                    marca = "  " if aciertos >= TOP_N - 1 else "<-"
                    primera = filas[0] if filas else {"distance": float("nan"), "name": "-"}
                    print(f"{marca} {query:18} {aciertos:2}/{TOP_N} en '{gondola}'"
                          f"   d@1={float(primera['distance']):.3f}   {primera['name'][:44]}")

                    if args.verbose:
                        for f in filas[:3]:
                            print(f"       {float(f['distance']):.3f}  [{f['shelf']}] {f['name'][:52]}")

                total = len(queries) * TOP_N
                print(f"total: {aciertos_totales}/{total} ({aciertos_totales / total:.0%})\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
