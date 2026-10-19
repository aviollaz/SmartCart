# src/vtex_logistics.py
"""
Lo que comparten las consultas de logística de las tiendas VTEX (Día,
Carrefour, Vea): el request que nunca lanza, el caché de 30 minutos que sólo
guarda respuestas exitosas, y el contrato fail-open de src/coto_logistics.py.

Lo único propio de cada tienda es cómo lee sus SLAs: una función
`delivery_options(client, lat, lng)` que devuelve `[(precio en centavos,
sucursal)]` de los envíos a domicilio, `[]` si la tienda dijo que no llega, o
None si no se pudo determinar.
"""
import time
from typing import Callable

import httpx

TIMEOUT_SECONDS = 6.0
CACHE_TTL_SECONDS = 30 * 60

_INDETERMINADO = {"ok": False, "covered": None, "sucursal": None, "mensaje": None, "delivery_cost": None}

DeliveryOptions = Callable[[httpx.Client, float, float], list | None]


def request_json(client: httpx.Client, method: str, url: str, **kwargs):
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


class VtexLogistics:
    def __init__(self, name: str, headers: dict, delivery_options: DeliveryOptions):
        self.name = name
        self.headers = headers
        self.delivery_options = delivery_options
        # {clave: (timestamp, valor)}. Sólo se guardan respuestas exitosas, así
        # un timeout no fija el fallback durante todo el TTL.
        self._cache: dict = {}

    def reset_cache(self) -> None:
        """Vacía el caché en memoria. Existe para los tests."""
        self._cache.clear()

    def check_coverage(self, lat: float, lng: float, client: httpx.Client | None = None) -> dict:
        """
        Pregunta a la tienda si entrega en (lat, lng).

        Devuelve {"ok", "covered", "sucursal", "mensaje", "delivery_cost"}.
        `ok=False` significa "no se pudo determinar" y NO debe leerse como falta
        de cobertura.
        """
        key = ("coverage", round(float(lat), 4), round(float(lng), 4))
        entry = self._cache.get(key)
        if entry is not None and time.monotonic() - entry[0] <= CACHE_TTL_SECONDS:
            return entry[1]

        owned = client is None
        if owned:
            client = httpx.Client(headers=self.headers, timeout=TIMEOUT_SECONDS, follow_redirects=True)
        try:
            options = self.delivery_options(client, lat, lng)
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
                "mensaje": f"{self.name} no realiza envíos a domicilio en esta dirección.",
                "delivery_cost": None,
            }
        else:
            price, sucursal = min(options)
            result = {"ok": True, "covered": True, "sucursal": sucursal, "mensaje": None,
                      "delivery_cost": price / 100}

        self._cache[key] = (time.monotonic(), result)
        return result

    def resolve(
        self,
        lat: float | None,
        lng: float | None,
        fallback_delivery_cost: float | None = None,
        client: httpx.Client | None = None,
    ) -> dict:
        """
        Cobertura y costo de envío para una coordenada. Nunca lanza.

        Devuelve {"covered", "sucursal", "delivery_cost", "source", "message"},
        igual que resolve_coto_logistics. Fail-open: sólo un "no" afirmativo
        excluye a la tienda.
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
            coverage = self.check_coverage(lat, lng, client=client)
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
