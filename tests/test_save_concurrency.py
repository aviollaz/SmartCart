"""
Escrituras concurrentes de SmartCartDB.save_store_products.

Las tres tiendas corren en paralelo (la matriz de scrape.yml) y comparten EANs,
así que sus transacciones compiten por las mismas filas de `unified_products`.
Recorriéndolas en órdenes distintos se deadlockeaban: 9 categorías perdidas
entre el 20 y el 25-sep-2026. `save_store_products` ordena el lote por
`unified_id` antes de escribir para que eso no pueda pasar, y reintenta el lote
si igual aparece un `DeadlockDetected`.

Corren contra Postgres, sobre `store_id` y EANs sintéticos que no colisionan con
datos reales, y limpian lo que crean.
"""
import threading

import psycopg
import pytest

from src.database import SmartCartDB

STORES = ("tienda_de_prueba_lock_a", "tienda_de_prueba_lock_b")
# 13 caracteres como máximo (`unified_products.ean` es VARCHAR(13)).
EAN_PREFIX = "9990000"
N_PRODUCTOS = 300


@pytest.fixture
def db():
    instancia = SmartCartDB()
    try:
        with psycopg.connect(instancia.conn_string):
            pass
    except Exception as e:
        pytest.skip(f"Postgres no disponible: {e}")
    _limpiar(instancia)
    yield instancia
    _limpiar(instancia)


def _limpiar(db):
    with psycopg.connect(db.conn_string) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM store_products WHERE store_id = ANY(%s)", (list(STORES),))
            cur.execute("DELETE FROM unified_products WHERE id LIKE %s", (f"prod_{EAN_PREFIX}%",))


def _producto(i: int) -> dict:
    return {
        "ean": f"{EAN_PREFIX}{i:04d}",
        "store_sku": f"sku_{i:04d}",
        "name": f"Producto de prueba {i}",
        "brand": "MarcaTest",
        "unit_type": "un",
        "total_volume_weight": 1.0,
        "base_price": 100.0,
        "raw_promos": [],
        "shelf": "alfajores",
        "source_category": "categoria_de_prueba",
        "url": "https://example.com",
        "in_stock": True,
    }


def test_dos_tiendas_en_ordenes_inversos_no_se_deadlockean(db, monkeypatch):
    # Sin reintentos: si el orden de locks no evitara el ciclo, el deadlock
    # tiene que llegar hasta acá en vez de quedar tapado por la red de abajo.
    monkeypatch.setattr(SmartCartDB, "MAX_SAVE_ATTEMPTS", 1)
    productos = [_producto(i) for i in range(N_PRODUCTOS)]
    lotes = {STORES[0]: productos, STORES[1]: list(reversed(productos))}
    # Crear el esquema antes, para que el DDL no participe de la carrera.
    with psycopg.connect(db.conn_string) as conn:
        db._ensure_schema(conn)

    errores = []
    arranque = threading.Barrier(len(STORES))

    def guardar(store_id):
        instancia = SmartCartDB(db.conn_string)
        instancia._schema_ready = True
        arranque.wait()
        try:
            instancia.save_store_products(lotes[store_id], store_id)
        except Exception as exc:  # noqa: BLE001 — se reporta abajo
            errores.append(exc)

    hilos = [threading.Thread(target=guardar, args=(s,)) for s in STORES]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=300)

    assert not errores, errores
    with psycopg.connect(db.conn_string) as conn:
        filas = conn.execute(
            "SELECT count(*) FROM store_products WHERE store_id = ANY(%s)", (list(STORES),)
        ).fetchone()[0]
    assert filas == 2 * N_PRODUCTOS


def test_un_deadlock_reintenta_el_lote(db, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_: None)
    escribir_de_verdad = SmartCartDB._write_rows
    llamadas = []

    def falla_una_vez(self, filas):
        llamadas.append(len(filas))
        if len(llamadas) == 1:
            raise psycopg.errors.DeadlockDetected("deadlock detected")
        return escribir_de_verdad(self, filas)

    monkeypatch.setattr(SmartCartDB, "_write_rows", falla_una_vez)

    guardadas = db.save_store_products([_producto(i) for i in range(3)], STORES[0])

    assert guardadas == 3
    assert llamadas == [3, 3]


def test_deadlock_persistente_levanta(db, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_: None)

    def siempre_falla(self, filas):
        raise psycopg.errors.DeadlockDetected("deadlock detected")

    monkeypatch.setattr(SmartCartDB, "_write_rows", siempre_falla)

    with pytest.raises(psycopg.errors.DeadlockDetected):
        db.save_store_products([_producto(0)], STORES[0])
