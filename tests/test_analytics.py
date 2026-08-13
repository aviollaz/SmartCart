"""
Tests de src/analytics.py. Suite pura: sin red, sin base de datos y sin modelo.

No se importa `src.api` a propósito, aunque de ahí venga el `OptimizationRequest`
real: ese import arrastra sentence-transformers y convertiría un suite de
milisegundos en uno de segundos. `build_cart_optimized_event` recibe el request
por duck typing, así que alcanza con el stand-in de abajo, que replica los
campos que el adapter lee.

Lo que se protege acá son las reglas del contrato del analyzer
(../SmartCart Performance Analyzer/src/models.py) que fallan en silencio:

  - un `occurred_at` sin zona horaria se rechaza con 422, y el evento se pierde;
  - un carrito `infeasible` tiene que emitirse igual (es el KPI de fricción), con
    montos en None y no en 0;
  - el envío no puede lanzar nunca, pase lo que pase con el servicio de destino.

Los tres son invisibles desde el lado de SmartCart: la optimización sale bien y
el tablero queda vacío o torcido sin que nadie se entere.
"""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

import httpx
import pytest
from pydantic import BaseModel

from src import analytics
from src.analytics import build_cart_optimized_event, send_cart_optimized_event


# --- Stand-in del request -----------------------------------------------------
# Espeja los campos de OptimizationRequest (src/api.py) que lee el adapter. Se
# usa un BaseModel de verdad y no un SimpleNamespace para que `model_dump()` de
# los ítems del carrito se comporte igual que en producción.

class _CartItem(BaseModel):
    unified_id: str
    quantity: int


class _Request(BaseModel):
    cart: List[_CartItem]
    user_memberships: Optional[List[str]] = []
    user_cards: Optional[List[str]] = []
    anon_user_id: Optional[str] = None
    zone: Optional[str] = None


def _request(**overrides) -> _Request:
    defaults = {
        "cart": [
            _CartItem(unified_id="prod_7790000000123", quantity=2),
            _CartItem(unified_id="prod_7790000000456", quantity=1),
        ],
        "user_memberships": ["Comunidad Coto"],
        "user_cards": ["Visa Galicia"],
        "anon_user_id": "9f2b77c4-51d0-4a3e-b8aa-0f6d21e4c9b7",
        "zone": "CABA",
    }
    defaults.update(overrides)
    return _Request(**defaults)


# --- Respuestas de /optimize --------------------------------------------------
# Forma real de lo que devuelve optimize_cart() + lo que le agrega api.py.

SUCCESS_RESULT = {
    "status": "success",
    "total_spent_net": 84210.55,
    "excluded_stores": [],
    "split": {
        "dia_online": {
            "products": [
                {"unified_id": "prod_7790000000123", "quantity": 2, "total_cost": 5400.0},
            ],
            "subtotal_products": 41000.0,
            "delivery_cost": 2000.0,
            "bank_discount": {"card": "Visa Galicia", "amount": 4100.0, "description": "20% tope $8000"},
            "store_total": 38900.0,
        },
        "carrefour_online": {
            "products": [
                {"unified_id": "prod_7790000000456", "quantity": 1, "total_cost": 41810.55},
            ],
            "subtotal_products": 41810.55,
            "delivery_cost": 3500.0,
            "bank_discount": None,
            "store_total": 45310.55,
        },
    },
    "logistics": {"coto": {"covered": True, "sucursal": "220", "delivery_cost": 3399.0, "source": "live", "message": None}},
    "price_savings": {"total": 6120.30, "items": [{"unified_id": "prod_7790000000123", "savings": 6120.30}]},
    "suggestions": [{"original_uid": "prod_7790000000123", "alternatives": [{}, {}]}],
    "strategic_swaps": [{"store": "carrefour_online"}],
}

# Un carrito que no llega a ningún mínimo. Ojo con lo que NO trae: ni `split`, ni
# `total_spent_net`, ni `price_savings`, ni `suggestions`, ni `strategic_swaps`.
INFEASIBLE_RESULT = {
    "status": "infeasible",
    "message": "No se encontró una asignación que cumpla los mínimos requeridos.",
    "excluded_stores": ["coto_online"],
    "logistics": {"coto": {"covered": False, "sucursal": "0", "delivery_cost": None, "source": "live", "message": "Coto no entrega acá."}},
}


