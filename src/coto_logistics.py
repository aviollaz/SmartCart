# src/coto_logistics.py
"""
Consulta en línea de la logística de Coto: si entregan en una coordenada dada y
cuánto cobran por el envío.

No vive en src/scrapers/ a propósito: esto se resuelve por request dentro de
/optimize, no es ingesta de catálogo.

Sobre los endpoints (relevado contra el sitio en vivo, no contra documentación):

- El sitio viejo (cotodigital3.com.ar / cotodigital.com.ar) redirige entero a
  www.coto.com.ar, que es un SPA Angular. Los endpoints `/getCobertura` y
  `/getCostoEnvio` a la raíz del dominio ya no existen: cualquier ruta
  desconocida devuelve el index.html del SPA con HTTP 200, así que un cliente
  descuidado parsea basura en vez de fallar. De ahí que acá se valide que la
  respuesta sea JSON antes de creerle.

- Las rutas reales son los actors ATG que consume el propio bundle del SPA,
  colgados de /rest/model. Ambas son **públicas**: no hace falta login, ni
  cookie de sesión, ni el token `_dynSessConf` que el sitio manda en otras
  llamadas. Se probó con y sin token y devuelven exactamente lo mismo.

- NO existe un endpoint de costo de envío por dirección. En el bundle no hay una
  sola aparición de "costo"/"importe", y los actors que sí calculan envío
  (getGrillaCupos, getCuposHoy, getEntregaRapida) responden
  USER_NOT_AUTHENTICATED: el envío real de Coto es función de un carrito armado
  en su servidor por un usuario logueado, no de la coordenada sola. Lo que sí se
  puede leer sin auth es la tarifa de entrega rápida publicada en la config
  (ENTREGA_RAPIDA_COSTO). Es un único número global, igual para toda dirección
  con cobertura — pero es el número vigente de Coto y no una estimación nuestra.
"""
import time

import httpx

BASE_URL = "https://www.coto.com.ar/rest/model"
COBERTURA_URL = f"{BASE_URL}/atg/actors/cProfileActor/getCobertura"
PARAMETROS_URL = f"{BASE_URL}/atg/actors/cProfileActor/getParametros2"

# Nombre del parámetro de config que trae la tarifa de envío vigente.
COSTO_ENVIO_PARAM = "ENTREGA_RAPIDA_COSTO"

# `mensajeError` vale exactamente "-" cuando el domicilio tiene cobertura plena.
# Es la misma comparación que hace el frontend de Coto.
SIN_ERROR = "-"

# Sucursales que significan "no te llegamos". El "0" se observó en vivo para
# Ushuaia y Córdoba; el "133" viene del relevamiento previo y se mantiene como
# guarda porque no cuesta nada y el caso no es reproducible a demanda.
SUCURSALES_SIN_COBERTURA = {"0", "133"}

TIMEOUT_SECONDS = 6.0
CACHE_TTL_SECONDS = 30 * 60

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:152.0) Gecko/20100101 Firefox/152.0",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-AR,es;q=0.9",
    "Referer": "https://www.coto.com.ar/",
    "Origin": "https://www.coto.com.ar",
}

# {clave: (timestamp, valor)}. Sin esto cada /optimize paga dos round-trips
# contra coto.com.ar. Se limpia con reset_cache() en los tests.
_cache: dict = {}


def reset_cache() -> None:
    """Vacía el caché en memoria. Existe para los tests."""
    _cache.clear()


def _cache_get(key):
    entry = _cache.get(key)
    if entry is None:
        return None

    stored_at, value = entry
    if time.monotonic() - stored_at > CACHE_TTL_SECONDS:
        _cache.pop(key, None)
        return None

    return value


def _cache_put(key, value) -> None:
    _cache[key] = (time.monotonic(), value)


def _fetch_json(url: str, params: dict | None = None, client: httpx.Client | None = None):
    """
    GET que devuelve el JSON o None, sin propagar nunca una excepción.

    Exige que el content-type sea JSON: como el SPA sirve su index.html con
    HTTP 200 para rutas inexistentes, chequear sólo el status code haría pasar
    una página HTML por una respuesta válida.
    """
    owned = client is None
    if owned:
        client = httpx.Client(headers=_HEADERS, timeout=TIMEOUT_SECONDS, follow_redirects=True)

    try:
        response = client.get(url, params=params)
        if response.status_code != 200:
            return None
        if "json" not in (response.headers.get("content-type") or "").lower():
            return None
        return response.json()
    except Exception:
        return None
    finally:
        if owned:
            client.close()


