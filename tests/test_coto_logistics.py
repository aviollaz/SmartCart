"""
Tests de src/coto_logistics.py. Suite pura: sin red y sin base de datos — todo
sale de httpx.MockTransport.

Los payloads de abajo son capturas reales del sitio de Coto (julio 2026), no
inventos: si Coto cambia la forma de la respuesta, estos tests siguen pasando y
el módulo se rompe en producción. Ese es el límite conocido de un fixture
congelado, y es preferible a depender de la red en el suite.
"""
import httpx
import pytest

from src import coto_logistics
from src.coto_logistics import (
    check_coverage,
    get_shipping_cost,
    parse_amount,
    resolve_coto_logistics,
)

# --- Payloads reales capturados contra www.coto.com.ar -----------------------

# lat=-34.6037&lng=-58.3816 (Obelisco, CABA)
COBERTURA_CABA = {
    "sucursal": {
        "@class": "atg.dto.backOffice.DtoSucursalCobertura",
        "coberturaCD": 1,
        "codigoError": "0",
        "mensajeError": "-",
        "sucursal": "220",
    }
}

# lat=-54.8019&lng=-68.3030 (Ushuaia) y también Córdoba capital: misma respuesta.
COBERTURA_SIN_COBERTURA = {
    "sucursal": {
        "@class": "atg.dto.backOffice.DtoSucursalCobertura",
        "coberturaCD": 0,
        "codigoError": "1",
        "mensajeError": (
            "El domicilio registrado tiene cobertura limitada solo para la compra de "
            "electrodomésticos con retiro en sucursal. Si desea adquirir otros productos "
            "por favor comuníquese con nosotros al 0810-888-2686 para ser asesorado."
        ),
        "sucursal": "0",
    }
}

# Respuesta de error de un actor ATG: JSON válido, pero sin "sucursal".
ERROR_ACTOR = {
    "codigoError": "2",
    "error": {
        "localizedMessage": "Atencion: Debe estar logueado para acceder a este recurso",
        "messageCode": "USER_NOT_AUTHENTICATED",
    },
    "mensajeError": "Debe estar logueado para acceder a este recurso",
}

# Recorte de getParametros2 (la respuesta real trae ~380 parámetros).
PARAMETROS = {
    "codigoError": "0",
    "productoDetalle": [
        {"nombre": "MINIMOGENERAL", "formulario": "GENERALES", "valor": "30000"},
        {"nombre": "ENTREGA_RAPIDA_COSTO", "formulario": "GENERAL", "valor": "3399"},
        {"nombre": "MONTO_MINIMO", "formulario": "PROMOCION_ENVIO", "valor": "5000"},
    ],
}

# El SPA Angular sirve esto con HTTP 200 para cualquier ruta que no conoce.
SPA_HTML = '<!DOCTYPE html><html lang="es-AR"><head><title>Coto Digital</title></head></html>'


# --- Helpers ----------------------------------------------------------------


def make_client(handler):
    """Cliente httpx con transporte simulado; `handler` recibe el request."""
    return httpx.Client(transport=httpx.MockTransport(handler))


def json_handler(payload, status_code=200):
    def handler(request):
        return httpx.Response(status_code, json=payload)

    return handler


@pytest.fixture(autouse=True)
def _limpiar_cache():
    """El caché es estado de módulo: sin esto un test contamina al siguiente."""
    coto_logistics.reset_cache()
    yield
    coto_logistics.reset_cache()


# --- Cobertura --------------------------------------------------------------


def test_caba_tiene_cobertura():
    with make_client(json_handler(COBERTURA_CABA)) as client:
        result = check_coverage(-34.6037, -58.3816, client=client)

    assert result["ok"] is True
    assert result["covered"] is True
    assert result["sucursal"] == "220"
    assert result["mensaje"] is None


def test_sucursal_cero_no_tiene_cobertura():
    with make_client(json_handler(COBERTURA_SIN_COBERTURA)) as client:
        result = check_coverage(-54.8019, -68.3030, client=client)

    assert result["ok"] is True
    assert result["covered"] is False
    assert result["sucursal"] == "0"
    assert "cobertura limitada" in result["mensaje"]


def test_sucursal_133_no_tiene_cobertura():
    payload = {"sucursal": {"mensajeError": "-", "sucursal": "133"}}
    with make_client(json_handler(payload)) as client:
        result = check_coverage(-34.6, -58.4, client=client)

    assert result["covered"] is False


def test_mensaje_de_error_excluye_aunque_la_sucursal_parezca_valida():
    payload = {"sucursal": {"mensajeError": "Fuera de zona", "sucursal": "220"}}
    with make_client(json_handler(payload)) as client:
        result = check_coverage(-34.6, -58.4, client=client)

    assert result["covered"] is False
    assert result["mensaje"] == "Fuera de zona"


def test_sucursal_numerica_se_normaliza_a_string():
    payload = {"sucursal": {"mensajeError": "-", "sucursal": 0}}
    with make_client(json_handler(payload)) as client:
        result = check_coverage(-34.6, -58.4, client=client)

    # El JSON trae la sucursal como string, pero si algún día viene numérica
    # comparar contra {"0", "133"} sin convertir daría "hay cobertura".
    assert result["sucursal"] == "0"
    assert result["covered"] is False


# --- Indeterminación: nunca debe leerse como "no hay cobertura" -------------


def test_html_del_spa_no_es_veredicto():
    def handler(request):
        return httpx.Response(200, text=SPA_HTML, headers={"content-type": "text/html"})

    with make_client(handler) as client:
        result = check_coverage(-34.6, -58.4, client=client)

    assert result["ok"] is False
    assert result["covered"] is None


