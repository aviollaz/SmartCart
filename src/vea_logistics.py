# src/vea_logistics.py
"""
Consulta en línea de la logística de Vea: si entregan en una coordenada dada y
cuánto cobran por el envío. Mismo contrato y política fail-open que
src/dia_logistics.py (lo común vive en src/vtex_logistics.py).

Sobre los endpoints (relevado contra el sitio en vivo, oct 2026; públicos, sin
cookie ni login, canal de venta `sc=34`):

- `GET /api/checkout/pub/regions` **no filtra por coordenada**: devuelve las ~88
  sucursales del país para Pilar, para Córdoba y para Ushuaia. No sirve como "no
  llegamos", al revés que en Día.

- Por eso se simula **una sola vez con un ítem por sucursal**: la respuesta trae
  un `logisticsInfo` por ítem y en ~2 s se sabe cuál envía. Simular sucursal por
  sucursal tardaba ~20 s por dirección.

- Todos los SLAs vienen con `deliveryChannel: "delivery"`, incluso "Retiro en
  Tienda" y "Retira en Auto". Lo que distingue el envío a domicilio es el nombre
  del SLA, "Envío a Domicilio". El courier no sirve: su sufijo cambia según la
  sucursal (`sm700ed` en Palermo, `sm697ev` en Pacheco).

- **El envío es `sla.price` + la franja horaria más barata**, igual que en
  Carrefour: `price` viene en 0 y la franja en 349900 centavos ($3.499) en CABA,
  San Isidro y Córdoba. Pilar, Quilmes y Morón no tienen envío a domicilio.

El SKU 253158 es el que simula el propio sitio. Siete sucursales contestan
`cannotBeDelivered` para él desde cualquier coordenada (incluso CABA), así que
no dependen de la dirección; si alguna empezara a enviar sin vender ese SKU,
Vea quedaría excluida de más, y no de menos.
"""
import httpx

from src.text_utils import normalize_label
from src.vtex_logistics import VtexLogistics, request_json

BASE_URL = "https://www.vea.com.ar/api/checkout/pub"
REGIONS_URL = f"{BASE_URL}/regions"
SIMULATION_URL = f"{BASE_URL}/orderForms/simulation"
SALES_CHANNEL = 34

DUMMY_SKU = "253158"
DOMICILIO_SLA = "envio a domicilio"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:152.0) Gecko/20100101 Firefox/152.0",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Referer": "https://www.vea.com.ar/",
    "Origin": "https://www.vea.com.ar",
}


def _sellers(client: httpx.Client, lat: float, lng: float) -> list | None:
    params = {"country": "ARG", "geoCoordinates": f"{lng};{lat}", "sc": SALES_CHANNEL}
    data = request_json(client, "GET", REGIONS_URL, params=params)
    if not isinstance(data, list):
        return None
    return [s["id"] for region in data if isinstance(region, dict)
            for s in region.get("sellers") or [] if isinstance(s, dict) and s.get("id")]


def _delivery_options(client: httpx.Client, lat: float, lng: float) -> list | None:
    """[(precio en centavos, sucursal)] de los envíos a domicilio, o None si falló."""
    sellers = _sellers(client, lat, lng)
    if not sellers:
        # Sin sucursales no hay nada que simular, pero como `regions` no mira la
        # coordenada, una lista vacía no es un "no llegamos": es una respuesta rara.
        return None

    body = {
        "items": [{"id": DUMMY_SKU, "quantity": 1, "seller": s} for s in sellers],
        "geoCoordinates": [lng, lat],
        "country": "ARG",
    }
    data = request_json(client, "POST", SIMULATION_URL, params={"sc": SALES_CHANNEL}, json=body)
    if not isinstance(data, dict) or not isinstance(data.get("logisticsInfo"), list):
        return None

    options = []
    for info in data["logisticsInfo"]:
        if not isinstance(info, dict) or not isinstance(info.get("itemIndex"), int):
            continue
        if not 0 <= info["itemIndex"] < len(sellers):
            continue
        for sla in info.get("slas") or []:
            if not isinstance(sla, dict) or not isinstance(sla.get("price"), (int, float)):
                continue
            if normalize_label(str(sla.get("name") or sla.get("id") or "")) != DOMICILIO_SLA:
                continue
            windows = [
                w["price"] for w in sla.get("availableDeliveryWindows") or []
                if isinstance(w, dict) and isinstance(w.get("price"), (int, float))
            ]
            options.append((sla["price"] + min(windows, default=0), sellers[info["itemIndex"]]))
    return options


_lookup = VtexLogistics("Vea", _HEADERS, _delivery_options)
check_coverage = _lookup.check_coverage
resolve_vea_logistics = _lookup.resolve
reset_cache = _lookup.reset_cache
