"""
Scraper de promociones bancarias de Vea.

Igual que Coto, no necesita navegador: la grilla de /descuentos-del-dia sale de
una entidad de Master Data VTEX pública (sin cookie ni login):

    GET /api/dataentities/JN/documents/bankDiscount?_fields=value,id&an=jumboargentina

`value` es un **string con JSON adentro**: ~200 promos de las tres cadenas de
Cencosud (Jumbo, Disco, Vea), con vencidas incluidas. Lo relevado (oct 2026):

- `websites` dice en qué sitios aplica; se usa la que lista `veaargentina`.
- `dateStart`/`dateEnd` son epoch en segundos.
- `days` va de "1" (lunes) a "6", y **"6" es sábado y domingo juntos**: Comafi
  ("viernes, sábados y domingos") viene como ["5","6"] y Macro ("jueves,
  viernes, sábado y domingo") como ["4","5","6"]. No aparece ningún "0" ni "7".
- `discount` es el número grande de la tarjeta, y como en Carrefour a veces son
  **cuotas**: "6.00" con `discountText` "cuotas sin interés". Un descuento
  trae `discountText` vacío o que empieza con "%".
- El banco sale de `banks[].name`, nunca del legal: la promo de jubilados
  ("Medios de Pago") menciona un "15% con Cencopay" que no es su beneficio.

Se descartan, contándolas, las que el modelo no puede representar: sólo en
locales, en productos seleccionados, o con monto mínimo (MODO: "compras iguales
o superiores a $100.000"). Aplicar cualquiera de ellas a todo el carrito
cotizaría de menos.
"""
import json
import re
import time

import httpx

from src.promotions.base import DiscountScraper
from src.promotions.banks import display_name, normalize_entity
from src.promotions.legal_parser import extract_cap
from src.promotions.models import BankDiscount
from src.text_utils import normalize_label

PROMOCIONES_URL = "https://www.vea.com.ar/api/dataentities/JN/documents/bankDiscount"
PROMOCIONES_PARAMS = {"_fields": "value,id", "an": "jumboargentina"}
WEBSITE = "veaargentina"

TIMEOUT_SECONDS = 15.0

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:152.0) Gecko/20100101 Firefox/152.0",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.vea.com.ar/descuentos-del-dia",
}

_DIAS = {
    "1": ("lunes",), "2": ("martes",), "3": ("miercoles",), "4": ("jueves",),
    "5": ("viernes",), "6": ("sabado", "domingo"),
}

_ONLINE = ("online", "web", "vea.com.ar")
_MINIMO_RE = re.compile(r"(superior|mayor)es? a \$|minimo de compra|a partir de \$")


class VeaScraper(DiscountScraper):
    """Descuentos bancarios de Vea, vía la entidad de Master Data de Cencosud."""

    STORE_ID = "vea_online"

    def __init__(self, client: httpx.Client | None = None, now: float | None = None) -> None:
        super().__init__()
        # Cliente y reloj inyectables, para testear sin red y con fechas fijas.
        self._client = client
        self._now = now

    def _fetch_raw(self):
        owned = self._client is None
        client = self._client or httpx.Client(headers=_HEADERS, timeout=TIMEOUT_SECONDS)
        try:
            response = client.get(PROMOCIONES_URL, params=PROMOCIONES_PARAMS)
            if response.status_code != 200:
                return None
            if "json" not in (response.headers.get("content-type") or "").lower():
                return None
            return json.loads(response.json()["value"])
        except Exception:
            return None
        finally:
            if owned:
                client.close()

    def _iter_raw_promos(self, raw):
        return raw if isinstance(raw, list) else []

    def _to_discount(self, raw_promo) -> BankDiscount | None:
        if WEBSITE not in (raw_promo.get("websites") or []):
            self._discard("otro sitio de cencosud")
            return None

        ahora = self._now if self._now is not None else time.time()
        if not int(raw_promo.get("dateStart") or 0) <= ahora <= int(raw_promo.get("dateEnd") or 0):
            self._discard("fuera de vigencia")
            return None

        if raw_promo.get("stores"):
            self._discard("sucursales puntuales")
            return None

        rotulo = normalize_label(raw_promo.get("discountText") or "")
        if "cuota" in rotulo and not rotulo.startswith("%"):
            self._discard("cuotas sin interes")
            return None

        info = raw_promo.get("info") or ""
        legal = raw_promo.get("legals") or ""
        texto = normalize_label(f"{raw_promo.get('installmentsText') or ''} {info} {legal}")

        if "presencial" in texto and not any(marca in texto for marca in _ONLINE):
            self._discard("solo local fisico")
            return None
        if "seleccionad" in texto:
            self._discard("productos seleccionados")
            return None
        if _MINIMO_RE.search(texto):
            self._discard("monto minimo")
            return None

        entidad = normalize_entity(*(b.get("name") for b in raw_promo.get("banks") or []))
        if entidad is None:
            self._discard("entidad desconocida")
            return None

        porcentaje = float(raw_promo.get("discount") or 0)
        dias = tuple(d for codigo in raw_promo.get("days") or () for d in _DIAS.get(codigo, ()))
        if not dias:
            self._discard("sin dias")
            return None

        tope, periodo = extract_cap(info)
        if tope is None:
            tope, periodo = extract_cap(legal)

        return BankDiscount(
            store=self.STORE_ID,
            entidad=entidad,
            porcentaje_descuento=porcentaje,
            dias_validos=dias,
            tope_reintegro=tope,
            tope_periodo=periodo,
            descripcion=self._build_descripcion(porcentaje, entidad, tope),
            promo_id=f"vea_{raw_promo.get('priority')}_{entidad}_{porcentaje:g}",
            texto_legal=legal.strip() or info.strip(),
            scraped_at=self._now_iso(),
        )

    @staticmethod
    def _build_descripcion(porcentaje: float, entidad: str, tope: int | None) -> str:
        base = f"{porcentaje:g}% de descuento con {display_name(entidad)}"
        if not tope:
            return base
        return f"{base} (Tope ${tope:,.0f})".replace(",", ".")


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    for descuento in VeaScraper().scrape():
        print(descuento)
