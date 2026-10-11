# src/dia_logistics.py
"""
Consulta en línea de la logística de Día: si entregan en una coordenada dada y
cuánto cobran por el envío. Mismo contrato y misma política fail-open que
src/coto_logistics.py.

Sobre los endpoints (relevado contra el sitio en vivo, oct 2026). Son los
públicos de checkout de VTEX; no hace falta cookie ni login:

- `GET /api/checkout/pub/regions?country=ARG&geoCoordinates={lng};{lat}` devuelve
  las sucursales (sellers) que atienden la coordenada. Fuera de zona (Córdoba)
  responde `sellers: []`: ese es el "no llegamos" afirmativo.

- `POST /api/checkout/pub/orderForms/simulation` con un ítem y la coordenada
  devuelve los SLAs de cada sucursal, con `price` en centavos. El sitio simula
  con un SKU "Dummy Modal" (10001664) que sale como no disponible, pero los SLAs
  vienen igual — es lo mismo que hace el propio frontend de Día.

- **Una coordenada puede tener varias sucursales con distinto servicio**: en
  Moreno la 177 sólo ofrece retiro en tienda y la 1019 envía a domicilio. Por
  eso la cobertura es "alguna sucursal tiene un SLA `delivery`", nunca la
  primera: leer sólo una excluiría a Día de una dirección adonde sí llega.

Con el ítem dummy el carrito vale $0, así que no se ve un eventual envío gratis
por monto. Si existe, se cobra de más, que es el lado seguro.
"""
import time

import httpx

BASE_URL = "https://diaonline.supermercadosdia.com.ar/api/checkout/pub"
REGIONS_URL = f"{BASE_URL}/regions"
SIMULATION_URL = f"{BASE_URL}/orderForms/simulation"

DUMMY_SKU = "10001664"
DELIVERY_CHANNEL = "delivery"

TIMEOUT_SECONDS = 6.0
CACHE_TTL_SECONDS = 30 * 60

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:152.0) Gecko/20100101 Firefox/152.0",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Referer": "https://diaonline.supermercadosdia.com.ar/",
    "Origin": "https://diaonline.supermercadosdia.com.ar",
}

_INDETERMINADO = {"ok": False, "covered": None, "sucursal": None, "mensaje": None, "delivery_cost": None}

# {clave: (timestamp, valor)}. Sólo se guardan respuestas exitosas.
_cache: dict = {}


def reset_cache() -> None:
    """Vacía el caché en memoria. Existe para los tests."""
    _cache.clear()


def _request_json(client: httpx.Client, method: str, url: str, **kwargs):
    """Request que devuelve el JSON o None, sin propagar nunca una excepción."""
    try:
        response = client.request(method, url, **kwargs)
        if response.status_code != 200:
            return None
        if "json" not in (response.headers.get("content-type") or "").lower():
            return None
        return response.json()
    except Exception:
        return None


def _sellers(client: httpx.Client, lat: float, lng: float) -> list | None:
    data = _request_json(client, "GET", REGIONS_URL, params={"country": "ARG", "geoCoordinates": f"{lng};{lat}"})
    if not isinstance(data, list):
        return None
    sellers = []
    for region in data:
        if not isinstance(region, dict) or not isinstance(region.get("sellers"), list):
            return None
        sellers += [s["id"] for s in region["sellers"] if isinstance(s, dict) and s.get("id")]
    return sellers


def _delivery_prices(client: httpx.Client, seller: str, lat: float, lng: float) -> list | None:
    """Precios (en centavos) de los SLAs de envío a domicilio de una sucursal."""
    body = {
        "country": "ARG",
        "items": [{"id": DUMMY_SKU, "quantity": 1, "seller": seller}],
        "shippingData": {
            "selectedAddresses": [{
                "country": "ARG",
                "addressType": "search",
                "addressId": "simulation",
                "geoCoordinates": [lng, lat],
            }]
        },
    }
    data = _request_json(client, "POST", SIMULATION_URL, params={"sc": 1}, json=body)
    if not isinstance(data, dict) or not isinstance(data.get("logisticsInfo"), list):
        return None
    return [
        sla["price"]
        for info in data["logisticsInfo"] if isinstance(info, dict)
        for sla in info.get("slas") or [] if isinstance(sla, dict)
        if sla.get("deliveryChannel") == DELIVERY_CHANNEL and isinstance(sla.get("price"), (int, float))
    ]


def check_coverage(lat: float, lng: float, client: httpx.Client | None = None) -> dict:
    """
    Pregunta a Día si entrega en (lat, lng).

    Devuelve {"ok", "covered", "sucursal", "mensaje", "delivery_cost"}. `ok=False`
    significa "no se pudo determinar" y NO debe leerse como falta de cobertura.
    `covered=False` sólo sale de una respuesta completa: sin sucursales, o todas
    respondieron y ninguna envía a domicilio.
    """
    key = ("coverage", round(float(lat), 4), round(float(lng), 4))
    entry = _cache.get(key)
    if entry is not None and time.monotonic() - entry[0] <= CACHE_TTL_SECONDS:
        return entry[1]

    owned = client is None
    if owned:
        client = httpx.Client(headers=_HEADERS, timeout=TIMEOUT_SECONDS, follow_redirects=True)
    try:
        sellers = _sellers(client, lat, lng)
        if sellers is None:
            return _INDETERMINADO

        best = None  # (precio en centavos, sucursal)
        for seller in sellers:
            prices = _delivery_prices(client, seller, lat, lng)
            if prices is None:
                return _INDETERMINADO
            if prices and (best is None or min(prices) < best[0]):
                best = (min(prices), seller)
    finally:
        if owned:
            client.close()

    if best is None:
        result = {
            "ok": True,
            "covered": False,
            "sucursal": None,
            "mensaje": "Día no realiza envíos a domicilio en esta dirección.",
            "delivery_cost": None,
        }
    else:
        result = {"ok": True, "covered": True, "sucursal": best[1], "mensaje": None, "delivery_cost": best[0] / 100}

    _cache[key] = (time.monotonic(), result)
    return result


def resolve_dia_logistics(
    lat: float | None,
    lng: float | None,
    fallback_delivery_cost: float | None = None,
    client: httpx.Client | None = None,
) -> dict:
    """
    Resuelve cobertura y costo de envío de Día para una coordenada. Nunca lanza.

    Devuelve {"covered", "sucursal", "delivery_cost", "source", "message"}, igual
    que resolve_coto_logistics. Fail-open: sólo un "no" afirmativo excluye a Día.
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

    return {
        "covered": coverage["covered"],
        "sucursal": coverage["sucursal"],
        "delivery_cost": coverage["delivery_cost"],
        "source": "live",
        "message": coverage["mensaje"],
    }
