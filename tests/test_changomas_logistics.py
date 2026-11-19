"""
Tests de src/changomas_logistics.py. Suite pura: sin red y sin base de datos —
todo sale de httpx.MockTransport.

Los payloads son recortes de respuestas reales de masonline.com.ar (nov 2026).
Mismo límite conocido que tests/test_vea_logistics.py: si ChangoMás cambia la
forma, estos tests siguen pasando y el módulo se rompe en producción.
"""
import httpx
import pytest

from src import changomas_logistics
from src.changomas_logistics import check_coverage, resolve_changomas_logistics

# Palermo: cuatro sellers "nacionales" que salen en todas las coordenadas y
# nunca tienen stock de almacén, y la sucursal 0015.
SELLERS = [{"id": "SW#x", "sellers": [{"id": "masonlineprod0008"}, {"id": "masonlineprod0015"}]}]

DOMICILIO = {"id": "Envío a domicilio", "name": "Envío a domicilio", "deliveryChannel": "delivery",
             "price": 0, "availableDeliveryWindows": [{"price": 399900}, {"price": 499900}]}


def simulation(*por_item):
    return {"logisticsInfo": [{"itemIndex": i, "slas": list(slas)} for i, slas in enumerate(por_item)]}


PALERMO = simulation([], [DOMICILIO])
SIN_STOCK = simulation([], [])

COORD = (-34.5889, -58.4306)


@pytest.fixture(autouse=True)
def _limpiar_cache():
    changomas_logistics.reset_cache()
    yield
    changomas_logistics.reset_cache()


def make_client(regions, sim, calls=None):
    def handler(request):
        if calls is not None:
            calls.append(request)
        payload = regions if request.url.path.endswith("/regions") else sim
        if isinstance(payload, httpx.Response):
            return payload
        return httpx.Response(200, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_sucursal_con_envio_a_domicilio_cubre_y_cotiza_sla_mas_franja():
    # preparar / ejecutar
    result = check_coverage(*COORD, client=make_client(SELLERS, PALERMO))

    # verificar
    assert result == {"ok": True, "covered": True, "sucursal": "masonlineprod0015",
                      "mensaje": None, "delivery_cost": 3999.0}


def test_una_sola_simulacion_con_un_item_por_sucursal_en_el_canal_1():
    # preparar
    calls = []

    # ejecutar
    check_coverage(*COORD, client=make_client(SELLERS, PALERMO, calls))

    # verificar
    simulaciones = [c for c in calls if c.url.path.endswith("/simulation")]
    assert len(simulaciones) == 1
    assert simulaciones[0].url.params["sc"] == "1"
    assert b"masonlineprod0008" in simulaciones[0].content


def test_regions_vacio_es_sin_cobertura():
    # preparar: Ushuaia, donde `regions` contesta []
    client = make_client([], PALERMO)

    # ejecutar
    result = check_coverage(*COORD, client=client)

    # verificar
    assert result["ok"] is True
    assert result["covered"] is False


def test_sellers_sin_stock_no_cuentan_como_cobertura():
    # preparar / ejecutar
    result = check_coverage(*COORD, client=make_client(SELLERS, SIN_STOCK))

    # verificar
    assert result["ok"] is True
    assert result["covered"] is False


@pytest.mark.parametrize("sim", [httpx.Response(500), httpx.Response(200, text="<html>"), {"items": []}])
def test_simulacion_rota_es_indeterminada(sim):
    assert check_coverage(*COORD, client=make_client(SELLERS, sim))["ok"] is False


def test_fallo_de_red_es_fail_open_al_fallback_y_no_se_cachea():
    # preparar
    caido = make_client(httpx.Response(503), PALERMO)

    # ejecutar
    info = resolve_changomas_logistics(*COORD, fallback_delivery_cost=3999.0, client=caido)
    despues = check_coverage(*COORD, client=make_client(SELLERS, PALERMO))

    # verificar
    assert info == {"covered": True, "sucursal": None, "delivery_cost": 3999.0,
                    "source": "fallback", "message": None}
    assert despues["covered"] is True
