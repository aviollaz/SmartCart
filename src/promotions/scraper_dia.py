"""
Scraper de promociones bancarias de Día.

La página (/medios-de-pago-y-promociones) la sirve una app VTEX propia,
`diaio-custom-bank-promotions`, que renderiza todo en el cliente.

Tres decisiones que salieron del relevamiento contra el sitio en vivo:

1. **Los días se leen de los tabs, no del texto legal.** La grilla tiene un filtro
   por día que efectivamente filtra las tarjetas, así que recorrer los siete tabs
   y anotar qué tarjetas aparecen en cada uno da los días como dato estructurado.
   Sacarlos del legal sería adivinar sobre prosa en mayúsculas donde conviven
   "TODOS LOS LUNES" con "DENTRO DE LOS 15 DÍAS HÁBILES".

2. **Se filtra por canal ONLINE.** Las 23 tarjetas incluyen promos exclusivas de
   los locales físicos; el optimizador compra online. El radio `#online` deja 14.

3. **"Ver Legales" abre un modal de verdad** (role="dialog"), no un acordeón: se
   monta dentro de la tarjeta y captura los eventos de puntero, así que si no se
   lo cierra el click sobre la tarjeta siguiente muere por timeout. De ahí que el
   ciclo sea abrir -> leer -> cerrar.

La identidad de una tarjeta es el `src` de su imagen: es lo único estable entre
una pasada de tabs y la siguiente. Las clases del contenedor traen el nombre del
banco ("card_detail Modo") pero se repiten entre promos distintas del mismo banco
—hay cuatro tarjetas "Naranja,Naranja"— así que no sirven como clave.
"""
import logging

from src.promotions.banks import display_name, normalize_entity
from src.promotions.legal_parser import extract_cap, extract_days, extract_percentage
from src.promotions.models import CANONICAL_DAYS, BankDiscount
from src.promotions.playwright_base import PlaywrightScraper
from src.text_utils import normalize_label

logger = logging.getLogger(__name__)

NS = "diaio-custom-bank-promotions-0-x-"


