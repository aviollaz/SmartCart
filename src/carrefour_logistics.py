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

import httpx

from src.vtex_logistics import VtexLogistics, request_json

SIMULATION_URL = "https://www.carrefour.com.ar/api/checkout/pub/orderForms/simulation"

DUMMY_SKU = "102261"
DELIVERY_CHANNEL = "delivery"
SUPERMERCADO_COURIER = re.compile(r"^(\d{4})_DOM$")
HOGAR_Y_ELECTRO = "0899"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:157.0) Gecko/20100101 Firefox/157.0",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Referer": "https://www.carrefour.com.ar/sucursales",
    "Origin": "https://www.carrefour.com.ar",
}

def _delivery_options(client: httpx.Client, lat: float, lng: float) -> list | None:
    """[(precio en centavos, sucursal)] de los envíos de supermercado, o None si falló."""
    body = {
        "items": [{"id": DUMMY_SKU, "quantity": 1, "seller": "1"}],
        "geoCoordinates": [lng, lat],
        "country": "ARG",
        "postalCode": None,
    }
    data = request_json(client, "POST", SIMULATION_URL, params={"sc": 1}, json=body)
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


_lookup = VtexLogistics("Carrefour", _HEADERS, _delivery_options)
check_coverage = _lookup.check_coverage
resolve_carrefour_logistics = _lookup.resolve
reset_cache = _lookup.reset_cache
