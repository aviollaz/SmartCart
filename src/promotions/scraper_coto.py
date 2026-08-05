"""
Scraper de promociones bancarias de Coto.

Único de los tres que no necesita navegador: Coto expone las promociones en un
actor ATG que devuelve JSON directamente.

Sobre el endpoint (relevado contra el sitio en vivo, no contra documentación):

- Es **público**. La URL que circula incluye un `_dynSessConf=...`, pero se probó
  con ese token, con un token inventado y sin ningún token: las tres respuestas
  son idénticas byte a byte (HTTP 200, application/json, 69.153 bytes). Por eso
  acá no se hardcodea: un token capturado de una sesión ajena no aporta nada y
  además caduca, así que sólo agregaría una forma de romperse. Es el mismo
  hallazgo ya documentado para los actors de src/coto_logistics.py.

- La respuesta anida todo un nivel: `{"codigoError", "result": {...}}`, y adentro
  vienen dos listas. Se usa **sólo `promocionesDigitales`**;
  `promocionesSucursalesFisicas` son las promos de las sucursales físicas y el
  optimizador compra online.

- El nombre del banco **no está en ningún campo propio**. `banco` es un código
  numérico y encima se reutiliza: `banco=0` aparece tanto en "Comunidad Coto"
  como en una promo Visa genérica. La fuente confiable es el nombre del archivo
  del logo (`icono`: "logo_galicia.png", "logo_naranjax2.png").

- 17 de las 31 promociones digitales son "N CUOTAS SIN INTERÉS": financiación, no
  ahorro. Se descartan contándolas (ver DiscountScraper.discards).
"""
import httpx

from src.promotions.base import DiscountScraper
from src.promotions.banks import display_name, normalize_entity
from src.promotions.legal_parser import extract_cap, extract_percentage, is_installment_offer
from src.promotions.models import CANONICAL_DAYS, BankDiscount
from src.text_utils import normalize_label

PROMOCIONES_URL = "https://www.coto.com.ar/rest/model/atg/actors/cProfileActor/getPromocionesMulticanal"

# `enviroment` está así escrito del lado de Coto; no es un typo nuestro.
PROMOCIONES_PARAMS = {"enviroment": "ag", "pushSite": "CotoDigital"}

TIMEOUT_SECONDS = 15.0

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:152.0) Gecko/20100101 Firefox/152.0",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-AR,es;q=0.9",
    "Referer": "https://www.coto.com.ar/",
    "Origin": "https://www.coto.com.ar",
}


class CotoScraper(DiscountScraper):
    """Descuentos bancarios de Coto, vía el actor ATG de promociones."""

    STORE_ID = "coto_online"

    def __init__(self, client: httpx.Client | None = None) -> None:
        super().__init__()
        # Cliente inyectable, igual que en src/coto_logistics.py: es lo que
        # permite testear el transporte con httpx.MockTransport sin salir a la red.
        self._client = client

    def _fetch_raw(self):
        """
        GET que devuelve el JSON decodificado, o None si la respuesta no es
        confiable.

        Se valida el **content-type**, no sólo el status: www.coto.com.ar es un
        SPA Angular que sirve su index.html con HTTP 200 para cualquier ruta
        desconocida, así que mirar sólo el código haría parsear una página HTML
        como si fuera la respuesta del actor.
        """
        owned = self._client is None
        client = self._client or httpx.Client(
            headers=_HEADERS, timeout=TIMEOUT_SECONDS, follow_redirects=True
        )

        try:
            response = client.get(PROMOCIONES_URL, params=PROMOCIONES_PARAMS)
            if response.status_code != 200:
                return None
            if "json" not in (response.headers.get("content-type") or "").lower():
                return None
            return response.json()
        except Exception:
            return None
        finally:
            if owned:
                client.close()

    def _iter_raw_promos(self, raw):
        if not isinstance(raw, dict):
            return []
        result = raw.get("result") or {}
        return result.get("promocionesDigitales") or []

    def _to_discount(self, raw_promo) -> BankDiscount | None:
        titulo = raw_promo.get("textoDescuento") or ""
        observacion = raw_promo.get("observacion") or ""

        # Primero la financiación: "18 CUOTAS SIN INTERÉS" no baja el precio del
        # carrito, difiere el pago, y el modelo del optimizador no la representa.
        if is_installment_offer(titulo):
            self._discard("cuotas sin interes")
            return None

        porcentaje = extract_percentage(titulo)
        if porcentaje is None:
            self._discard("sin porcentaje")
            return None

        # El icono va primero porque es la fuente confiable: en la prosa aparecen
        # "Visa" y "Mastercard" en casi todas las promos, que son la marca de la
        # tarjeta y no el banco que la emite.
        entidad = normalize_entity(
            raw_promo.get("icono"),
            titulo,
            raw_promo.get("descripcion"),
        )
        if entidad is None:
            self._discard("entidad desconocida")
            return None

        dias = self._extract_dias(raw_promo)
        if not dias:
            self._discard("sin dias")
            return None

        tope, periodo = extract_cap(observacion)

        return BankDiscount(
            store=self.STORE_ID,
            entidad=entidad,
            porcentaje_descuento=porcentaje,
            dias_validos=dias,
            tope_reintegro=tope,
            tope_periodo=periodo,
            descripcion=self._build_descripcion(titulo, entidad, tope),
            promo_id=f"coto_{raw_promo.get('id')}",
            texto_legal=observacion,
            scraped_at=self._now_iso(),
        )

    @staticmethod
    def _extract_dias(raw_promo) -> tuple[str, ...]:
        """
        Días desde el array estructurado `dias`, no desde el texto.

        Coto ya los entrega como [{"descripcion": "Miercoles"}, ...], así que acá
        no hace falta el parser de texto libre que sí necesitan Día y Carrefour.
        Se normaliza igual (casefold sin acentos) porque Coto escribe "Miercoles"
        sin tilde pero nada garantiza que siga haciéndolo.
        """
        dias = []
        for entrada in raw_promo.get("dias") or []:
            etiqueta = normalize_label(entrada.get("descripcion") or "")
            if etiqueta in CANONICAL_DAYS:
                dias.append(etiqueta)
        return tuple(dias)

    @staticmethod
    def _build_descripcion(titulo: str, entidad: str, tope: int | None) -> str:
        """
        Texto legible; termina en el campo `description` que muestra la UI.

        El nombre de la entidad sólo se agrega si el título no lo dice ya: los
        títulos de Coto mezclan los dos formatos ("30% DE DESCUENTO", que no
        nombra al banco, y "COMUNIDAD COTO 15%", que sí), y concatenar a ciegas
        producía "Comunidad coto 15% con Comunidad Coto".
        """
        base = titulo.strip().capitalize()
        nombre = display_name(entidad)
        if normalize_label(nombre) not in normalize_label(base):
            base = f"{base} con {nombre}"

        if not tope:
            return base
        return f"{base} (Tope ${tope:,.0f})".replace(",", ".")


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    for descuento in CotoScraper().scrape():
        print(descuento)
