# src/schema.py
"""
El esquema de Postgres, en un solo lugar.

Antes de este módulo el DDL estaba repartido en tres archivos y ninguno creaba
las tablas base: `SmartCartDB._ensure_schema` agregaba columnas sueltas,
`EmbeddingPipeline.ensure_vector_extension_and_index` la extensión y el índice
HNSW, y `scraper_telemetry` su propia tabla. `unified_products` y
`store_products` se habían creado a mano contra el Postgres de desarrollo y **no
existían en ningún lado del repo**: ni un .sql, ni un initdb, ni una línea de
Python. Un clone nuevo no arrancaba, y los defaults de columna eran
indescubribles desde el código — que es exactamente cómo `units_per_pack` llegó
a afirmar DEFAULT 1 ("no es un pack") sobre 287 productos que sí lo eran, sin
que nadie pudiera verlo leyendo el proyecto.

Sigue sin haber migraciones versionadas, y es una decisión: el DDL entero es
**idempotente y declarativo**. CREATE TABLE IF NOT EXISTS para lo base, ADD
COLUMN IF NOT EXISTS para todo lo que se agregó después, CREATE INDEX IF NOT
EXISTS para los índices. Correrlo sobre una base virgen la crea; correrlo sobre
la base de desarrollo de hace seis meses la converge; correrlo dos veces
seguidas no hace nada la segunda. Es el patrón que `scraper_telemetry` ya usaba
bien, aplicado a las tres tablas.

**Este módulo no borra nada.** Los DROP COLUMN de columnas que dejaron de usarse
viven en `src/scripts/migrate_shelves.py`, que se corre a mano una vez: un módulo
que borra datos al importarse es la clase de cosa que no se deshace. Una columna
vieja que quedó en la base simplemente no aparece acá, y ningún código la lee.

Orden de las sentencias: extensión -> tablas -> columnas -> índices. Importa,
porque `unified_products.name_embedding` es de tipo vector(384) y ese tipo no
existe hasta que corre el CREATE EXTENSION.
"""
import logging
import os

import psycopg

logger = logging.getLogger(__name__)

# El docker-compose local. Vive acá y no en `SmartCartDB` porque el DDL tiene que
# poder correrse sin instanciar el repositorio (python -m src.schema), y porque
# así hay una sola definición de "a qué base apunta el proyecto".
#
# DATABASE_URL existe para que el pipeline desatendido apunte a otra instancia sin
# tocar código. Se lee dentro de la función y no a nivel módulo porque
# load_dotenv() corre en el entry point, después de importar.
DEFAULT_CONN_STRING = (
    "host=localhost port=5432 dbname=smartcart user=smartuser password=smartpassword"
)


def resolve_conn_string(conn_string: str | None = None) -> str:
    """La cadena de conexión efectiva: explícita > DATABASE_URL > docker-compose."""
    return conn_string or os.getenv("DATABASE_URL") or DEFAULT_CONN_STRING


# --------------------------------------------------------------------------
# DDL
# --------------------------------------------------------------------------

_EXTENSIONS = (
    "CREATE EXTENSION IF NOT EXISTS vector;",
)

# Las tablas tal como están en la base viva, menos las columnas que ya no lee
# nadie. Los tipos son los originales (VARCHAR con largos, NUMERIC(10,2)): no se
# "modernizan" a TEXT porque el CREATE sólo corre en bases nuevas y el objetivo es
# que una base nueva y una vieja sean la misma base, no dos parecidas.
_TABLES = (
    # `shelf` es la góndola canónica de src/shelves.py, y es la ÚNICA noción de
    # categoría del proyecto. Reemplazó a dos columnas que decían lo mismo peor:
    # `category` (4 buckets de un dict de 12 claves, con el 80% del catálogo
    # cayendo en "Otros") y `tags` (la ruta de taxonomía de UNA tienda, que al ser
    # por EAN se pisaba entre tiendas y ganaba la última que escribía).
    """
    CREATE TABLE IF NOT EXISTS unified_products (
        id                  VARCHAR(50)  PRIMARY KEY,
        ean                 VARCHAR(13)  UNIQUE,
        name                VARCHAR(255) NOT NULL,
        brand               VARCHAR(100),
        shelf               TEXT,
        unit_type           VARCHAR(10),
        total_volume_weight NUMERIC(10,2),
        name_embedding      vector(384),
        is_gluten_free      BOOLEAN DEFAULT FALSE,
        is_vegan            BOOLEAN DEFAULT FALSE
    );
    """,
    # `last_updated` lleva su DEFAULT declarado acá. En la base hecha a mano el
    # default existía pero era invisible desde el repo, y el upsert de
    # save_store_products sólo lo escribe en la rama UPDATE — o sea que el valor de
    # una fila recién insertada dependía de algo que no estaba escrito en ningún
    # lado.
    """
    CREATE TABLE IF NOT EXISTS store_products (
        id                 SERIAL PRIMARY KEY,
        unified_product_id VARCHAR(50)   REFERENCES unified_products(id),
        store_id           VARCHAR(50)   NOT NULL,
        store_sku          VARCHAR(100)  NOT NULL,
        product_url        TEXT,
        base_price         NUMERIC(10,2) NOT NULL,
        in_stock           BOOLEAN   DEFAULT TRUE,
        promotions_json    JSONB,
        last_updated       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        image_url          TEXT,
        store_item_id      TEXT,
        source_category    TEXT,
        CONSTRAINT unique_store_sku UNIQUE (store_id, store_sku)
    );
    """,
    # Una fila por PASO por corrida del pipeline. Se abre en RUNNING antes del
    # trabajo y se cierra al terminar: un proceso que muere de golpe deja la fila
    # en RUNNING, que es justo la señal que un INSERT final perdería. Ver
    # src/scraper_telemetry.py.
    """
    CREATE TABLE IF NOT EXISTS scraper_execution_logs (
        id                   BIGSERIAL PRIMARY KEY,
        run_id               UUID        NOT NULL,
        supermercado         TEXT        NOT NULL,
        start_time           TIMESTAMPTZ NOT NULL,
        end_time             TIMESTAMPTZ,
        duration_seconds     NUMERIC(10,2),
        items_scraped        INTEGER     NOT NULL DEFAULT 0,
        categories_ok        INTEGER     NOT NULL DEFAULT 0,
        categories_failed    INTEGER     NOT NULL DEFAULT 0,
        categories_empty     INTEGER     NOT NULL DEFAULT 0,
        pruned_rows          INTEGER,
        pruned_orphans       INTEGER,
        prune_skipped_reason TEXT,
        status               TEXT        NOT NULL,
        error_message        TEXT,
        hostname             TEXT,
        CONSTRAINT scraper_execution_logs_status_chk
            CHECK (status IN ('RUNNING','SUCCESS','PARTIAL','FAILED'))
    );
    """,
)

