"""
Tests de src/dia_logistics.py. Suite pura: sin red y sin base de datos — todo
sale de httpx.MockTransport.

Los payloads son recortes de respuestas reales de diaonline (oct 2026): si Día
cambia la forma, estos tests siguen pasando y el módulo se rompe en producción.
Mismo límite conocido que tests/test_coto_logistics.py.
"""
import json

import httpx
import pytest

from src import dia_logistics
from src.dia_logistics import check_coverage, resolve_dia_logistics

# Moreno (-34.6351713, -58.8611855): dos sucursales, sólo la 1019 envía.
REGIONS_MORENO = [{
    "id": "U1cjYXJkaWFwcm9kMTAxOTthcmRpYXByb2QxNzc=",
    "sellers": [
        {"id": "ardiaprod1019", "name": "Tienda Moreno", "logo": ""},
        {"id": "ardiaprod177", "name": "ardiaprod177", "logo": ""},
    ],
}]

# Córdoba capital: fuera de zona.
REGIONS_CORDOBA = [{"id": "U1cj", "sellers": []}]


def simulation(*slas):
    return {
        "logisticsInfo": [{"itemIndex": 0, "addressId": "simulation", "slas": list(slas)}],
        "messages": [{"code": "withoutPriceFulfillment", "text": "El ítem Dummy Modal no está disponible"}],
        "minimumOrderValue": 1200000,
    }


ENVIO = {"id": "Envío a Domicilio", "deliveryChannel": "delivery", "price": 499900, "polygonName": "P1019Ev5"}
RETIRO = {"id": "Retiro en Tienda (pup177P)", "deliveryChannel": "pickup-in-point", "price": 79900}

SIMULATIONS = {"ardiaprod1019": simulation(ENVIO), "ardiaprod177": simulation(RETIRO)}

MORENO = (-34.6351713, -58.8611855)
CORDOBA = (-31.4201, -64.1888)


@pytest.fixture(autouse=True)
def _limpiar_cache():
    dia_logistics.reset_cache()
    yield
    dia_logistics.reset_cache()


def make_client(regions, simulations=SIMULATIONS, calls=None):
    def handler(request):
        if calls is not None:
            calls.append(request.url.path)
        if request.url.path.endswith("/regions"):
            return httpx.Response(200, json=regions)
        seller = json.loads(request.content)["items"][0]["seller"]
        payload = simulations[seller]
        if isinstance(payload, httpx.Response):
            return payload
        return httpx.Response(200, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_cubre_si_alguna_sucursal_envia_aunque_otra_solo_haga_retiro():
    result = check_coverage(*MORENO, client=make_client(REGIONS_MORENO))

    assert result == {"ok": True, "covered": True, "sucursal": "ardiaprod1019",
                      "mensaje": None, "delivery_cost": 4999.0}


def test_la_coordenada_viaja_como_lng_lat():
    seen = []

    def handler(request):
        if request.url.path.endswith("/regions"):
            seen.append(request.url.params["geoCoordinates"])
            return httpx.Response(200, json=REGIONS_MORENO)
        seen.append(json.loads(request.content)["shippingData"]["selectedAddresses"][0]["geoCoordinates"])
        return httpx.Response(200, json=simulation(ENVIO))

    check_coverage(*MORENO, client=httpx.Client(transport=httpx.MockTransport(handler)))

    assert seen[0] == "-58.8611855;-34.6351713"
    assert seen[1] == [-58.8611855, -34.6351713]


def test_sin_sucursales_no_hay_cobertura():
    result = check_coverage(*CORDOBA, client=make_client(REGIONS_CORDOBA))

    assert result["ok"] is True
    assert result["covered"] is False
    assert result["delivery_cost"] is None


def test_si_todas_solo_hacen_retiro_no_hay_cobertura():
    simulations = {"ardiaprod1019": simulation(RETIRO), "ardiaprod177": simulation(RETIRO)}
    result = check_coverage(*MORENO, client=make_client(REGIONS_MORENO, simulations))

    assert result["ok"] is True
    assert result["covered"] is False


def test_se_queda_con_el_envio_mas_barato():
    caro = dict(ENVIO, price=599900)
    simulations = {"ardiaprod1019": simulation(caro), "ardiaprod177": simulation(RETIRO, ENVIO)}
    result = check_coverage(*MORENO, client=make_client(REGIONS_MORENO, simulations))

    assert result["sucursal"] == "ardiaprod177"
    assert result["delivery_cost"] == 4999.0


def test_una_simulacion_fallida_no_es_veredicto():
    """Si la sucursal que no respondió era la que envía, decir "no llega" mentiría."""
    simulations = {"ardiaprod1019": httpx.Response(500), "ardiaprod177": simulation(RETIRO)}
    result = check_coverage(*MORENO, client=make_client(REGIONS_MORENO, simulations))

    assert result["ok"] is False


def test_html_no_es_veredicto():
    client = httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, text="<!DOCTYPE html><html></html>", headers={"content-type": "text/html"})))
    assert check_coverage(*MORENO, client=client)["ok"] is False


def test_timeout_no_es_veredicto():
    def handler(request):
        raise httpx.ConnectTimeout("timeout", request=request)

    assert check_coverage(*MORENO, client=httpx.Client(transport=httpx.MockTransport(handler)))["ok"] is False


