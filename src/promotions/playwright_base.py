"""
Capa intermedia para los scrapers que necesitan un navegador.

Día y Carrefour renderizan sus promociones bancarias en el cliente: la grilla no
existe en el HTML que devuelve el servidor (se verificó bajando la página de Día
descomprimida — 1,7 MB y 62 <script> — donde "reintegro" y "tope" aparecen cero
veces). No hay un endpoint JSON equivalente al de Coto, así que la única forma de
leerlas es ejecutar el JavaScript.

Coto NO pasa por acá, y esa asimetría es deliberada: su endpoint es público y
devuelve JSON, así que levantarle un Chromium sería más lento, más frágil y
dependería de tener el navegador instalado, sin ganar nada.
"""
import logging
from abc import abstractmethod
from typing import Any, ClassVar

from src.promotions.base import DiscountScraper

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)


class PlaywrightScraper(DiscountScraper):
    """Base de los scrapers que necesitan renderizar la página."""

    #: Página que hay que abrir. La define cada subclase.
    URL: ClassVar[str]

    #: Selector que confirma que la grilla ya se hidrató.
    READY_SELECTOR: ClassVar[str]

    #: Milisegundos de gracia después de que aparece READY_SELECTOR. Las apps VTEX
    #: montan las tarjetas en varias pasadas y el primer render llega incompleto.
    SETTLE_MS: ClassVar[int] = 4000

    NAV_TIMEOUT_MS: ClassVar[int] = 60000
    READY_TIMEOUT_MS: ClassVar[int] = 45000

    def __init__(self, headless: bool = True) -> None:
        super().__init__()
        self.headless = headless

    def _fetch_raw(self) -> Any:
        """
        Abre la página, espera a que la grilla exista y delega en la subclase.

        El import de playwright es local a propósito: así importar
        src.promotions no requiere tener playwright ni Chromium instalados, y
        CotoScraper —que no los necesita— sigue funcionando en un entorno pelado.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error(
                "%s necesita playwright. Instalar con: pip install playwright && "
                "python -m playwright install chromium", self.STORE_ID,
            )
            return None

        with sync_playwright() as p:
            browser = None
            try:
                browser = p.chromium.launch(headless=self.headless)
                page = browser.new_context(
                    user_agent=USER_AGENT,
                    locale="es-AR",
                    viewport={"width": 1440, "height": 2400},
                ).new_page()

                page.goto(self.URL, wait_until="domcontentloaded", timeout=self.NAV_TIMEOUT_MS)
                page.wait_for_selector(self.READY_SELECTOR, timeout=self.READY_TIMEOUT_MS)
                page.wait_for_timeout(self.SETTLE_MS)

                return self._extract_from_page(page)
            except Exception as exc:
                # Devolver None (y no propagar) hace que scrape() lo convierta en
                # DiscountScrapeError, que el runner ya sabe traducir a "conservá
                # el bloque anterior de esta tienda".
                logger.error("%s: falló la extracción con navegador: %s", self.STORE_ID, exc)
                return None
            finally:
                if browser is not None:
                    browser.close()

    @abstractmethod
    def _extract_from_page(self, page) -> Any:
        """
        Saca de la página los datos crudos de las promociones.

        Devuelve estructuras de Python planas (dicts, listas), nunca handles de
        Playwright: para cuando corre `_to_discount` el navegador ya está cerrado,
        así que un ElementHandle que sobreviva a este método está muerto.
        """
