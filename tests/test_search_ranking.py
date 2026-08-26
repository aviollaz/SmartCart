"""
Ranking de /search y /category: el desempate por disponibilidad entre tiendas.

Necesita Postgres arriba y poblado, y carga el modelo de sentence-transformers
(igual que tests/test_api.py). No son tests aislados.

Lo que se protege acá es un feature que, mal implementado, no se nota: si el
bonus no se aplica los resultados igual salen, solo que sin el reordenamiento.
Por eso las aserciones son sobre el invariante del score y no sobre productos
concretos, que cambian con cada scrapeo.
"""
import logging

import psycopg
import pytest
from fastapi.testclient import TestClient

from src.api import (
    SEARCH_EF_SEARCH,
    SEARCH_POOL_SIZE,
    STORE_BONUS,
    STORE_BONUS_CAP,
    app,
)
from src.database import SmartCartDB

logger = logging.getLogger(__name__)

# Una góndola real de src/shelves.py: la tabla es cerrada, así que hardcodear el
# slug no puede quedar desactualizado sin que tests/test_shelves.py lo note.
GONDOLA = "leches"

QUERIES = ["yogur bebible", "galletitas", "leche descremada", "aceite", "gaseosa"]


@pytest.fixture(scope="module")
def client():
    # El `with` corre el lifespan, que es lo que carga el modelo.
    with TestClient(app) as c:
        yield c


def _score(producto):
    """El score que ordena, replicado desde el ORDER BY del endpoint."""
    extra = min(max(producto["store_count"] - 1, 0), STORE_BONUS_CAP)
    return producto["distance"] - STORE_BONUS * extra


@pytest.mark.parametrize("q", QUERIES)
def test_los_resultados_vienen_ordenados_por_el_score_combinado(client, q):
    """
    Si el bonus no se aplicara, los resultados vendrían ordenados por distancia
    pura y esta secuencia no sería monótona en cuanto dos productos con distinta
    cantidad de tiendas quedaran a distancia parecida.
    """
    resultados = client.get("/search", params={"q": q, "limit": 20}).json()
    assert resultados, f"'{q}' no devolvió resultados"

    scores = [_score(p) for p in resultados]
    assert scores == sorted(scores), f"'{q}' no está ordenado por el score combinado"


@pytest.mark.parametrize("q", QUERIES)
def test_el_bonus_esta_topeado(client, q):
    """
    La cota dura del feature: por muchas tiendas que tenga, un producto no puede
    superar a otro que esté más de `STORE_BONUS * STORE_BONUS_CAP` más cerca.
    Sin el LEAST(), sumar tiendas en el futuro aflojaría el ranking solo.
    """
    resultados = client.get("/search", params={"q": q, "limit": 20}).json()
    tope = STORE_BONUS * STORE_BONUS_CAP

    for anterior, siguiente in zip(resultados, resultados[1:]):
        adelantamiento = anterior["distance"] - siguiente["distance"]
        assert adelantamiento <= tope + 1e-9, (
            f"'{q}': {anterior['name']!r} (d={anterior['distance']:.3f}) superó a "
            f"{siguiente['name']!r} (d={siguiente['distance']:.3f}) por {adelantamiento:.3f}, "
            f"más que el tope {tope}"
        )


def test_store_count_viene_poblado(client):
    resultados = client.get("/search", params={"q": "leche", "limit": 20}).json()
    assert resultados

    for p in resultados:
        assert p["store_count"] is not None
        assert p["store_count"] >= 0
        # Solo hay tres tiendas; un número mayor significa que el COUNT no es
        # DISTINCT y está contando ofertas en vez de tiendas.
        assert p["store_count"] <= 3


def test_el_bonus_efectivamente_sube_productos_multitienda(client):
    """
    El feature tiene que producir un efecto medible, no solo no romper.

    Se compara contra el orden por distancia pura del mismo conjunto: el top-10
    del ranking real no puede tener MENOS tiendas promedio que el top-10
    ordenado por distancia sola.
    """
    resultados = client.get("/search", params={"q": "yogur", "limit": 20}).json()
    assert len(resultados) >= 10

    por_distancia = sorted(resultados, key=lambda p: p["distance"])
    tiendas_real = sum(p["store_count"] for p in resultados[:10]) / 10
    tiendas_distancia = sum(p["store_count"] for p in por_distancia[:10]) / 10

    assert tiendas_real >= tiendas_distancia


def test_el_pool_no_queda_topeado_por_ef_search():
    """
    El modo de falla silencioso que motivó `SEARCH_EF_SEARCH`.

    `hnsw.ef_search` vale 40 por defecto en pgvector y es un techo sobre las
    filas que devuelve el índice: sin subirlo, un `LIMIT 100` devuelve 40 y el
    rerank reordena siempre los mismos 40 candidatos. Nada falla a la vista —
    el feature simplemente no puede cambiar la composición del top-N.
    """
    db = SmartCartDB()
    vector = "[" + ",".join(["0.01"] * 384) + "]"

    with psycopg.connect(db.conn_string) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM unified_products WHERE name_embedding IS NOT NULL")
            disponibles = cur.fetchone()[0]
            if disponibles < SEARCH_POOL_SIZE:
                pytest.skip(f"hacen falta {SEARCH_POOL_SIZE} productos con embedding, hay {disponibles}")

            cur.execute(
                "SELECT set_config('hnsw.ef_search', %s, false)", (str(SEARCH_EF_SEARCH),)
            )
            cur.execute(
                """
                SELECT count(*) FROM (
                    SELECT 1 FROM unified_products
                    WHERE name_embedding IS NOT NULL
                    ORDER BY name_embedding <=> %s
                    LIMIT %s
                ) t
                """,
                (vector, SEARCH_POOL_SIZE),
            )
            assert cur.fetchone()[0] == SEARCH_POOL_SIZE

    assert SEARCH_EF_SEARCH >= SEARCH_POOL_SIZE, (
        "ef_search por debajo del pool lo recorta en silencio"
    )


def test_category_es_determinista(client):
    """
    Antes la query no tenía ORDER BY: con LIMIT 50 sobre una categoría más
    grande, Postgres devolvía 50 filas en el orden que tuviera a mano y dos
    llamadas iguales podían traer productos distintos.
    """
    primera = client.get(f"/category/{GONDOLA}", params={"limit": 20}).json()
    segunda = client.get(f"/category/{GONDOLA}", params={"limit": 20}).json()

    if not primera:
        pytest.skip(f"no hay productos en la góndola {GONDOLA}")

    assert [p["unified_id"] for p in primera] == [p["unified_id"] for p in segunda]


def test_category_ordena_por_disponibilidad(client):
    """
    En /category no hay relevancia que resignar (su `distance` es 0.0 fija), así
    que el orden por cantidad de tiendas es estricto, sin bonus ni tope.
    """
    resultados = client.get(f"/category/{GONDOLA}", params={"limit": 20}).json()
    if not resultados:
        pytest.skip(f"no hay productos en la góndola {GONDOLA}")

    counts = [p["store_count"] for p in resultados]
    assert counts == sorted(counts, reverse=True)
