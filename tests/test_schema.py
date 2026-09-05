"""
Tests de src/schema.py contra Postgres (no necesita el modelo de embeddings).

Lo que se protege es la propiedad que hace posible que no haya migraciones
versionadas: el DDL entero es **idempotente**. Si deja de serlo, el síntoma no es
un test rojo en CI sino un `save_store_products` que explota en medio de un
barrido a las 3 de la mañana, porque `_ensure_schema` corre en cada instancia de
SmartCartDB.

Corre contra la base poblada sin tocar datos: sólo emite DDL que ya está
aplicado, y consulta el catálogo de Postgres.
"""
import psycopg
import pytest

from src.schema import STATEMENTS, ensure_schema, resolve_conn_string

TABLAS = ("unified_products", "store_products", "scraper_execution_logs")

# Las columnas que el proyecto dejó de usar. Que sigan sin existir es la mitad
# del punto: si alguien las reintroduce en el DDL, vuelven los NULL con cara de
# dato bueno (`units_per_pack DEFAULT 1` afirmando "no es un pack" sobre 287
# productos que sí lo eran).
COLUMNAS_MUERTAS = (
    ("unified_products", "units_per_pack"),
    ("unified_products", "category"),
    ("unified_products", "tags"),
)


@pytest.fixture(scope="module")
def conn():
    try:
        # 30s y no 5: contra el docker-compose local sobraban, pero la base vive
        # en Neon, que se suspende sola tras 5 minutos sin actividad y tarda
        # varios segundos en despertar. Con 5s el fixture salteaba las NUEVE
        # aserciones de esquema y pytest reportaba verde — el mismo modo de falla
        # que estos tests existen para detectar, esta vez en los tests mismos.
        with psycopg.connect(resolve_conn_string(), connect_timeout=30) as c:
            yield c
    except psycopg.OperationalError as exc:
        pytest.skip(f"Postgres no disponible: {exc}")


def _columnas(conn, tabla) -> set:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
            (tabla,),
        )
        return {row[0] for row in cur.fetchall()}


def test_ensure_schema_es_idempotente(conn):
    """Dos corridas seguidas, que es literalmente lo que pasa en producción."""
    ensure_schema(conn)
    ensure_schema(conn)


@pytest.mark.parametrize("tabla", TABLAS)
def test_las_tres_tablas_existen(conn, tabla):
    ensure_schema(conn)

    assert _columnas(conn, tabla), f"falta la tabla {tabla}"


def test_unified_products_tiene_la_gondola(conn):
    ensure_schema(conn)

    assert "shelf" in _columnas(conn, "unified_products")


@pytest.mark.parametrize("tabla,columna", COLUMNAS_MUERTAS)
def test_las_columnas_muertas_no_vuelven(conn, tabla, columna):
    ensure_schema(conn)

    assert columna not in _columnas(conn, tabla)


def test_store_products_guarda_el_nombre_de_la_tienda(conn):
    """
    El nombre propio de cada oferta. Sin esta columna el único nombre de la base
    es `unified_products.name`, que es por EAN y lo pisa la última cadena que
    escribió: de los tres nombres de un producto sobrevive uno y no queda registro
    de cuál, así que verificar a mano qué levantó cada tienda es imposible.
    """
    ensure_schema(conn)

    assert "name" in _columnas(conn, "store_products")


def test_los_indices_estan(conn):
    ensure_schema(conn)

    with conn.cursor() as cur:
        cur.execute("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
        indices = {row[0] for row in cur.fetchall()}

    esperados = {
        "idx_unified_products_name_embedding_hnsw",
        "idx_unified_products_shelf",
        "idx_store_products_source_category",
        "idx_scraper_exec_logs_run",
        "idx_scraper_exec_logs_time",
    }
    assert esperados <= indices, f"faltan: {esperados - indices}"


def test_el_ddl_no_borra_nada():
    """
    Ninguna sentencia del módulo puede ser destructiva. El DDL corre solo, en
    cada arranque de la API y en cada barrido; los DROP viven en
    src/scripts/migrate_shelves.py, que se corre a mano y una sola vez.
    """
    prohibidas = ("DROP ", "TRUNCATE", "DELETE ")
    for statement in STATEMENTS:
        upper = statement.upper()
        assert not any(p in upper for p in prohibidas), statement
