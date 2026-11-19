"""
Scraper de promociones bancarias de ChangoMás.

Como Vea, no necesita navegador: la página /promociones-bancarias (la app
`valtech.gdn-banks-promotions`) lee dos colecciones públicas del servicio de
contenido de GDN, sin cookie ni login:

    GET /_v/private/gdn-services/content/banks-promotions?_fields=...
    GET /_v/private/gdn-services/content/financing-banks?_fields=id,name

Lo relevado (nov 2026), sobre 46 registros:

- **Casi todo es presencial.** `ecommerce` / `express_ecommerce_all` dicen si
  aplica online; en noviembre no quedaba ninguna online vigente. Por eso
  `MIN_EXPECTED_DISCOUNTS = 0`: un bloque vacío es lo normal, no una falla.
- Los días son siete booleanos (`monday`…`sunday`); la vigencia,
  `active_from`/`active_to` en ISO, y además un flag `active`.
- El banco sale de `idBank` contra `financing-banks`. Los registros de MasClub
  (el club de socios) traen `isMasClub` y su "banco" es "MasClub".
- El tope está en `sub_title` ("Tope: $15.000 semanal"); `legal` es el fallback.
- `discount_percentage` viene en null en las promos de cuotas.

Se descartan, contándolas, las que el modelo no puede representar: sólo en
locales, con monto mínimo (MODO: "Mínimo de compra: $75.000"), o con una lista
de rubros excluidos (la de MasClub del 27-oct sacaba aceites, harinas, leches y
bebidas). Aplicarlas a todo el carrito cotizaría de menos.
"""
import re
import time
from datetime import datetime

import httpx

from src.promotions.base import DiscountScraper
from src.promotions.banks import display_name, normalize_entity
from src.promotions.legal_parser import extract_cap
from src.promotions.models import CANONICAL_DAYS, BankDiscount
from src.text_utils import normalize_label

CONTENT_URL = "https://www.masonline.com.ar/_v/private/gdn-services/content"
PROMOS_FIELDS = ("id,sub_title,discount_percentage,active,active_from,active_to,ecommerce,"
                 "express_ecommerce_all,isMasClub,idBank,legal,"
                 "monday,tuesday,wednesday,thursday,friday,saturday,sunday")

TIMEOUT_SECONDS = 15.0

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:152.0) Gecko/20100101 Firefox/152.0",
    "Accept": "application/json",
    "Referer": "https://www.masonline.com.ar/promociones-bancarias",
}

_DIAS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
# "minmo" no es un error de tipeo nuestro: así viene en una de MODO.
_MINIMO_RE = re.compile(r"(superior|mayor)es? a \$|minimo de compra|minmo de compra|a partir de \$")


def _epoch(iso: str | None) -> float:
    return datetime.fromisoformat(iso).timestamp() if iso else 0.0


class ChangomasScraper(DiscountScraper):
    """Descuentos bancarios de ChangoMás, vía el servicio de contenido de GDN."""

    STORE_ID = "changomas_online"
    MIN_EXPECTED_DISCOUNTS = 0

    def __init__(self, client: httpx.Client | None = None, now: float | None = None,
                 banks: dict | None = None) -> None:
        super().__init__()
        # Cliente, reloj y bancos inyectables, para testear sin red y con fechas fijas.
        self._client = client
        self._now = now
        self._banks = banks or {}

    def _fetch_raw(self):
        owned = self._client is None
        client = self._client or httpx.Client(headers=_HEADERS, timeout=TIMEOUT_SECONDS)
        try:
            bancos = client.get(f"{CONTENT_URL}/financing-banks", params={"_fields": "id,name", "_to": 999})
            promos = client.get(f"{CONTENT_URL}/banks-promotions", params={"_fields": PROMOS_FIELDS, "_to": 999})
            if bancos.status_code != 200 or promos.status_code != 200:
                return None
            self._banks = {b["id"]: b["name"] for b in bancos.json()}
            return promos.json()
        except Exception:
            return None
        finally:
            if owned:
                client.close()

    def _iter_raw_promos(self, raw):
        return raw if isinstance(raw, list) else []

    def _to_discount(self, raw_promo) -> BankDiscount | None:
        if not raw_promo.get("active"):
            self._discard("inactiva")
            return None

        ahora = self._now if self._now is not None else time.time()
        if not _epoch(raw_promo.get("active_from")) <= ahora < _epoch(raw_promo.get("active_to")):
            self._discard("fuera de vigencia")
            return None

        if not (raw_promo.get("ecommerce") or raw_promo.get("express_ecommerce_all")):
            self._discard("solo local fisico")
            return None

        porcentaje = raw_promo.get("discount_percentage")
        if not porcentaje:
            self._discard("sin porcentaje")
            return None

        sub_title = raw_promo.get("sub_title") or ""
        legal = raw_promo.get("legal") or ""
        texto = normalize_label(f"{sub_title} {legal}")
        if _MINIMO_RE.search(texto):
            self._discard("monto minimo")
            return None
        if "no incluye" in texto:
            self._discard("productos excluidos")
            return None

        if raw_promo.get("isMasClub"):
            entidad = "masclub"
        else:
            entidad = normalize_entity(self._banks.get(raw_promo.get("idBank")))
        if entidad is None:
            self._discard("entidad desconocida")
            return None

        dias = tuple(dia for dia, campo in zip(CANONICAL_DAYS, _DIAS) if raw_promo.get(campo))
        if not dias:
            self._discard("sin dias")
            return None

        tope, periodo = extract_cap(sub_title)
        if tope is None:
            tope, periodo = extract_cap(legal)

        porcentaje = float(porcentaje)
        return BankDiscount(
            store=self.STORE_ID,
            entidad=entidad,
            porcentaje_descuento=porcentaje,
            dias_validos=dias,
            tope_reintegro=tope,
            tope_periodo=periodo,
            descripcion=self._build_descripcion(porcentaje, entidad, tope),
            promo_id=f"changomas_{raw_promo.get('id')}",
            texto_legal=legal.strip() or sub_title.strip(),
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
    for descuento in ChangomasScraper().scrape():
        print(descuento)