# Lo que se agregó después del esquema base. Redundante en una base nueva (el
# CREATE de arriba ya las trae) y necesario en una vieja: es lo que hace que las
# dos converjan al mismo lugar. Una columna nueva se agrega en los dos sitios, en
# la misma edición.
_COLUMNS = (
    """
    ALTER TABLE unified_products
        ADD COLUMN IF NOT EXISTS shelf          TEXT,
        ADD COLUMN IF NOT EXISTS name_embedding vector(384),
        ADD COLUMN IF NOT EXISTS is_gluten_free BOOLEAN DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS is_vegan       BOOLEAN DEFAULT FALSE;
    """,
    # store_item_id: el itemId de VTEX, que es lo que espera
    # /checkout/cart/add?sku= para armar un carrito por URL. Va aparte de
    # `store_sku` —que en las dos tiendas VTEX guarda el productId— porque son
    # identificadores distintos: en Carrefour el producto 100650 es el item 17305.
    # En Día coinciden por casualidad de su catálogo, y confiar en esa coincidencia
    # es lo que haría que la próxima tienda VTEX arme carritos equivocados sin
    # ningún síntoma. NULL para las tiendas que no son VTEX (Coto).
    #
    # source_category: la clave con la que se scrapeó la fila (el catv… de Coto o
    # el slug de los VTEX). Es lo que le permite al pruning acotarse a las
    # categorías cuyo barrido terminó bien, en vez de apagarse entero ante una sola
    # categoría caída.
    """
    ALTER TABLE store_products
        ADD COLUMN IF NOT EXISTS store_item_id   TEXT,
        ADD COLUMN IF NOT EXISTS source_category TEXT;
    """,
    # categories_empty: categorías que cerraron su barrido sin devolver un solo
    # producto. No es un fallo —hay categorías legítimamente vacías— pero es la
    # firma de una clave que murió: Día renombró `almacen/pastas-y-arroce` y la
    # clave vieja siguió existiendo en el árbol con cero productos, así que dos
    # góndolas quedaron vacías durante semanas reportando 24/24 categorías OK.
    # Sin esta columna el único rastro era un WARNING en el log de esa noche.
    """
    ALTER TABLE scraper_execution_logs
        ADD COLUMN IF NOT EXISTS categories_empty INTEGER NOT NULL DEFAULT 0;
    """,
)

_INDEXES = (
    # HNSW con distancia coseno: es lo que hace barata la búsqueda semántica de
    # GET /search. Ojo con hnsw.ef_search (default 40), que topea cuántas filas
    # devuelve el índice — src/api.py lo sube por conexión.
    """
    CREATE INDEX IF NOT EXISTS idx_unified_products_name_embedding_hnsw
        ON unified_products USING hnsw (name_embedding vector_cosine_ops);
    """,
    # Sostiene GET /category/{slug} y el filtro de misma góndola de las
    # sustituciones. Reemplaza al GIN sobre `tags`, que existía para el operador de
    # solapamiento &&: con una sola góndola por producto la comparación es igualdad
    # y alcanza un btree.
    """
    CREATE INDEX IF NOT EXISTS idx_unified_products_shelf
        ON unified_products (shelf);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_store_products_source_category
        ON store_products (store_id, source_category);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_scraper_exec_logs_run
        ON scraper_execution_logs (run_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_scraper_exec_logs_time
        ON scraper_execution_logs (supermercado, start_time DESC);
    """,
)

STATEMENTS = _EXTENSIONS + _TABLES + _COLUMNS + _INDEXES


# --------------------------------------------------------------------------
# Aplicación
# --------------------------------------------------------------------------

def ensure_schema(conn) -> None:
    """
    Aplica el DDL completo sobre una conexión ya abierta.

    Levanta si algo falla. Quien llama decide: los caminos de escritura dejan
    propagar (sin esquema no hay nada que guardar), y src/api.py lo atrapa y sigue,
    porque un backend con credenciales de sólo lectura tiene que poder servir
    aunque no pueda emitir DDL.
    """
    with conn.cursor() as cur:
        for statement in STATEMENTS:
            cur.execute(statement)


def ensure_schema_at(conn_string: str | None = None, *,
                     connect_timeout: int | None = None) -> None:
    """Igual que `ensure_schema`, abriendo su propia conexión."""
    kwargs = {"connect_timeout": connect_timeout} if connect_timeout else {}
    with psycopg.connect(resolve_conn_string(conn_string), **kwargs) as conn:
        ensure_schema(conn)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    ensure_schema_at()
    logger.info("Esquema aplicado.")
