"""
Tests de src/carrefour_logistics.py. Suite pura: sin red y sin base de datos —
todo sale de httpx.MockTransport.

Los payloads son recortes de respuestas reales de carrefour.com.ar (oct 2026):
si Carrefour cambia la forma, estos tests siguen pasando y el módulo se rompe en
producción. Mismo límite conocido que tests/test_dia_logistics.py.
"""
import json

import httpx
import pytest

from src import carrefour_logistics
from src.carrefour_logistics import check_coverage, resolve_carrefour_logistics


def sla(name, courier, price, *windows):
    return {
        "id": name,
        "deliveryChannel": "delivery",
        "price": price,
        "deliveryIds": [{"courierId": courier}],
        "availableDeliveryWindows": [{"price": p} for p in windows],
    }


RETIRO = {"id": "Retiro en Tienda (0775PR)", "deliveryChannel": "pickup-in-point", "price": 0, "deliveryIds": []}
HOGAR = sla("Envío Domicilio", "0899_DOM", 0, 329900)
HOGAR_CR = sla("Costo regulable Envío Domicilio", "0899_DOM_CR", 0, 499900)


def simulation(*slas):
    return {"logisticsInfo": [{"itemIndex": 0, "slas": list(slas)}], "minimumOrderValue": 200000}


# Palermo: la franja de Hogar & Electro es más barata, pero no es la del súper.
PALERMO = simulation(RETIRO, HOGAR, sla("Envío a Domicilio", "0026_DOM", 0, 399000, 399000), HOGAR_CR)
# Pilar: recargo de sucursal + franja = $6.339.
PILAR = simulation(RETIRO, HOGAR, HOGAR_CR, sla("Envío a Domicilio", "0183_DOM", 234900, 399000))
# Mar del Plata: franja gratis; el envío al interior es de Hogar & Electro.
MDQ = simulation(sla("Envío a Domicilio", "0022_DOM", 0, 0),
                 sla("Envío a Domicilio x Sucursal", "0899_DOM_INT", 359900))
# Ushuaia: sólo retiro.
USHUAIA = simulation(RETIRO)

COORD = (-34.361056, -58.751084)


@pytest.fixture(autouse=True)
def _limpiar_cache():
    carrefour_logistics.reset_cache()
    yield
    carrefour_logistics.reset_cache()


def make_client(payload, calls=None):
    def handler(request):
        if calls is not None:
            calls.append(request.url.path)
        if isinstance(payload, httpx.Response):
            return payload
        return httpx.Response(200, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_envio_es_recargo_de_sucursal_mas_franja():
    result = check_coverage(*COORD, client=make_client(PILAR))

    assert result == {"ok": True, "covered": True, "sucursal": "0183",
                      "mensaje": None, "delivery_cost": 6339.0}


def test_ignora_hogar_y_electro():
    result = check_coverage(*COORD, client=make_client(PALERMO))

    assert result["sucursal"] == "0026"
    assert result["delivery_cost"] == 3990.0


def test_franja_gratis():
    result = check_coverage(*COORD, client=make_client(MDQ))

    assert result["sucursal"] == "0022"
    assert result["delivery_cost"] == 0.0


def test_la_coordenada_viaja_como_lng_lat():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content)["geoCoordinates"])
        return httpx.Response(200, json=PILAR)

    check_coverage(*COORD, client=httpx.Client(transport=httpx.MockTransport(handler)))

    assert seen == [[-58.751084, -34.361056]]


def test_sin_envio_de_supermercado_no_hay_cobertura():
    for payload in (USHUAIA, simulation(HOGAR, HOGAR_CR)):
        carrefour_logistics.reset_cache()
        result = check_coverage(*COORD, client=make_client(payload))

        assert result["ok"] is True
        assert result["covered"] is False
        assert result["delivery_cost"] is None


def test_error_http_no_es_veredicto():
    assert check_coverage(*COORD, client=make_client(httpx.Response(500)))["ok"] is False


def test_html_no_es_veredicto():
    html = httpx.Response(200, text="<!DOCTYPE html><html></html>", headers={"content-type": "text/html"})
    assert check_coverage(*COORD, client=make_client(html))["ok"] is False


def test_el_exito_se_cachea_y_el_fallo_no():
    calls = []
    check_coverage(*COORD, client=make_client(PILAR, calls))
    check_coverage(*COORD, client=make_client(PILAR, calls))
    assert len(calls) == 1

    carrefour_logistics.reset_cache()
    check_coverage(*COORD, client=make_client(httpx.Response(500)))
    assert check_coverage(*COORD, client=make_client(PILAR))["ok"] is True


def test_resolve_con_cobertura_usa_el_costo_vivo():
    result = resolve_carrefour_logistics(*COORD, fallback_delivery_cost=3500, client=make_client(PILAR))

    assert result["covered"] is True
    assert result["delivery_cost"] == 6339.0
    assert result["source"] == "live"


def test_resolve_sin_cobertura_excluye_y_explica():
    result = resolve_carrefour_logistics(*COORD, fallback_delivery_cost=3500, client=make_client(USHUAIA))

    assert result["covered"] is False
    assert result["message"]


def test_resolve_es_fail_open():
    def handler(request):
        raise httpx.ConnectError("caído", request=request)

    result = resolve_carrefour_logistics(*COORD, fallback_delivery_cost=3500,
                                         client=httpx.Client(transport=httpx.MockTransport(handler)))

    assert result == {"covered": True, "sucursal": None, "delivery_cost": 3500,
                      "source": "fallback", "message": None}


def test_resolve_sin_coordenadas_no_consulta_nada():
    def handler(request):
        raise AssertionError("no debería llamar a la red")

    result = resolve_carrefour_logistics(None, None, fallback_delivery_cost=3500,
                                         client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert result["source"] == "fallback"
