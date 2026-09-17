# tests/test_http_retry.py
"""
Suite pura (sin Postgres, sin httpx real) de `src/scrapers/http_retry.py`.

Cubre las cuatro combinaciones que le importan al scraper que lo llama: éxito
directo, recuperación tras una falla transitoria (de transporte o de status), y
agotar los intentos en cada una de esas dos formas de fallar.
"""
import httpx
import pytest

from src.scrapers.http_retry import MAX_ATTEMPTS, request_with_retry


class _RespuestaFalsa:
    def __init__(self, status_code):
        self.status_code = status_code


def _secuencia(monkeypatch, resultados):
    """Devuelve una función que va agotando `resultados` en cada llamada."""
    restantes = list(resultados)

    def make_request():
        assert restantes, "se pidieron más intentos de los guionados"
        siguiente = restantes.pop(0)
        if isinstance(siguiente, Exception):
            raise siguiente
        return siguiente

    monkeypatch.setattr("time.sleep", lambda *_: None)
    return make_request


def test_exito_directo_no_reintenta(monkeypatch):
    make_request = _secuencia(monkeypatch, [_RespuestaFalsa(200)])

    respuesta = request_with_retry(make_request, "TEST")

    assert respuesta.status_code == 200


def test_recupera_tras_una_excepcion_de_transporte(monkeypatch):
    make_request = _secuencia(monkeypatch, [
        httpx.ConnectTimeout("timeout"),
        _RespuestaFalsa(200),
    ])

    respuesta = request_with_retry(make_request, "TEST")

    assert respuesta.status_code == 200


def test_recupera_tras_un_500_pasajero(monkeypatch):
    make_request = _secuencia(monkeypatch, [
        _RespuestaFalsa(500),
        _RespuestaFalsa(200),
    ])

    respuesta = request_with_retry(make_request, "TEST")

    assert respuesta.status_code == 200


def test_agota_los_intentos_y_relanza_la_excepcion_de_transporte(monkeypatch):
    make_request = _secuencia(monkeypatch, [httpx.ConnectTimeout("timeout")] * MAX_ATTEMPTS)

    with pytest.raises(httpx.ConnectTimeout):
        request_with_retry(make_request, "TEST")


def test_agota_los_intentos_y_devuelve_el_ultimo_500(monkeypatch):
    # A diferencia del caso de transporte, acá no hay excepción que relanzar:
    # se devuelve la última respuesta para que el llamador arme el mensaje de
    # error con el detalle (sección, página) que este módulo no conoce.
    make_request = _secuencia(monkeypatch, [_RespuestaFalsa(500)] * MAX_ATTEMPTS)

    respuesta = request_with_retry(make_request, "TEST")

    assert respuesta.status_code == 500


def test_un_404_no_se_reintenta(monkeypatch):
    make_request = _secuencia(monkeypatch, [_RespuestaFalsa(404)])

    respuesta = request_with_retry(make_request, "TEST")

    assert respuesta.status_code == 404
