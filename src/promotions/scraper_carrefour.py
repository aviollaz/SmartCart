"""
Scraper de promociones bancarias de Carrefour.

La página (/promociones-bancarias) la sirve la app VTEX
`valtech-carrefourar-bank-promotions`. Es la más cómoda de las tres: el texto
legal ya está en el DOM, sólo colapsado, así que **no hay que clickear nada** —
al contrario de Día, donde cada legal vive en un modal que hay que abrir y cerrar.

Dos trampas que el relevamiento dejó a la vista:

1. **El número grande de la tarjeta no siempre es un porcentaje.** El bloque
   `ColLeftPercentage` dice "20" en "20% de descuento" pero también dice "6" en
   "Hasta 6 Cuotas sin interés", y el símbolo "%" es un span aparte que se
   renderiza igual en los dos casos. Leerlo sin mirar el rótulo de al lado
   (`ColLeftPercentageText`: "De descuento" / "sin interés") convierte un plan de
   6 cuotas en un 6% de descuento que no existe. Por eso la financiación se
   descarta ANTES de leer el número.

2. **La mitad de las promos son exclusivas de los locales físicos.** Cada tarjeta
   declara sus formatos con iconos, y el de carrefour.com.ar es el que lleva la
   clase `logoOnline`. De las 32 tarjetas, 20 aplican online. Sin ese filtro
   entrarían promos de Carrefour Maxi que no se pueden usar comprando por web.
"""
import logging

from src.promotions.banks import display_name, normalize_entity
from src.promotions.legal_parser import extract_cap, extract_days, extract_percentage
from src.promotions.models import BankDiscount
from src.promotions.playwright_base import PlaywrightScraper
from src.text_utils import normalize_label

logger = logging.getLogger(__name__)

NS = "valtech-carrefourar-bank-promotions-0-x-"

# Rótulos que delatan financiación en vez de descuento.
_MARCADORES_CUOTAS = ("sin interes", "cuota")