# --- build_cart_optimized_event ----------------------------------------------

def test_occurred_at_lleva_zona_horaria():
    """
    El contrato rechaza un timestamp naive a propósito: el emisor corre en UTC-3
    y sin zona cada evento se correría tres horas, desalineando los cortes
    diarios del tablero.
    """
    event = build_cart_optimized_event(_request(), SUCCESS_RESULT, duration_ms=812)

    parsed = datetime.fromisoformat(event["occurred_at"])
    assert parsed.tzinfo is not None
    assert parsed.utcoffset().total_seconds() == 0


def test_event_id_es_un_uuid_nuevo_por_optimizacion():
    """Es la clave de idempotencia y es UNIQUE en el warehouse: repetirlo entre
    dos optimizaciones distintas haría que la segunda se descarte en silencio."""
    first = build_cart_optimized_event(_request(), SUCCESS_RESULT)
    second = build_cart_optimized_event(_request(), SUCCESS_RESULT)

    UUID(first["event_id"])  # lanza si no es un UUID válido
    assert first["event_id"] != second["event_id"]


def test_success_reenvia_montos_y_split_sin_recalcular():
    request = _request()
    event = build_cart_optimized_event(request, SUCCESS_RESULT, duration_ms=812)

    assert event["event_type"] == "cart_optimized"
    assert event["schema_version"] == 1
    assert event["source"]["app"] == "smartcart"
    assert event["source"]["env"] == "dev"

    assert event["user"] == {
        "anon_user_id": "9f2b77c4-51d0-4a3e-b8aa-0f6d21e4c9b7",
        "zone": "CABA",
        "memberships": ["Comunidad Coto"],
        "cards": ["Visa Galicia"],
    }

    assert event["cart"]["items"] == [
        {"unified_id": "prod_7790000000123", "quantity": 2},
        {"unified_id": "prod_7790000000456", "quantity": 1},
    ]

    result = event["result"]
    assert result["status"] == "success"
    assert result["total_spent_net"] == 84210.55
    # El split viaja tal cual, sin tocar: los agregados por tienda los calcula el
    # analyzer, en un solo lugar.
    assert result["split"] is SUCCESS_RESULT["split"]
    assert result["price_savings_total"] == 6120.30

    engine = event["engine"]
    assert engine["suggestions_count"] == 1
    assert engine["strategic_swaps_count"] == 1
    assert engine["coto_covered"] is True
    assert engine["coto_delivery_source"] == "live"
    assert engine["duration_ms"] == 812


def test_price_savings_en_none_no_rompe():
    """api.py setea price_savings = None si su propio cálculo falla. Sin el
    `or {}` del adapter eso sería un AttributeError que se lleva puesto el evento
    entero por un número accesorio."""
    result = {**SUCCESS_RESULT, "price_savings": None}

    event = build_cart_optimized_event(_request(), result)

    assert event["result"]["price_savings_total"] is None
    assert event["result"]["total_spent_net"] == 84210.55


def test_infeasible_se_emite_con_split_vacio_y_montos_en_none():
    """
    Un carrito que no alcanza los mínimos no es un error a descartar: es el KPI
    de fricción. Los montos van a None y no a 0 — un cero se promediaría como una
    compra de $0 y hundiría el ticket promedio.
    """
    event = build_cart_optimized_event(_request(), INFEASIBLE_RESULT, duration_ms=95)

    result = event["result"]
    assert result["status"] == "infeasible"
    assert result["split"] == {}
    assert result["total_spent_net"] is None
    assert result["price_savings_total"] is None
    assert result["excluded_stores"] == ["coto_online"]

    # Las claves que sólo existen en el camino exitoso no pueden faltar en el
    # payload: el contrato las tipa con default, pero mandarlas explícitas evita
    # depender de esos defaults.
    assert event["engine"]["suggestions_count"] == 0
    assert event["engine"]["strategic_swaps_count"] == 0
    assert event["engine"]["coto_covered"] is False


