# src/changomas_logistics.py
"""
Consulta en línea de la logística de ChangoMás (masonline.com.ar): si entregan
en una coordenada dada y cuánto cobran por el envío. Mismo contrato y política
fail-open que src/dia_logistics.py (lo común vive en src/vtex_logistics.py).

Sobre los endpoints (relevado contra el sitio en vivo, nov 2026; públicos, sin
cookie ni login, canal de venta `sc=1`):

- `GET /api/checkout/pub/regions` **sí filtra por coordenada**, como en Día:
  Ushuaia contesta `sellers: []`, y eso es un "no llegamos" de verdad.

- Para cualquier dirección cubierta trae 5 o 6 sellers: cuatro "nacionales"
  (`masonlineprod0008`, `0014`, `0095`, `0101`) que salen en todas las
  coordenadas y contestan `withoutStock` para almacén, y la sucursal que
  atiende la zona. Por eso se simula **una sola vez con un ítem por seller**,
  como en Vea, y vale el seller que trae el SLA de envío.

- El envío a domicilio es el SLA "Envío a domicilio" y cuesta **`sla.price` +
  la franja más barata**: CABA $0 + $3.999, Córdoba $0 + $3.999, Quilmes
  $5.000 + $8.000.

El SKU 152791 (yerba Playadito 1 kg) es de stock general. Si una sucursal que
envía no lo tuviera, ChangoMás quedaría excluida de más, y no de menos.
"""
import httpx

from src.text_utils import normalize_label
from src.vtex_logistics import VtexLogistics, request_json

BASE_URL = "https://www.masonline.com.ar/api/checkout/pub"
REGIONS_URL = f"{BASE_URL}/regions"
SIMULATION_URL = f"{BASE_URL}/orderForms/simulation"
SALES_CHANNEL = 1

DUMMY_SKU = "152791"
DOMICILIO_SLA = "envio a domicilio"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:152.0) Gecko/20100101 Firefox/152.0",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Referer": "https://www.masonline.com.ar/",
    "Origin": "https://www.masonline.com.ar",
}


def _sellers(client: httpx.Client, lat: float, lng: float) -> list | None:
    params = {"country": "ARG", "geoCoordinates": f"{lng};{lat}", "sc": SALES_CHANNEL}
    data = request_json(client, "GET", REGIONS_URL, params=params)
    if not isinstance(data, list):
        return None
    return [s["id"] for region in data if isinstance(region, dict)
            for s in region.get("sellers") or [] if isinstance(s, dict) and s.get("id")]


def _delivery_options(client: httpx.Client, lat: float, lng: float) -> list | None:
    """[(precio en centavos, sucursal)] de los envíos a domicilio, `[]` si no llega, o None si falló."""
    sellers = _sellers(client, lat, lng)
    if sellers is None:
        return None
    if not sellers:
        return []

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


_lookup = VtexLogistics("ChangoMás", _HEADERS, _delivery_options)
check_coverage = _lookup.check_coverage
resolve_changomas_logistics = _lookup.resolve
reset_cache = _lookup.reset_cache