class CarrefourScraper(PlaywrightScraper):
    """Descuentos bancarios de Carrefour."""

    STORE_ID = "carrefour_online"
    URL = "https://www.carrefour.com.ar/promociones-bancarias"

    CARD_SELECTOR = f".{NS}cardBox"
    READY_SELECTOR = CARD_SELECTOR
    DATE_SELECTOR = f"{NS}dateText"
    PERCENT_SELECTOR = f"{NS}ColLeftPercentage"
    PERCENT_LABEL_SELECTOR = f"{NS}ColLeftPercentageText"
    TITLE_SELECTOR = f"{NS}ColRightTittle"
    TEXT_SELECTOR = f"{NS}ColRightText"
    LEGAL_SELECTOR = f"{NS}legalContent"
    ONLINE_LOGO_SELECTOR = f"{NS}logoOnline"
    CARD_IMAGE_SELECTOR = f"{NS}Image"

    def _extract_from_page(self, page):
        """
        Baja las 32 tarjetas de una sola evaluación en el navegador.

        Se hace en un único `eval_on_selector_all` en vez de iterar con handles
        porque no hay interacción de por medio: es lectura pura, y así se cruza
        el puente Python<->navegador una vez en lugar de 32*7 veces.
        """
        return page.eval_on_selector_all(
            self.CARD_SELECTOR,
            """(els, s) => els.map((e, indice) => {
                const texto = clase => {
                    const nodo = e.querySelector('.' + clase);
                    return nodo ? nodo.innerText.trim() : '';
                };
                return {
                    indice,
                    fecha: texto(s.fecha),
                    porcentaje: texto(s.porcentaje),
                    rotulo: texto(s.rotulo),
                    titulo: texto(s.titulo),
                    texto: texto(s.texto),
                    legal: texto(s.legal),
                    online: !!e.querySelector('.' + s.online),
                    imagenes: Array.from(e.querySelectorAll('.' + s.imagen))
                        .map(i => i.getAttribute('alt') || i.getAttribute('src') || ''),
                };
            })""",
            {
                "fecha": self.DATE_SELECTOR,
                "porcentaje": self.PERCENT_SELECTOR,
                "rotulo": self.PERCENT_LABEL_SELECTOR,
                "titulo": self.TITLE_SELECTOR,
                "texto": self.TEXT_SELECTOR,
                "legal": self.LEGAL_SELECTOR,
                "online": self.ONLINE_LOGO_SELECTOR,
                "imagen": self.CARD_IMAGE_SELECTOR,
            },
        )

    def _iter_raw_promos(self, raw):
        return raw or []

    def _to_discount(self, raw_promo) -> BankDiscount | None:
        if not raw_promo.get("online"):
            self._discard("solo local fisico")
            return None

        titulo = raw_promo.get("titulo") or ""
        rotulo = raw_promo.get("rotulo") or ""

        # Antes que nada: si es financiación, el número de al lado son cuotas.
        if self._es_financiacion(rotulo, titulo):
            self._discard("cuotas sin interes")
            return None

        porcentaje = self._extract_percentage(raw_promo, titulo)
        if porcentaje is None:
            self._discard("sin porcentaje de descuento")
            return None

        entidad = normalize_entity(
            " ".join(raw_promo.get("imagenes") or ()),
            titulo,
            raw_promo.get("legal"),
        )
        if entidad is None:
            self._discard("entidad desconocida")
            return None

        # El encabezado ("Todos los Jueves de Agosto", "Lunes a Viernes de
        # Agosto") es la fuente más limpia de días; el legal es el respaldo.
        dias = extract_days(raw_promo.get("fecha")) or extract_days(raw_promo.get("legal"))
        if not dias:
            # Quedan afuera las de "Programando la entrega de tu pedido..." y
            # "Válido en el mes de Agosto", que no nombran ningún día. Asumir
            # "todos" las haría aplicar un martes sin que nadie lo haya dicho, y
            # el filtro por día del loader es justamente lo que evita prometer
            # un ahorro el día equivocado.
            self._discard("sin dias")
            return None

        # El tope suele estar en el texto corto de la tarjeta ("Tope de devolución
        # $10.000"), que es mucho menos ruidoso que el legal; si no, el legal.
        tope, periodo = extract_cap(raw_promo.get("texto"))
        if tope is None:
            tope, periodo = extract_cap(raw_promo.get("legal"))

        return BankDiscount(
            store=self.STORE_ID,
            entidad=entidad,
            porcentaje_descuento=porcentaje,
            dias_validos=dias,
            tope_reintegro=tope,
            tope_periodo=periodo,
            descripcion=self._build_descripcion(porcentaje, entidad, tope),
            promo_id=f"carrefour_{raw_promo.get('indice')}_{entidad}",
            texto_legal=(raw_promo.get("legal") or "").strip(),
            scraped_at=self._now_iso(),
        )

    @staticmethod
    def _es_financiacion(rotulo: str, titulo: str) -> bool:
        texto = normalize_label(f"{rotulo} {titulo}")
        return any(marcador in texto for marcador in _MARCADORES_CUOTAS)

    def _extract_percentage(self, raw_promo, titulo: str) -> float | None:
        """
        El número del bloque grande, con el título como respaldo.

        Ese bloque es el dato más confiable de la tarjeta —está estructurado y no
        hay que adivinarlo— pero a veces trae otra cosa: se observó una tarjeta
        cuyo rótulo era "Tope de devolución $...". Cuando no es un porcentaje
        plausible se cae al título, que dice "20% de descuento en un pago con...".
        """
        crudo = (raw_promo.get("porcentaje") or "").strip().replace(",", ".")
        try:
            numero = float(crudo)
            if 0 < numero <= 100:
                return numero
        except ValueError:
            pass

        return extract_percentage(titulo)

    @staticmethod
    def _build_descripcion(porcentaje: float, entidad: str, tope: int | None) -> str:
        base = f"{porcentaje:.0f}% de ahorro con {display_name(entidad)}"
        if not tope:
            return base
        return f"{base} (Tope ${tope:,.0f})".replace(",", ".")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    for descuento in CarrefourScraper().scrape():
        print(descuento.descripcion, descuento.dias_validos)