class DiaScraper(PlaywrightScraper):
    """Descuentos bancarios de Día."""

    STORE_ID = "dia_online"
    URL = "https://diaonline.supermercadosdia.com.ar/medios-de-pago-y-promociones"

    # Selectores como constantes: cuando VTEX renombre una clase, el arreglo es
    # una línea acá y no una búsqueda por todo el flujo.
    CARD_SELECTOR = f".{NS}card_detail"
    READY_SELECTOR = CARD_SELECTOR
    DAY_TAB_SELECTOR = f"button.{NS}days_filters__tab"
    LEGAL_BUTTON_SELECTOR = f"button.{NS}card_detail__terms"
    LEGAL_TEXT_SELECTOR = f".{NS}card_detail__modal_text"
    MODAL_CLOSE_SELECTOR = f"button.{NS}card_detail__modal_close"
    ONLINE_RADIO_SELECTOR = "input#online"

    # Etiquetas tal cual las escribe Día en los tabs, en orden canónico.
    DAY_TABS = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")
    ALL_DAYS_TAB = "Todos"

    MODAL_TIMEOUT_MS = 10000
    FILTER_SETTLE_MS = 1600

    def _extract_from_page(self, page):
        page.check(self.ONLINE_RADIO_SELECTOR)
        page.wait_for_timeout(self.FILTER_SETTLE_MS)

        dias_por_tarjeta = self._collect_days(page)
        return self._collect_cards(page, dias_por_tarjeta)

    def _collect_days(self, page) -> dict[str, list[str]]:
        """
        Recorre los tabs de día y anota en cuáles aparece cada tarjeta.

        Devuelve {src de la imagen: [días canónicos]}.
        """
        dias_por_tarjeta: dict[str, list[str]] = {}

        for indice, etiqueta in enumerate(self.DAY_TABS):
            try:
                page.click(f"{self.DAY_TAB_SELECTOR}:text-is('{etiqueta}')")
                page.wait_for_timeout(self.FILTER_SETTLE_MS)
            except Exception as exc:
                logger.warning("%s: no se pudo filtrar por %s: %s", self.STORE_ID, etiqueta, exc)
                continue

            visibles = page.eval_on_selector_all(
                self.CARD_SELECTOR, "els => els.map(e => (e.querySelector('img') || {}).src || '')"
            )
            for src in visibles:
                if src:
                    dias_por_tarjeta.setdefault(src, []).append(CANONICAL_DAYS[indice])

        # Se vuelve a "Todos" para que el recorrido de legales vea las 14 tarjetas
        # y no sólo las del último día consultado.
        page.click(f"{self.DAY_TAB_SELECTOR}:text-is('{self.ALL_DAYS_TAB}')")
        page.wait_for_timeout(self.FILTER_SETTLE_MS)
        return dias_por_tarjeta

    def _collect_cards(self, page, dias_por_tarjeta: dict[str, list[str]]) -> list[dict]:
        """Abre el legal de cada tarjeta y devuelve dicts planos."""
        total = len(page.query_selector_all(self.CARD_SELECTOR))
        tarjetas = []

        for indice in range(total):
            # Se vuelve a consultar el nodo en cada vuelta: abrir y cerrar el modal
            # remonta parte del árbol y un handle guardado antes queda obsoleto.
            card = page.query_selector_all(self.CARD_SELECTOR)[indice]
            src = card.evaluate("e => (e.querySelector('img') || {}).src || ''")
            alt = card.evaluate("e => (e.querySelector('img') || {}).alt || ''")

            tarjetas.append({
                "src": src,
                "alt": alt,
                "dias": dias_por_tarjeta.get(src, []),
                "legal": self._read_legal(page, card, indice),
                "indice": indice,
            })

        return tarjetas

    def _read_legal(self, page, card, indice: int) -> str:
        """
        Abre el modal, lee el texto y lo cierra.

        Es fail-open por tarjeta: si una no abre, se pierde esa promo y no la
        corrida entera. Cerrar es obligatorio — el modal tapa la grilla y dejarlo
        abierto rompe todas las tarjetas siguientes, no sólo ésta.
        """
        boton = card.query_selector(self.LEGAL_BUTTON_SELECTOR)
        if boton is None:
            return ""

        try:
            boton.click()
            page.wait_for_selector(self.LEGAL_TEXT_SELECTOR, timeout=self.MODAL_TIMEOUT_MS)
            texto = page.inner_text(self.LEGAL_TEXT_SELECTOR).strip()
        except Exception as exc:
            logger.warning("%s: no se pudo leer el legal de la tarjeta %d: %s",
                           self.STORE_ID, indice, exc)
            texto = ""

        try:
            page.click(self.MODAL_CLOSE_SELECTOR, timeout=self.MODAL_TIMEOUT_MS)
            page.wait_for_timeout(400)
        except Exception as exc:
            logger.warning("%s: quedó abierto el modal de la tarjeta %d: %s",
                           self.STORE_ID, indice, exc)

        return texto

    def _iter_raw_promos(self, raw):
        return raw or []

    def _to_discount(self, raw_promo) -> BankDiscount | None:
        legal = raw_promo.get("legal") or ""
        if not legal:
            self._discard("sin texto legal")
            return None

        # `strict=True` porque acá la entrada es el legal completo, donde el
        # descuento convive con las tasas de financiación ("CFT 0% TEA 0%").
        porcentaje = extract_percentage(legal, strict=True)
        if porcentaje is None:
            # Cubre dos casos: los planes de cuotas, y los legales que sólo
            # expresan el beneficio con un ejemplo ("EN UN CONSUMO DE $60.000
            # RECIBIRÁ UN REINTEGRO DE $15.000"). Deducir el 25% de esa división
            # sería inventar un número que la tienda no publicó.
            self._discard("sin porcentaje de descuento")
            return None

        # El alt de la imagen nombra la marca ("Promoción bancaria: Banco
        # Columbia") y es mucho más seguro que el legal, donde aparecen el
        # domicilio del anunciante y frases como "DE ALCANCE NACIONAL".
        entidad = normalize_entity(self._clean_alt(raw_promo.get("alt")), legal)
        if entidad is None:
            self._discard("entidad desconocida")
            return None

        dias = tuple(raw_promo.get("dias") or ())
        if not dias:
            # Fallback al texto sólo si los tabs no dijeron nada.
            dias = extract_days(legal)
        if not dias:
            self._discard("sin dias")
            return None

        tope, periodo = extract_cap(legal)

        return BankDiscount(
            store=self.STORE_ID,
            entidad=entidad,
            porcentaje_descuento=porcentaje,
            dias_validos=dias,
            tope_reintegro=tope,
            tope_periodo=periodo,
            descripcion=self._build_descripcion(porcentaje, entidad, tope),
            promo_id=f"dia_{raw_promo.get('indice')}_{entidad}",
            texto_legal=legal,
            scraped_at=self._now_iso(),
        )

    @staticmethod
    def _clean_alt(alt: str | None) -> str:
        """Saca el prefijo fijo "Promoción bancaria:" que Día le pone a cada alt."""
        if not alt:
            return ""
        limpio = alt.split(":", 1)[-1] if normalize_label(alt).startswith("promocion bancaria") else alt
        return limpio.strip()

    @staticmethod
    def _build_descripcion(porcentaje: float, entidad: str, tope: int | None) -> str:
        base = f"{porcentaje:.0f}% de ahorro con {display_name(entidad)}"
        if not tope:
            return base
        return f"{base} (Tope ${tope:,.0f})".replace(",", ".")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    for descuento in DiaScraper().scrape():
        print(descuento.descripcion, descuento.dias_validos)
