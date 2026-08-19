"""
Tests de las etapas de POST /optimize (src/api.py).

Existen porque la descomposición del endpoint las volvió testeables: mientras
eran bloques dentro de una función de 235 líneas, la única forma de ejercitarlas
era levantar la app entera contra Postgres, y de hecho no las cubría nadie
(`test_api.py` prueba `/` y `/search`, no `/optimize`).

No tocan la base ni el modelo: el cursor es un doble y la logística de Coto se
monkeypatchea.
"""
import pytest

from src import api

COTO = "coto_online"
DIA = "dia_online"
CARREFOUR = "carrefour_online"


class FakeCursor:
    """Cursor que devuelve filas fijas según la columna que le pidan."""

    def __init__(self, url_rows=None, item_rows=None):
        self.url_rows = url_rows or {}
        self.item_rows = item_rows or {}
        self._result = []
        self.queries = []

    def execute(self, sql, params):
        self.queries.append((sql, params))
        store_id, uids = params
        if "store_item_id" in sql:
            self._result = [
                {"unified_product_id": uid, "store_item_id": self.item_rows[(store_id, uid)]}
                for uid in uids if (store_id, uid) in self.item_rows
            ]
        else:
            self._result = [
                {"unified_product_id": uid, "product_url": self.url_rows[(store_id, uid)]}
                for uid in uids if (store_id, uid) in self.url_rows
            ]

    def fetchall(self):
        return self._result


def _split(store, *uids, quantity=1):
    return {store: {"products": [{"unified_id": u, "quantity": quantity} for u in uids]}}


# --------------------------------------------------------------------------
# _optional_feature
# --------------------------------------------------------------------------

def test_optional_feature_devuelve_el_resultado():
    assert api._optional_feature("x", "default", lambda a, b: a + b, 1, 2) == 3


def test_optional_feature_devuelve_el_default_si_explota(caplog):
    def _explota():
        raise RuntimeError("la base se cayó")

    assert api._optional_feature("la feature X", [], _explota) == []
    assert "la feature X" in caplog.text


def test_optional_feature_pasa_kwargs():
    assert api._optional_feature("x", None, lambda *, a, b: a * b, a=3, b=4) == 12


# --------------------------------------------------------------------------
# _ensure_optional_keys
# --------------------------------------------------------------------------

def test_ensure_optional_keys_completa_lo_que_falta():
    result = {"status": "success"}
    api._ensure_optional_keys(result)
    assert result["suggestions"] == []
    assert result["strategic_swaps"] == []
    assert result["price_savings"] is None


def test_ensure_optional_keys_no_pisa_lo_que_ya_esta():
    result = {"suggestions": [{"a": 1}], "strategic_swaps": [{"b": 2}], "price_savings": {"total": 5}}
    api._ensure_optional_keys(result)
    assert result["suggestions"] == [{"a": 1}]
    assert result["strategic_swaps"] == [{"b": 2}]
    assert result["price_savings"] == {"total": 5}


# --------------------------------------------------------------------------
# _resolve_coto_stage
# --------------------------------------------------------------------------

class _Req:
    def __init__(self, delivery_costs=None, lat=None, lng=None):
        self.delivery_costs = delivery_costs
        self.lat = lat
        self.lng = lng


def test_coto_cubierto_pisa_el_costo_de_envio(monkeypatch):
    monkeypatch.setattr(api, "resolve_coto_logistics",
                        lambda lat, lng, fallback_delivery_cost: {
                            "covered": True, "delivery_cost": 3399, "source": "live"})

    costs, excluded, logistics = _resolve(_Req({COTO: 3000, DIA: 3000, CARREFOUR: 3500}, -34.6, -58.4))

    assert costs[COTO] == 3399.0
    assert excluded == []
    assert logistics["source"] == "live"


def test_coto_sin_cobertura_se_excluye(monkeypatch):
    monkeypatch.setattr(api, "resolve_coto_logistics",
                        lambda lat, lng, fallback_delivery_cost: {
                            "covered": False, "delivery_cost": None, "message": "no llega"})

    costs, excluded, _ = _resolve(_Req({COTO: 3000, DIA: 3000, CARREFOUR: 3500}, -31.4, -64.2))

    assert excluded == [COTO]
    # No se encarece: se saca del modelo. El costo queda como vino.
    assert costs[COTO] == 3000


