"""
Tests de src/vea_logistics.py. Suite pura: sin red y sin base de datos — todo
sale de httpx.MockTransport.

Los payloads son recortes de respuestas reales de vea.com.ar (oct 2026). Mismo
límite conocido que tests/test_dia_logistics.py: si Vea cambia la forma, estos
tests siguen pasando y el módulo se rompe en producción.
"""
import httpx
import pytest

from src import vea_logistics
from src.vea_logistics import check_coverage, resolve_vea_logistics

SELLERS = [{"id": "SW#x", "sellers": [{"id": "jumboargentinav700cordoba700"}, {"id": "jumboargentinav153moroni"}]}]


def sla(name, courier, price, *windows):
    return {"id": name, "name": name, "deliveryChannel": "delivery", "price": price,
            "deliveryIds": [{"courierId": courier}],
            "availableDeliveryWindows": [{"price": p} for p in windows]}


RETIRO = sla("Retiro en Tienda - Av Córdoba 6103 CABA", "sm9700rt", 0)
EN_AUTO = sla("Retira en Auto - Av Córdoba 6103 CABA", "sm9700ra", 0)
DOMICILIO = sla("Envío a Domicilio", "sm700ed", 0, 349900, 349900)


def simulation(*por_item):
    return {"logisticsInfo": [{"itemIndex": i, "slas": list(slas)} for i, slas in enumerate(por_item)]}


# Palermo: la sucursal 700 envía; Morón sólo ofrece retiro.
PALERMO = simulation([RETIRO, EN_AUTO, DOMICILIO], [sla("Retiro en Tienda - Morón", "sm153rt", 0)])
# Pilar: todo es retiro, aunque el canal diga "delivery".
PILAR = simulation([RETIRO, EN_AUTO], [])

COORD = (-34.5889, -58.4307)


@pytest.fixture(autouse=True)
def _limpiar_cache():
    vea_logistics.reset_cache()
    yield
    vea_logistics.reset_cache()


def make_client(regions, sim, calls=None):
    def handler(request):
        if calls is not None:
            calls.append(request)
        payload = regions if request.url.path.endswith("/regions") else sim
        if isinstance(payload, httpx.Response):
            return payload
        return httpx.Response(200, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_envio_a_domicilio_es_franja_mas_precio():
    result = check_coverage(*COORD, client=make_client(SELLERS, PALERMO))

    assert result == {"ok": True, "covered": True, "sucursal": "jumboargentinav700cordoba700",
                      "mensaje": None, "delivery_cost": 3499.0}


def test_una_sola_simulacion_con_un_item_por_sucursal():
    calls = []
    check_coverage(*COORD, client=make_client(SELLERS, PALERMO, calls))

    simulaciones = [c for c in calls if c.url.path.endswith("/simulation")]
    assert len(simulaciones) == 1
    assert simulaciones[0].url.params["sc"] == "34"
    assert b"jumboargentinav153moroni" in simulaciones[0].content


def test_los_retiros_no_son_envio_aunque_el_canal_diga_delivery():
    result = check_coverage(*COORD, client=make_client(SELLERS, PILAR))

    assert result["ok"] is True
    assert result["covered"] is False


def test_sin_sucursales_es_indeterminado_y_no_un_no():
    # `regions` no mira la coordenada: una lista vacía es una respuesta rara.
    assert check_coverage(*COORD, client=make_client([], PALERMO))["ok"] is False


@pytest.mark.parametrize("sim", [httpx.Response(500), httpx.Response(200, text="<html>"), {"items": []}])
def test_simulacion_rota_es_indeterminada(sim):
    assert check_coverage(*COORD, client=make_client(SELLERS, sim))["ok"] is False


def test_resolve_sin_respuesta_cae_al_fallback():
    info = resolve_vea_logistics(*COORD, fallback_delivery_cost=3499.0,
                                 client=make_client(httpx.Response(503), PALERMO))

    assert info == {"covered": True, "sucursal": None, "delivery_cost": 3499.0,
                    "source": "fallback", "message": None}