def test_respuesta_de_error_del_actor_no_es_veredicto():
    with make_client(json_handler(ERROR_ACTOR)) as client:
        result = check_coverage(-34.6, -58.4, client=client)

    assert result["ok"] is False
    assert result["covered"] is None


def test_timeout_no_es_veredicto():
    def handler(request):
        raise httpx.ConnectTimeout("timeout")

    with make_client(handler) as client:
        result = check_coverage(-34.6, -58.4, client=client)

    assert result["ok"] is False


def test_http_500_no_es_veredicto():
    with make_client(json_handler({}, status_code=500)) as client:
        result = check_coverage(-34.6, -58.4, client=client)

    assert result["ok"] is False


# --- Costo de envío ---------------------------------------------------------


def test_costo_de_envio_sale_de_los_parametros():
    with make_client(json_handler(PARAMETROS)) as client:
        assert get_shipping_cost(client=client) == 3399


def test_costo_de_envio_none_si_falta_el_parametro():
    payload = {"productoDetalle": [{"nombre": "OTRA_COSA", "valor": "1"}]}
    with make_client(json_handler(payload)) as client:
        assert get_shipping_cost(client=client) is None


def test_costo_de_envio_none_si_la_respuesta_es_html():
    def handler(request):
        return httpx.Response(200, text=SPA_HTML, headers={"content-type": "text/html"})

    with make_client(handler) as client:
        assert get_shipping_cost(client=client) is None


@pytest.mark.parametrize(
    "raw, esperado",
    [
        ("3399", 3399),
        (3399, 3399),
        (3399.0, 3399),
        ("3399.50", 3400),
        ("$3399", 3399),
        ("3.399,00", 3399),
        ("1.234,56", 1235),
        ("", None),
        ("gratis", None),
        (None, None),
    ],
)
def test_parse_amount(raw, esperado):
    assert parse_amount(raw) == esperado


# --- Caché ------------------------------------------------------------------


def test_la_cobertura_se_cachea_por_coordenada():
    llamadas = []

    def handler(request):
        llamadas.append(request.url)
        return httpx.Response(200, json=COBERTURA_CABA)

    with make_client(handler) as client:
        check_coverage(-34.6037, -58.3816, client=client)
        check_coverage(-34.6037, -58.3816, client=client)

    assert len(llamadas) == 1


def test_una_coordenada_distinta_no_usa_el_cache():
    llamadas = []

    def handler(request):
        llamadas.append(request.url)
        return httpx.Response(200, json=COBERTURA_CABA)

    with make_client(handler) as client:
        check_coverage(-34.6037, -58.3816, client=client)
        check_coverage(-31.4201, -64.1888, client=client)

    assert len(llamadas) == 2


def test_las_respuestas_indeterminadas_no_se_cachean():
    """Un timeout no debe dejar clavado el fallback durante 30 minutos."""
    llamadas = []

    def handler(request):
        llamadas.append(request.url)
        raise httpx.ConnectTimeout("timeout")

    with make_client(handler) as client:
        check_coverage(-34.6, -58.4, client=client)
        check_coverage(-34.6, -58.4, client=client)

    assert len(llamadas) == 2


# --- Orquestación / fail-open ----------------------------------------------


def routing_handler(cobertura_payload, parametros_payload=PARAMETROS):
    """Despacha según la URL, para poder ejercitar resolve_coto_logistics()."""

    def handler(request):
        if "getCobertura" in str(request.url):
            return httpx.Response(200, json=cobertura_payload)
        return httpx.Response(200, json=parametros_payload)

    return handler


def test_resolve_con_cobertura_usa_el_costo_vivo():
    with make_client(routing_handler(COBERTURA_CABA)) as client:
        result = resolve_coto_logistics(-34.6037, -58.3816, fallback_delivery_cost=2500, client=client)

    assert result["covered"] is True
    assert result["delivery_cost"] == 3399
    assert result["source"] == "live"
    assert result["sucursal"] == "220"


def test_resolve_sin_cobertura_excluye_y_explica():
    with make_client(routing_handler(COBERTURA_SIN_COBERTURA)) as client:
        result = resolve_coto_logistics(-54.8019, -68.3030, fallback_delivery_cost=2500, client=client)

    assert result["covered"] is False
    assert result["delivery_cost"] is None
    assert "cobertura limitada" in result["message"]


def test_resolve_es_fail_open_ante_un_fallo_de_red():
    def handler(request):
        raise httpx.ConnectTimeout("timeout")

    with make_client(handler) as client:
        result = resolve_coto_logistics(-34.6, -58.4, fallback_delivery_cost=2500, client=client)

    assert result["covered"] is True
    assert result["delivery_cost"] == 2500
    assert result["source"] == "fallback"


def test_resolve_con_cobertura_cae_al_fallback_si_no_hay_costo():
    """Hay cobertura confirmada pero los parámetros no traen la tarifa."""
    sin_costo = {"productoDetalle": []}
    with make_client(routing_handler(COBERTURA_CABA, sin_costo)) as client:
        result = resolve_coto_logistics(-34.6037, -58.3816, fallback_delivery_cost=2500, client=client)

    assert result["covered"] is True
    assert result["delivery_cost"] == 2500
    assert result["source"] == "fallback"


def test_resolve_sin_coordenadas_no_consulta_nada():
    def handler(request):
        raise AssertionError("no debería salir a la red sin coordenadas")

    with make_client(handler) as client:
        result = resolve_coto_logistics(None, None, fallback_delivery_cost=2500, client=client)

    assert result["covered"] is True
    assert result["delivery_cost"] == 2500
    assert result["source"] == "fallback"