def test_perfil_sin_datos_viaja_en_null_y_no_rompe():
    """Un perfil de localStorage anterior a la feature no trae anon_user_id, y el
    usuario puede haber salteado el onboarding de dirección."""
    event = build_cart_optimized_event(
        _request(anon_user_id=None, zone=None, user_memberships=None, user_cards=None),
        SUCCESS_RESULT,
    )

    assert event["user"]["anon_user_id"] is None
    assert event["user"]["zone"] is None
    # Listas y no None: el contrato las tipa como list con default_factory.
    assert event["user"]["memberships"] == []
    assert event["user"]["cards"] == []


def test_result_sin_bloque_de_logistica_no_rompe():
    """`logistics` lo agrega api.py después de llamar al optimizador. Si algún
    camino futuro no lo pone, el evento tiene que salir igual."""
    event = build_cart_optimized_event(_request(), {"status": "infeasible"})

    assert event["engine"]["coto_covered"] is None
    assert event["engine"]["coto_delivery_source"] is None


def test_env_configurable(monkeypatch):
    monkeypatch.setenv("ANALYTICS_ENV", "prod")

    event = build_cart_optimized_event(_request(), SUCCESS_RESULT)

    assert event["source"]["env"] == "prod"


# --- send_cart_optimized_event ------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_missing_key_flag():
    """El aviso de "falta la API key" se loguea una sola vez por proceso, con un
    flag de módulo. Sin resetearlo, el orden de los tests decidiría el resultado."""
    analytics._missing_key_logged = False
    yield
    analytics._missing_key_logged = False


def test_envio_manda_api_key_url_y_timeout(monkeypatch):
    monkeypatch.setenv("ANALYTICS_API_KEY", "una-clave")
    monkeypatch.setenv("ANALYTICS_URL", "http://localhost:8001/")

    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return httpx.Response(201, json={"status": "stored", "id": 1})

    monkeypatch.setattr(analytics.httpx, "post", fake_post)

    send_cart_optimized_event({"event_id": "abc"})

    # La barra final de ANALYTICS_URL no puede duplicarse en el path.
    assert captured["url"] == "http://localhost:8001/events/cart-optimized"
    assert captured["headers"] == {"X-API-Key": "una-clave"}
    assert captured["json"] == {"event_id": "abc"}
    assert captured["timeout"] == 2.0


def test_sin_api_key_no_emite_y_avisa_una_sola_vez(monkeypatch, caplog):
    monkeypatch.delenv("ANALYTICS_API_KEY", raising=False)

    def exploding_post(*args, **kwargs):
        raise AssertionError("no debería intentar emitir sin API key")

    monkeypatch.setattr(analytics.httpx, "post", exploding_post)

    with caplog.at_level("WARNING", logger="src.analytics"):
        send_cart_optimized_event({"event_id": "abc"})
        send_cart_optimized_event({"event_id": "def"})
        send_cart_optimized_event({"event_id": "ghi"})

    avisos = [r for r in caplog.records if "ANALYTICS_API_KEY" in r.getMessage()]
    assert len(avisos) == 1


def test_el_envio_nunca_lanza(monkeypatch, caplog):
    """
    EL invariante del módulo. La analítica no puede tumbar /optimize: si el
    analyzer está caído, timeoutea o el DNS no resuelve, esto loguea y sigue.
    """
    monkeypatch.setenv("ANALYTICS_API_KEY", "una-clave")

    def exploding_post(*args, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(analytics.httpx, "post", exploding_post)

    with caplog.at_level("ERROR", logger="src.analytics"):
        send_cart_optimized_event({"event_id": "abc"})  # no lanza

    assert any("No se pudo emitir" in r.getMessage() for r in caplog.records)


def test_un_rechazo_del_contrato_se_loguea(monkeypatch, caplog):
    """Un 422 silencioso es el peor final posible: el evento se pierde y el
    tablero aparece vacío meses después, sin ninguna pista de por qué."""
    monkeypatch.setenv("ANALYTICS_API_KEY", "una-clave")

    monkeypatch.setattr(
        analytics.httpx,
        "post",
        lambda *a, **kw: httpx.Response(422, json={"detail": [{"msg": "occurred_at naive"}]}),
    )

    with caplog.at_level("ERROR", logger="src.analytics"):
        send_cart_optimized_event({"event_id": "abc"})

    assert any("422" in r.getMessage() for r in caplog.records)
