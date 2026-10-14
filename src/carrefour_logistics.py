# src/carrefour_logistics.py
"""
Consulta en línea de la logística de Carrefour: si entregan en una coordenada
dada y cuánto cobran por el envío. Mismo contrato y misma política fail-open que
src/dia_logistics.py.

Sobre el endpoint (relevado contra el sitio en vivo, oct 2026). Es el público de
checkout de VTEX; no hace falta cookie ni login:

- `POST /api/checkout/pub/orderForms/simulation` con un ítem y la coordenada
  devuelve los SLAs de cada canal. Se simula con el SKU 102261 ($0,01), el mismo
  que usa la página /sucursales del propio sitio.

- Cada SLA de envío trae su courier. El de supermercado es `NNNN_DOM`, donde
  NNNN es la sucursal que atiende la zona (0026 Warnes, 0183 Pilar...). Los
  `0899_*` son de Hogar & Electro y no aplican a un carrito de súper.

- **El envío es `sla.price` + el precio de la franja horaria**, ambos en
  centavos: en Pilar 2.349 de recargo de sucursal + 3.990 de franja = $6.339,
  confirmado contra el `totalizers.Shipping` de un orderForm real. Se toma la
  franja más barata porque el usuario puede elegirla.

- No hay escalonado por monto: con un orderForm anónimo real el envío no se
  movió entre $6.500 y $140.000 de carrito. Lo que varía es la zona.

Sin ningún SLA `NNNN_DOM` (Ushuaia, campo bonaerense) es el "no llegamos".
"""
import re
import time

import httpx

SIMULATION_URL = "https://www.carrefour.com.ar/api/checkout/pub/orderForms/simulation"

DUMMY_SKU = "102261"
DELIVERY_CHANNEL = "delivery"
SUPERMERCADO_COURIER = re.compile(r"^(\d{4})_DOM$")
HOGAR_Y_ELECTRO = "0899"

TIMEOUT_SECONDS = 6.0
CACHE_TTL_SECONDS = 30 * 60

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:157.0) Gecko/20100101 Firefox/157.0",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Referer": "https://www.carrefour.com.ar/sucursales",
    "Origin": "https://www.carrefour.com.ar",
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


def _delivery_options(client: httpx.Client, lat: float, lng: float) -> list | None:
    """[(precio en centavos, sucursal)] de los envíos de supermercado, o None si falló."""
    body = {
        "items": [{"id": DUMMY_SKU, "quantity": 1, "seller": "1"}],
        "geoCoordinates": [lng, lat],
        "country": "ARG",
        "postalCode": None,
    }
    data = _request_json(client, "POST", SIMULATION_URL, params={"sc": 1}, json=body)
    if not isinstance(data, dict) or not isinstance(data.get("logisticsInfo"), list):
        return None

    options = []
    for info in data["logisticsInfo"]:
        for sla in (info.get("slas") or []) if isinstance(info, dict) else []:
            if not isinstance(sla, dict) or sla.get("deliveryChannel") != DELIVERY_CHANNEL:
                continue
            if not isinstance(sla.get("price"), (int, float)):
                continue
            for delivery_id in sla.get("deliveryIds") or []:
                if not isinstance(delivery_id, dict):
                    continue
                match = SUPERMERCADO_COURIER.match(str(delivery_id.get("courierId") or ""))
                if not match or match.group(1) == HOGAR_Y_ELECTRO:
                    continue
                windows = [
                    w["price"] for w in sla.get("availableDeliveryWindows") or []
                    if isinstance(w, dict) and isinstance(w.get("price"), (int, float))
                ]
                options.append((sla["price"] + min(windows, default=0), match.group(1)))
    return options


def check_coverage(lat: float, lng: float, client: httpx.Client | None = None) -> dict:
    """
    Pregunta a Carrefour si entrega en (lat, lng).

    Devuelve {"ok", "covered", "sucursal", "mensaje", "delivery_cost"}. `ok=False`
    significa "no se pudo determinar" y NO debe leerse como falta de cobertura.
    """
    key = ("coverage", round(float(lat), 4), round(float(lng), 4))
    entry = _cache.get(key)
    if entry is not None and time.monotonic() - entry[0] <= CACHE_TTL_SECONDS:
        return entry[1]

    owned = client is None
    if owned:
        client = httpx.Client(headers=_HEADERS, timeout=TIMEOUT_SECONDS, follow_redirects=True)
    try:
        options = _delivery_options(client, lat, lng)
    finally:
        if owned:
            client.close()

    if options is None:
        return _INDETERMINADO

    if not options:
        result = {
            "ok": True,
            "covered": False,
            "sucursal": None,
            "mensaje": "Carrefour no realiza envíos a domicilio en esta dirección.",
            "delivery_cost": None,
        }
    else:
        price, sucursal = min(options)
        result = {"ok": True, "covered": True, "sucursal": sucursal, "mensaje": None, "delivery_cost": price / 100}

    _cache[key] = (time.monotonic(), result)
    return result


def resolve_carrefour_logistics(
    lat: float | None,
    lng: float | None,
    fallback_delivery_cost: float | None = None,
    client: httpx.Client | None = None,
) -> dict:
    """
    Resuelve cobertura y costo de envío de Carrefour para una coordenada. Nunca lanza.

    Devuelve {"covered", "sucursal", "delivery_cost", "source", "message"}, igual
    que resolve_dia_logistics. Fail-open: sólo un "no" afirmativo excluye a Carrefour.
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