def parse_amount(raw) -> int | None:
    """
    Normaliza a entero un monto que puede venir como int, float o string.

    La config devuelve "3399" (string), pero se toleran float y separadores
    porque el valor lo edita gente desde un back-office. Con coma presente se
    asume formato local (1.234,56); sin coma, el punto se lee como decimal.
    """
    if raw is None or isinstance(raw, bool):
        return None

    if isinstance(raw, (int, float)):
        return int(round(raw))

    text = str(raw).strip().replace("$", "").replace(" ", "")
    if not text:
        return None

    if "," in text:
        text = text.replace(".", "").replace(",", ".")

    try:
        return int(round(float(text)))
    except ValueError:
        return None


def check_coverage(lat: float, lng: float, client: httpx.Client | None = None) -> dict:
    """
    Pregunta a Coto si entrega en (lat, lng).

    Devuelve {"ok", "covered", "sucursal", "mensaje"}. `ok=False` significa "no
    se pudo determinar" (red caída, HTML en vez de JSON, respuesta de error del
    actor) y NO debe leerse como falta de cobertura: sólo un veredicto
    afirmativo de Coto excluye la tienda.

    El payload real anida todo bajo "sucursal":

        {"sucursal": {"coberturaCD": 1, "codigoError": "0",
                      "mensajeError": "-", "sucursal": "220"}}
    """
    key = ("coverage", round(float(lat), 4), round(float(lng), 4))
    cached = _cache_get(key)
    if cached is not None:
        return cached

    data = _fetch_json(COBERTURA_URL, {"lat": lat, "lng": lng}, client=client)

    # Las respuestas de error del actor (ej. USER_NOT_AUTHENTICATED) son JSON
    # válido pero no traen "sucursal": son indeterminación, no un "no llegamos".
    sucursal_info = data.get("sucursal") if isinstance(data, dict) else None
    if not isinstance(sucursal_info, dict):
        return {"ok": False, "covered": None, "sucursal": None, "mensaje": None}

    mensaje = sucursal_info.get("mensajeError")
    sucursal = sucursal_info.get("sucursal")
    sucursal = str(sucursal) if sucursal is not None else None

    covered = mensaje == SIN_ERROR and sucursal not in SUCURSALES_SIN_COBERTURA

    result = {
        "ok": True,
        "covered": covered,
        "sucursal": sucursal,
        "mensaje": None if mensaje == SIN_ERROR else mensaje,
    }
    _cache_put(key, result)
    return result


def get_shipping_cost(client: httpx.Client | None = None) -> int | None:
    """
    Tarifa de envío vigente publicada por Coto, o None si no se pudo obtener.

    Sale de getParametros2, que devuelve ~380 pares nombre/valor de config bajo
    "productoDetalle". Es un valor global: no depende de la dirección (ver el
    docstring del módulo).
    """
    key = ("shipping_cost",)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    data = _fetch_json(PARAMETROS_URL, client=client)
    if not isinstance(data, dict):
        return None

    parametros = data.get("productoDetalle")
    if not isinstance(parametros, list):
        return None

    for parametro in parametros:
        if not isinstance(parametro, dict):
            continue
        if parametro.get("nombre") != COSTO_ENVIO_PARAM:
            continue

        costo = parse_amount(parametro.get("valor"))
        if costo is not None:
            _cache_put(key, costo)
            return costo

    return None


def resolve_coto_logistics(
    lat: float | None,
    lng: float | None,
    fallback_delivery_cost: float | None = None,
    client: httpx.Client | None = None,
) -> dict:
    """
    Resuelve cobertura y costo de envío de Coto para una coordenada. Nunca lanza.

    Devuelve {"covered", "sucursal", "delivery_cost", "source", "message"}, donde
    `source` es "live" si el costo salió de Coto y "fallback" si se usó el valor
    de la tabla por zona que manda el frontend.

    Política **fail-open**: ante cualquier fallo (timeout, HTML, JSON raro) Coto
    sigue compitiendo con el costo de fallback. Sólo un "no hay cobertura"
    afirmativo lo excluye. Un endpoint de un tercero cayéndose no debería borrar
    media tienda del optimizador y devolverle al usuario un precio peor.
    """
    fallback = {
        "covered": True,
        "sucursal": None,
        "delivery_cost": fallback_delivery_cost,
        "source": "fallback",
        "message": None,
    }

    if lat is None or lng is None:
        return fallback

    try:
        coverage = check_coverage(lat, lng, client=client)
    except Exception:
        return fallback

    if not coverage["ok"]:
        return fallback

    if not coverage["covered"]:
        return {
            "covered": False,
            "sucursal": coverage["sucursal"],
            "delivery_cost": None,
            "source": "live",
            "message": coverage["mensaje"] or "Coto no realiza entregas en esta dirección.",
        }

    try:
        costo = get_shipping_cost(client=client)
    except Exception:
        costo = None

    return {
        "covered": True,
        "sucursal": coverage["sucursal"],
        "delivery_cost": costo if costo is not None else fallback_delivery_cost,
        "source": "live" if costo is not None else "fallback",
        "message": None,
    }
