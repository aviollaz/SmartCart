"""
Tests de src/jumbo_logistics.py. Suite pura: sin red y sin base de datos — todo
sale de httpx.MockTransport.

Los payloads son recortes de respuestas reales de jumbo.com.ar (nov 2026). Mismo
límite conocido que tests/test_vea_logistics.py: si Jumbo cambia la forma, estos
tests siguen pasando y el módulo se rompe en producción.
"""
import httpx
import pytest

from src import jumbo_logistics
from src.jumbo_logistics import check_coverage

SELLERS = [{"id": "v2.509F", "sellers": [{"id": "jumboargentinaj5206palermo"},
                                         {"id": "jumboargentinaj5204lomas"}]}]


def sla(name, price, *windows):
    return {"id": name, "name": name, "deliveryChannel": "delivery", "price": price,
            "availableDeliveryWindows": [{"price": p} for p in windows]}


RETIRO_PALERMO = sla("Retiro en Tienda - Jumbo Palermo Av. Bullrich 345  y Cerviño", 0)
DOMICILIO = sla("Envío a Domicilio", 0, 399900, 399900)
RETIRO_LOMAS = sla("Retiro en Tienda - Jumbo Lomas", 0)


def simulation(*por_item):
    return {"logisticsInfo": [{"itemIndex": i, "slas": list(slas)} for i, slas in enumerate(por_item)]}


COORD = (-34.6, -58.4)


@pytest.fixture(autouse=True)
def _limpiar_cache():
    jumbo_logistics.reset_cache()
    yield
    jumbo_logistics.reset_cache()


def make_client(regions, sim, calls=None):
    def handler(request):
        if calls is not None:
            calls.append(request)
        payload = regions if request.url.path.endswith("/regions") else sim
        return httpx.Response(200, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_jumbo_palermo_envia_y_cobra_sla_mas_franja():
    # preparar: CABA, la sucursal Palermo trae "Envío a Domicilio" a 0 + $3.999
    cliente = make_client(SELLERS, simulation([RETIRO_PALERMO, DOMICILIO], [RETIRO_LOMAS]))

    # ejecutar
    result = check_coverage(*COORD, client=cliente)

    # verificar
    assert result == {"ok": True, "covered": True, "sucursal": "jumboargentinaj5206palermo",
                      "mensaje": None, "delivery_cost": 3999.0}


def test_jumbo_solo_retiro_no_cubre():
    # preparar: Córdoba, todas las sucursales ofrecen sólo retiro
    cliente = make_client(SELLERS, simulation([RETIRO_PALERMO], [RETIRO_LOMAS]))

    # ejecutar
    result = check_coverage(-31.42, -64.18, client=cliente)

    # verificar
    assert result["ok"] is True
    assert result["covered"] is False


def test_jumbo_sin_sucursales_es_indeterminado():
    # preparar: `regions` no mira la coordenada, así que vacío es una respuesta rara
    cliente = make_client([], simulation([DOMICILIO]))

    # ejecutar
    result = check_coverage(*COORD, client=cliente)

    # verificar
    assert result["ok"] is False


def test_jumbo_simula_con_canal_32():
    # preparar
    calls = []
    cliente = make_client(SELLERS, simulation([DOMICILIO], []), calls)

    # ejecutar
    check_coverage(*COORD, client=cliente)

    # verificar
    assert [c.url.host for c in calls] == ["www.jumbo.com.ar", "www.jumbo.com.ar"]
    assert [c.url.params["sc"] for c in calls] == ["32", "32"]