def test_sin_delivery_costs_usa_los_defaults(monkeypatch):
    monkeypatch.setattr(api, "resolve_coto_logistics",
                        lambda lat, lng, fallback_delivery_cost: {
                            "covered": True, "delivery_cost": None})

    costs, _, _ = _resolve(_Req(None))

    assert costs == dict(api.DEFAULT_DELIVERY_COSTS)


def test_no_muta_el_dict_del_request(monkeypatch):
    """El request de Pydantic no puede quedar alterado por la etapa de logística."""
    monkeypatch.setattr(api, "resolve_coto_logistics",
                        lambda lat, lng, fallback_delivery_cost: {
                            "covered": True, "delivery_cost": 9999})

    original = {COTO: 3000, DIA: 3000, CARREFOUR: 3500}
    req = _Req(dict(original), -34.6, -58.4)
    _resolve(req)

    assert req.delivery_costs == original


def _resolve(req):
    return api._resolve_coto_stage(req)


# --------------------------------------------------------------------------
# _attach_product_urls
# --------------------------------------------------------------------------

def test_attach_product_urls_pega_link_y_promo():
    split = _split(COTO, "prod_a", "prod_b")
    cur = FakeCursor(url_rows={(COTO, "prod_a"): "https://coto/a"})
    flat = {"prod_a": {COTO: {"applied_promo_id": "p1", "promo_description": "3x2",
                              "effective_unit_price": 100.0}}}

    api._attach_product_urls(cur, split, flat)

    a, b = split[COTO]["products"]
    assert a["product_url"] == "https://coto/a"
    assert a["applied_promo_id"] == "p1"
    assert a["effective_unit_price"] == 100.0
    # Sin fila en la base ni en el flatten: link None y sin claves de promo.
    assert b["product_url"] is None
    assert "applied_promo_id" not in b


def test_attach_product_urls_ignora_tiendas_sin_productos():
    split = {COTO: {"products": []}}
    cur = FakeCursor()
    api._attach_product_urls(cur, split, {})
    assert cur.queries == []


# --------------------------------------------------------------------------
# _attach_vtex_checkout_links
# --------------------------------------------------------------------------

def test_magic_link_con_todos_los_item_id():
    split = _split(DIA, "prod_a", "prod_b", quantity=2)
    cur = FakeCursor(item_rows={(DIA, "prod_a"): "111", (DIA, "prod_b"): "222"})

    api._attach_vtex_checkout_links(cur, split)

    url = split[DIA]["checkout_url"]
    assert url.startswith("https://diaonline.supermercadosdia.com.ar/checkout/cart/add?sc=1")
    assert "sku=111&qty=2&seller=1" in url
    assert "sku=222&qty=2&seller=1" in url


def test_sin_link_si_falta_un_item_id(caplog):
    """
    Un carrito a medias es peor que ninguno: el usuario cree que ya tiene todo
    cargado y paga menos productos de los que eligió.
    """
    split = _split(DIA, "prod_a", "prod_b")
    cur = FakeCursor(item_rows={(DIA, "prod_a"): "111"})   # falta prod_b

    api._attach_vtex_checkout_links(cur, split)

    assert "checkout_url" not in split[DIA]
    assert "sin store_item_id" in caplog.text


def test_coto_no_arma_magic_link():
    """Coto no es VTEX: no tiene endpoint de carrito por URL."""
    split = _split(COTO, "prod_a")
    cur = FakeCursor(item_rows={(COTO, "prod_a"): "111"})

    api._attach_vtex_checkout_links(cur, split)

    assert "checkout_url" not in split[COTO]
    assert cur.queries == []


def test_carrefour_tambien_arma_link():
    split = _split(CARREFOUR, "prod_a")
    cur = FakeCursor(item_rows={(CARREFOUR, "prod_a"): "17305"})

    api._attach_vtex_checkout_links(cur, split)

    assert "www.carrefour.com.ar/checkout/cart/add" in split[CARREFOUR]["checkout_url"]
    assert "sku=17305" in split[CARREFOUR]["checkout_url"]


@pytest.mark.parametrize("store", [DIA, CARREFOUR])
def test_ninguna_tienda_vtex_sin_item_id_rompe(store):
    split = _split(store, "prod_a")
    cur = FakeCursor(item_rows={})

    api._attach_vtex_checkout_links(cur, split)

    assert "checkout_url" not in split[store]