def test_el_exito_se_cachea_y_el_fallo_no():
    calls = []
    check_coverage(*MORENO, client=make_client(REGIONS_MORENO, calls=calls))
    check_coverage(*MORENO, client=make_client(REGIONS_MORENO, calls=calls))
    assert len(calls) == 3  # regions + dos simulaciones, una sola vez

    dia_logistics.reset_cache()
    failing = {"ardiaprod1019": httpx.Response(500), "ardiaprod177": simulation(RETIRO)}
    check_coverage(*MORENO, client=make_client(REGIONS_MORENO, failing))
    assert check_coverage(*MORENO, client=make_client(REGIONS_MORENO))["ok"] is True


def test_resolve_con_cobertura_usa_el_costo_vivo():
    result = resolve_dia_logistics(*MORENO, fallback_delivery_cost=3500, client=make_client(REGIONS_MORENO))

    assert result["covered"] is True
    assert result["delivery_cost"] == 4999.0
    assert result["source"] == "live"


def test_resolve_sin_cobertura_excluye_y_explica():
    result = resolve_dia_logistics(*CORDOBA, fallback_delivery_cost=3500, client=make_client(REGIONS_CORDOBA))

    assert result["covered"] is False
    assert result["message"]


def test_resolve_es_fail_open():
    def handler(request):
        raise httpx.ConnectError("caído", request=request)

    result = resolve_dia_logistics(*MORENO, fallback_delivery_cost=3500,
                                   client=httpx.Client(transport=httpx.MockTransport(handler)))

    assert result == {"covered": True, "sucursal": None, "delivery_cost": 3500,
                      "source": "fallback", "message": None}


def test_resolve_sin_coordenadas_no_consulta_nada():
    def handler(request):
        raise AssertionError("no debería llamar a la red")

    result = resolve_dia_logistics(None, None, fallback_delivery_cost=3500,
                                   client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert result["source"] == "fallback"


# --------------------------------------------------------------------------
# quote_cart: el envío del carrito real, que depende del peso (issue #15)
# --------------------------------------------------------------------------

SAN_ISIDRO = (-34.4708, -58.5286)


def cart_client(payload, seen=None):
    def handler(request):
        if seen is not None:
            seen.append(json.loads(request.content))
        return httpx.Response(200, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def cart_simulation(items, *lines):
    """`lines`: los SLAs de cada línea de la respuesta, en orden."""
    return {
        "items": [{"id": sku, "quantity": qty} for sku, qty in items],
        "logisticsInfo": [{"itemIndex": i, "slas": list(slas)} for i, slas in enumerate(lines)],
    }


def envio(price, name="Envío a Domicilio"):
    return {"id": name, "deliveryChannel": "delivery", "price": price}


def test_quote_cart_suma_el_sla_repartido_entre_lineas():
    # Real (oct 2026): 3 alfajores vuelven en dos líneas y VTEX reparte el
    # envío de $4.999 entre las dos.
    payload = cart_simulation([("289319", 2), ("289319", 1)], [envio(166632)], [envio(333268)])
    assert dia_logistics.quote_cart(*SAN_ISIDRO, "ardiaprod1004", [("289319", 3)],
                                    client=cart_client(payload)) == 4999.0


def test_quote_cart_manda_los_items_reales_a_la_sucursal():
    seen = []
    payload = cart_simulation([("295616", 6)], [envio(689900)])
    quote = dia_logistics.quote_cart(*SAN_ISIDRO, "ardiaprod1004", [("295616", 6)],
                                     client=cart_client(payload, seen))
    assert quote == 6899.0
    assert seen[0]["items"] == [{"id": "295616", "quantity": 6, "seller": "ardiaprod1004"}]


def test_quote_cart_toma_el_sla_mas_barato_que_ofrecen_todas_las_lineas():
    payload = cart_simulation(
        [("a", 1), ("b", 1)],
        [envio(300000), envio(100000, "Express")],
        [envio(300000)],
    )
    # "Express" no lo ofrece la segunda línea: no es un envío posible del carrito.
    assert dia_logistics.quote_cart(*SAN_ISIDRO, "s", [("a", 1), ("b", 1)],
                                    client=cart_client(payload)) == 6000.0


def test_quote_cart_sin_envio_en_una_linea_es_none():
    # Una línea sin stock en la sucursal: cotizar sin ella sería cotizar un
    # carrito más liviano.
    payload = cart_simulation([("a", 1), ("b", 1)], [envio(499900)], [])
    assert dia_logistics.quote_cart(*SAN_ISIDRO, "s", [("a", 1), ("b", 1)],
                                    client=cart_client(payload)) is None


def test_quote_cart_con_un_item_que_no_volvio_es_none():
    payload = cart_simulation([("a", 1)], [envio(499900)])
    assert dia_logistics.quote_cart(*SAN_ISIDRO, "s", [("a", 1), ("b", 1)],
                                    client=cart_client(payload)) is None


def test_quote_cart_no_lanza_si_dia_no_contesta():
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    assert dia_logistics.quote_cart(*SAN_ISIDRO, "s", [("a", 1)], client=client) is None
