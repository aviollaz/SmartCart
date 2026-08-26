# tests/test_products_by_ids.py
"""
POST /products/by-ids: el lookup por lista de unified_id que usa el historial de
compras del frontend.

Necesita Postgres arriba y poblado, y paga la carga del modelo por el `lifespan`
del app (igual que tests/test_api.py) aunque este endpoint no lo use: es el
impuesto de levantar el TestClient, no algo a esquivar.

Los helpers puros del final no tocan la base ni el modelo.
"""
import logging

import pytest
from fastapi.testclient import TestClient

from src.api import MAX_PRODUCTS_BY_IDS, _build_product_response, app

logger = logging.getLogger(__name__)

# Un id con forma valida que no puede existir: prod_{ean} con un EAN de ceros.
ID_INEXISTENTE = "prod_0000000000000"


def _sample_ids(client, n=3):
    """Ids reales del catalogo. Se toman de /search en vez de hardcodear EANs,
    igual que hace test_api.py, para que el test no dependa de que este scrapeado
    un producto en particular."""
    response = client.get("/search?q=leche&limit=10")
    assert response.status_code == 200
    ids = [p["unified_id"] for p in response.json()]
    if len(ids) < n:
        pytest.skip("El catalogo no tiene suficientes productos indexados")
    return ids[:n]


def test_devuelve_los_productos_en_el_orden_pedido():
    with TestClient(app) as client:
        ids = _sample_ids(client)
        # Se pide al reves para que el orden pedido no coincida con ningun orden
        # natural de Postgres: si el endpoint ignorara el orden, este assert
        # pasaria por casualidad con la lista sin invertir.
        pedido = list(reversed(ids))

        response = client.post("/products/by-ids", json={"unified_ids": pedido})
        assert response.status_code == 200
        assert [p["unified_id"] for p in response.json()] == pedido


def test_un_id_inexistente_se_omite_y_el_resto_vuelve():
    """El contrato del que depende toda la feature: ausente == lo borro el pruning.

    Es lo que rompe un futuro "filtremos por in_stock para ser consistentes con
    /price-preview": ahi la ausencia volveria a ser ambigua.
    """
    with TestClient(app) as client:
        ids = _sample_ids(client, 2)
        pedido = [ids[0], ID_INEXISTENTE, ids[1]]

        response = client.post("/products/by-ids", json={"unified_ids": pedido})
        assert response.status_code == 200

        devueltos = [p["unified_id"] for p in response.json()]
        assert devueltos == ids, "El inexistente tiene que desaparecer sin arrastrar a los demas"


def test_id_duplicado_devuelve_una_sola_fila():
    """El frontend keyea la grilla por unified_id: dos filas iguales serian dos
    claves de React iguales."""
    with TestClient(app) as client:
        uid = _sample_ids(client, 1)[0]

        response = client.post("/products/by-ids", json={"unified_ids": [uid, uid]})
        assert response.status_code == 200
        assert [p["unified_id"] for p in response.json()] == [uid]


def test_paridad_de_campos_con_category():
    """min_price, image_url, unit_price y store_count tienen que salir identicos
    por los dos endpoints. Es lo que impide que _build_product_response vuelva a
    ser dos implementaciones."""
    with TestClient(app) as client:
        gondola = client.get("/categories").json()[0]["shelves"][0]["slug"]
        desde_categoria = client.get(f"/category/{gondola}?limit=5").json()
        if not desde_categoria:
            pytest.skip(f"La gondola '{gondola}' no tiene productos")

        ids = [p["unified_id"] for p in desde_categoria]
        por_id = {p["unified_id"]: p for p in
                  client.post("/products/by-ids", json={"unified_ids": ids}).json()}

        for esperado in desde_categoria:
            obtenido = por_id[esperado["unified_id"]]
            for campo in ("min_price", "image_url", "unit_price", "store_count",
                          "name", "distance", "shelf", "shelf_label"):
                assert obtenido[campo] == esperado[campo], f"{campo} difiere entre los dos endpoints"


def test_los_limites_de_la_lista_los_rechaza_pydantic():
    with TestClient(app) as client:
        assert client.post("/products/by-ids", json={"unified_ids": []}).status_code == 422

        demasiados = [f"prod_{i:013d}" for i in range(MAX_PRODUCTS_BY_IDS + 1)]
        assert client.post("/products/by-ids", json={"unified_ids": demasiados}).status_code == 422


# --------------------------------------------------------------------------
# _build_product_response: puro, sin base ni modelo.
# --------------------------------------------------------------------------

def _row(**overrides):
    fila = {
        "id": "prod_1", "ean": "1", "name": "Producto", "brand": "Marca",
        "shelf": "alfajores", "unit_type": "g",
        "total_volume_weight": 500.0, "is_gluten_free": False, "is_vegan": False,
        "store_count": 0,
    }
    fila.update(overrides)
    return fila


def _oferta(store_id, base_price=100.0, image_url=None, promo_unit_price=None):
    return {"store_id": store_id, "base_price": base_price, "image_url": image_url,
            "promo_unit_price": promo_unit_price}


def test_sin_ofertas_el_precio_es_cero_y_no_hay_imagen():
    resultado = _build_product_response(_row(), [])
    assert resultado["min_price"] == 0.0
    assert resultado["image_url"] is None
    assert resultado["available_at_stores"] == []


def test_una_oferta_en_cero_no_entra_en_el_minimo():
    """base_price 0 es "no se sabe el precio", no "es gratis"."""
    ofertas = [_oferta("coto_online", 0.0), _oferta("dia_online", 250.0)]
    assert _build_product_response(_row(), ofertas)["min_price"] == 250.0


def test_la_imagen_respeta_la_prioridad_de_tiendas():
    ofertas = [_oferta("dia_online", image_url="dia.jpg"), _oferta("coto_online", image_url="coto.jpg")]
    assert _build_product_response(_row(), ofertas)["image_url"] == "coto.jpg"


def test_una_tienda_prioritaria_sin_imagen_cede_el_turno():
    ofertas = [_oferta("coto_online", image_url=None), _oferta("dia_online", image_url="dia.jpg")]
    assert _build_product_response(_row(), ofertas)["image_url"] == "dia.jpg"
