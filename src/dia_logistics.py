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
import httpx

from src.vtex_logistics import VtexLogistics, request_json

BASE_URL = "https://diaonline.supermercadosdia.com.ar/api/checkout/pub"
REGIONS_URL = f"{BASE_URL}/regions"
SIMULATION_URL = f"{BASE_URL}/orderForms/simulation"

DUMMY_SKU = "10001664"
DELIVERY_CHANNEL = "delivery"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:152.0) Gecko/20100101 Firefox/152.0",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Referer": "https://diaonline.supermercadosdia.com.ar/",
    "Origin": "https://diaonline.supermercadosdia.com.ar",
}


def _sellers(client: httpx.Client, lat: float, lng: float) -> list | None:
    data = request_json(client, "GET", REGIONS_URL, params={"country": "ARG", "geoCoordinates": f"{lng};{lat}"})
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
    data = request_json(client, "POST", SIMULATION_URL, params={"sc": 1}, json=body)
    if not isinstance(data, dict) or not isinstance(data.get("logisticsInfo"), list):
        return None
    return [
        sla["price"]
        for info in data["logisticsInfo"] if isinstance(info, dict)
        for sla in info.get("slas") or [] if isinstance(sla, dict)
        if sla.get("deliveryChannel") == DELIVERY_CHANNEL and isinstance(sla.get("price"), (int, float))
    ]


def _delivery_options(client: httpx.Client, lat: float, lng: float) -> list | None:
    """
    [(precio más barato, sucursal)] de las sucursales que envían a domicilio.

    Una sucursal que no respondió hace indeterminada la respuesta entera: podía
    ser justo la que envía.
    """
    sellers = _sellers(client, lat, lng)
    if sellers is None:
        return None

    options = []
    for seller in sellers:
        prices = _delivery_prices(client, seller, lat, lng)
        if prices is None:
            return None
        if prices:
            options.append((min(prices), seller))
    return options


_lookup = VtexLogistics("Día", _HEADERS, _delivery_options)
check_coverage = _lookup.check_coverage
resolve_dia_logistics = _lookup.resolve
reset_cache = _lookup.reset_cache
