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

**El envío depende del PESO del carrito, no del monto** (relevado oct 2026,
issue #15). En San Isidro: 24 cafés por $527.000 pagan $4.999 igual que uno
solo, y no hay envío gratis; 3 bidones de 6,5 L (~20 kg) pagan $4.999, 6
(~39 kg) $6.899 y 10 o más (~65 kg) $11.999. Los tramos cambian por sucursal y
no se publican en ningún lado. Por eso la cobertura de abajo, que simula con el
ítem dummy, sólo da el envío MÁS BARATO — el de un carrito liviano — y
`quote_cart()` cotiza el carrito real una vez que el solver decidió qué va a
Día (ver `_requote_dia_shipping` en src/api.py).
"""
import httpx

from src.vtex_logistics import TIMEOUT_SECONDS, VtexLogistics, request_json

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


def _simulate(client: httpx.Client, seller: str, lat: float, lng: float, items: list) -> dict | None:
    """Simulación de checkout de `items` ([(sku, cantidad)]) en una sucursal."""
    body = {
        "country": "ARG",
        "items": [{"id": str(sku), "quantity": int(qty), "seller": seller} for sku, qty in items],
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
    return data


def _delivery_slas(info) -> dict:
    """{nombre del SLA: precio en centavos} de los envíos a domicilio de un ítem."""
    if not isinstance(info, dict):
        return {}
    return {
        sla.get("id") or sla.get("name"): sla["price"]
        for sla in info.get("slas") or [] if isinstance(sla, dict)
        if sla.get("deliveryChannel") == DELIVERY_CHANNEL and isinstance(sla.get("price"), (int, float))
    }


def _delivery_prices(client: httpx.Client, seller: str, lat: float, lng: float) -> list | None:
    """Precios (en centavos) de los SLAs de envío a domicilio de una sucursal."""
    data = _simulate(client, seller, lat, lng, [(DUMMY_SKU, 1)])
    if data is None:
        return None
    return [price for info in data["logisticsInfo"] for price in _delivery_slas(info).values()]


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


def quote_cart(lat: float, lng: float, seller: str, items: list,
               client: httpx.Client | None = None) -> float | None:
    """
    Envío a domicilio (en pesos) de un carrito real en la sucursal `seller`.

    `items` es [(itemId de VTEX, cantidad)]. VTEX reparte el precio de un SLA
    entre las líneas del carrito (3 alfajores: $1.666,32 + $3.332,68), así que el
    envío es la suma de ese SLA sobre todas las líneas, y se toma el SLA más
    barato que TODAS ofrecen.

    Devuelve None si no se pudo cotizar —sin respuesta, o alguna línea sin envío
    a domicilio (sin stock en esa sucursal)—: cotizar sin ella sería cotizar un
    carrito más liviano, que es justo el error que esto corrige. Nunca lanza.
    No usa caché: el carrito cambia en cada llamada.
    """
    if not items:
        return None
    owned = client is None
    if owned:
        client = httpx.Client(headers=_HEADERS, timeout=TIMEOUT_SECONDS, follow_redirects=True)
    try:
        data = _simulate(client, seller, lat, lng, items)
    except Exception:
        return None
    finally:
        if owned:
            client.close()
    if data is None:
        return None

    per_line = [_delivery_slas(info) for info in data["logisticsInfo"]]
    requested = {str(sku) for sku, _ in items}
    returned = {str(i.get("id")) for i in data.get("items") or [] if isinstance(i, dict)}
    if not per_line or not requested <= returned or any(not slas for slas in per_line):
        return None

    common = set.intersection(*(set(slas) for slas in per_line))
    if not common:
        return None
    return min(sum(slas[name] for slas in per_line) for name in common) / 100


_lookup = VtexLogistics("Día", _HEADERS, _delivery_options)
check_coverage = _lookup.check_coverage
resolve_dia_logistics = _lookup.resolve
reset_cache = _lookup.reset_cache
