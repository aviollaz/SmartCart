"""
Tests del borrado de filas obsoletas (SmartCartDB.prune_missing_store_products).

Corren contra Postgres, sobre un `store_id` sintético que no colisiona con las
tiendas reales, así que se pueden correr con la base poblada sin tocar datos de
verdad. Cada test crea sus filas y las limpia al terminar.
"""
import psycopg
import pytest

from src.database import SmartCartDB

STORE = "tienda_de_prueba_pruning"


@pytest.fixture
def db():
    instancia = SmartCartDB()
    try:
        with psycopg.connect(instancia.conn_string):
            pass
    except Exception as e:
        pytest.skip(f"Postgres no disponible: {e}")
    yield instancia
    _limpiar(instancia)


def _limpiar(db):
    with psycopg.connect(db.conn_string) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM store_products WHERE store_id = %s", (STORE,))
            cur.execute(
                """DELETE FROM unified_products
                   WHERE id LIKE 'prod_test_pruning_%%'
                     AND NOT EXISTS (SELECT 1 FROM store_products sp
                                     WHERE sp.unified_product_id = unified_products.id)"""
            )


def _sembrar(db, skus):
    """Crea un unified_product y su oferta por cada SKU."""
    _limpiar(db)
    with psycopg.connect(db.conn_string) as conn:
        with conn.cursor() as cur:
            for sku in skus:
                uid = f"prod_test_pruning_{sku}"
                cur.execute(
                    """INSERT INTO unified_products (id, ean, name, brand, unit_type, category)
                       VALUES (%s, %s, %s, 'MarcaTest', 'un', 'Otros')
                       ON CONFLICT (id) DO NOTHING""",
                    (uid, sku, f"Producto de prueba {sku}"),
                )
                cur.execute(
                    """INSERT INTO store_products
                       (unified_product_id, store_id, store_sku, product_url, base_price,
                        in_stock, promotions_json)
                       VALUES (%s, %s, %s, 'http://x', 1000, TRUE, '[]')
                       ON CONFLICT (store_id, store_sku) DO NOTHING""",
                    (uid, STORE, sku),
                )


def _skus_en_base(db):
    with psycopg.connect(db.conn_string) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT store_sku FROM store_products WHERE store_id = %s ORDER BY store_sku",
                (STORE,),
            )
            return [r[0] for r in cur.fetchall()]


def _existe_unified(db, sku):
    with psycopg.connect(db.conn_string) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM unified_products WHERE id = %s",
                (f"prod_test_pruning_{sku}",),
            )
            return cur.fetchone() is not None


def test_borra_solo_las_filas_que_no_se_vieron(db):
    _sembrar(db, [f"s{n}" for n in range(10)])

    # Se vieron 8 de 10: las dos que faltan se discontinuaron.
    vistos = {f"s{n}" for n in range(8)}
    resultado = db.prune_missing_store_products(STORE, vistos)

    assert resultado["deleted"] == 2
    assert resultado["skipped"] is False
    assert _skus_en_base(db) == sorted(vistos)


def test_borra_el_unified_product_que_se_queda_sin_ofertas(db):
    _sembrar(db, [f"s{n}" for n in range(10)])
    resultado = db.prune_missing_store_products(STORE, {f"s{n}" for n in range(8)})

    assert resultado["orphans"] >= 2
    assert not _existe_unified(db, "s8"), "sin ninguna oferta ya no lo vende nadie"
    assert _existe_unified(db, "s0")


def test_un_scrapeo_sin_skus_no_borra_nada(db):
    """
    El modo de falla que documenta CLAUDE.md: el hash de la persisted query de
    VTEX rota, la tienda responde 200 con `errors` y cero productos, y la regla
    de "página vacía = fin de categoría" lo lee como éxito. Si eso podara,
    borraría el catálogo entero de la tienda.
    """
    _sembrar(db, [f"s{n}" for n in range(10)])
    resultado = db.prune_missing_store_products(STORE, set())

    assert resultado["skipped"] is True
    assert resultado["deleted"] == 0
    assert len(_skus_en_base(db)) == 10


def test_aborta_si_borraria_una_fraccion_sospechosa(db):
    """Perder un tercio del catálogo de golpe es un scraper roto, no la góndola."""
    _sembrar(db, [f"s{n}" for n in range(10)])

    # Se vieron sólo 2 de 10: borraría el 80%.
    resultado = db.prune_missing_store_products(STORE, {"s0", "s1"})

    assert resultado["skipped"] is True
    assert resultado["deleted"] == 0
    assert "80%" in resultado["reason"]
    assert len(_skus_en_base(db)) == 10


def test_el_umbral_deja_pasar_una_baja_normal(db):
    _sembrar(db, [f"s{n}" for n in range(10)])

    # 20% < 30%: una baja plausible del catálogo.
    resultado = db.prune_missing_store_products(STORE, {f"s{n}" for n in range(8)})

    assert resultado["skipped"] is False
    assert resultado["deleted"] == 2


def test_dry_run_informa_pero_no_borra(db):
    _sembrar(db, [f"s{n}" for n in range(10)])
    vistos = {f"s{n}" for n in range(8)}

    seco = db.prune_missing_store_products(STORE, vistos, dry_run=True)

    assert len(_skus_en_base(db)) == 10, "el dry-run no debe tocar la base"
    assert _existe_unified(db, "s8")

    # Y lo que informó tiene que ser exactamente lo que hace el run real, huérfanos
    # incluidos: el dry-run corre el DELETE y lo deshace, no lo estima aparte.
    real = db.prune_missing_store_products(STORE, vistos)
    assert (seco["deleted"], seco["orphans"]) == (real["deleted"], real["orphans"])


def test_sin_filas_obsoletas_no_hace_nada(db):
    _sembrar(db, [f"s{n}" for n in range(5)])
    resultado = db.prune_missing_store_products(STORE, {f"s{n}" for n in range(5)})

    assert resultado == {"deleted": 0, "orphans": 0, "skipped": False, "reason": None}
    assert len(_skus_en_base(db)) == 5


def test_no_toca_otras_tiendas(db):
    """El pruning de una tienda no puede llevarse las filas de las demás."""
    _sembrar(db, [f"s{n}" for n in range(10)])

    with psycopg.connect(db.conn_string) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT store_id, count(*) FROM store_products GROUP BY store_id")
            antes = dict(cur.fetchall())

    db.prune_missing_store_products(STORE, {f"s{n}" for n in range(8)})

    with psycopg.connect(db.conn_string) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT store_id, count(*) FROM store_products GROUP BY store_id")
            despues = dict(cur.fetchall())

    for store, n in antes.items():
        if store != STORE:
            assert despues.get(store) == n, f"el pruning tocó {store}"
