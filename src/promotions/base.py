"""
La clase base abstracta de los scrapers de promociones bancarias.

El diseño es un *template method*: `scrape()` fija el ciclo de vida completo
(traer -> iterar -> traducir -> validar -> reportar) y no se sobreescribe. Cada
cadena sólo aporta las tres piezas que realmente difieren — de dónde salen los
datos, cómo se recorre la respuesta y cómo se traduce un registro suelto.

El punto de concentrar el resto acá es que el descarte de registros es la parte
del scraping que más silenciosamente se rompe: si cada subclase filtrara por su
cuenta, tres implementaciones tendrían tres criterios distintos sobre qué es una
promo inválida y ninguna llevaría la cuenta de lo que tiró.
"""
import logging
from abc import ABC, abstractmethod
from collections import Counter
from datetime import datetime, timezone
from typing import Any, ClassVar, Iterable

from src.promotions.models import BankDiscount, InvalidDiscount

logger = logging.getLogger(__name__)


class DiscountScrapeError(RuntimeError):
    """
    La corrida de una cadena falló y su resultado no es confiable.

    Se distingue de "esta cadena no tiene promociones" a propósito. El modo de
    falla que justifica la clase está documentado en CLAUDE.md para el
    `sha256Hash` rotado de Carrefour: la fuente responde 200 con un payload que no
    sirve, el scraper lo lee como una corrida limpia de 0 productos, y el error
    sólo se nota mucho después. Un resultado vacío se trata como falla, no como
    dato, y el runner conserva el bloque anterior en vez de pisarlo con [].
    """


class DiscountScraper(ABC):
    """Base de todos los scrapers de descuentos bancarios."""

    #: Id de tienda del optimizador ("coto_online", ...). Lo define cada subclase.
    STORE_ID: ClassVar[str]

    #: Por debajo de esto la corrida se considera fallida en vez de vacía.
    MIN_EXPECTED_DISCOUNTS: ClassVar[int] = 1

    def __init__(self) -> None:
        # Motivo -> cantidad. Lo lee el runner para poder decir "descarté 17 por
        # cuotas" en vez de dejar que 17 registros desaparezcan sin explicación.
        self.discards: Counter = Counter()

    # ------------------------------------------------------------------ público

    def scrape(self) -> list[BankDiscount]:
        """
        Ciclo completo de una cadena. No se sobreescribe: las subclases
        implementan los tres métodos abstractos de abajo.
        """
        self.discards.clear()

        raw = self._fetch_raw()
        if raw is None:
            raise DiscountScrapeError(f"{self.STORE_ID}: no se pudo obtener la fuente")

        discounts: list[BankDiscount] = []
        for raw_promo in self._iter_raw_promos(raw):
            try:
                discount = self._to_discount(raw_promo)
            except InvalidDiscount as exc:
                # Un registro que no pasa la validación del modelo se descarta,
                # no se corrige: un descuento inventado se aplica de verdad.
                self._discard(f"invalido: {exc}")
                continue
            except Exception as exc:  # noqa: BLE001 - una promo rota no voltea la corrida
                logger.warning("%s: error traduciendo una promo: %s", self.STORE_ID, exc)
                self._discard("error de traduccion")
                continue

            if discount is not None:
                discounts.append(discount)

        discounts = self._deduplicate(discounts)

        if len(discounts) < self.MIN_EXPECTED_DISCOUNTS:
            raise DiscountScrapeError(
                f"{self.STORE_ID}: {len(discounts)} descuentos utilizables "
                f"(descartes: {dict(self.discards)}). Se trata como falla, no como catálogo vacío."
            )

        logger.info(
            "%s: %d descuentos utilizables, %d descartados %s",
            self.STORE_ID, len(discounts), sum(self.discards.values()), dict(self.discards),
        )
        return discounts

    # ------------------------------------------------------------- a implementar

    @abstractmethod
    def _fetch_raw(self) -> Any:
        """Trae la fuente cruda (JSON decodificado, lista de textos legales, ...)."""

    @abstractmethod
    def _iter_raw_promos(self, raw: Any) -> Iterable[Any]:
        """Recorre la fuente y entrega un registro por promoción."""

    @abstractmethod
    def _to_discount(self, raw_promo: Any) -> BankDiscount | None:
        """
        Traduce un registro a BankDiscount, o devuelve None para descartarlo.

        Antes de devolver None conviene llamar a `self._discard(motivo)` para que
        el descarte quede contado.
        """

    # ------------------------------------------------------------------ helpers

    def _discard(self, motivo: str) -> None:
        """Registra un descarte por motivo."""
        self.discards[motivo] += 1

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def _deduplicate(self, discounts: list[BankDiscount]) -> list[BankDiscount]:
        """
        Saca duplicados conservando el orden.

        Existe porque las grillas renderizadas en cliente repiten tarjetas (un
        carrusel que envuelve, o una promo listada en dos secciones), y sin esto
        el mismo descuento entraría dos veces al archivo.

        La comparación es por identidad *semántica* y no por igualdad del objeto:
        dos apariciones de la misma promo traen distinto `promo_id` (en las
        grillas VTEX el id sale del índice de la tarjeta) y pueden traer distinto
        `scraped_at` si la corrida cruza un segundo. Comparar el objeto entero no
        deduplicaría nada.
        """
        vistos: set[tuple] = set()
        unicos = []
        for discount in discounts:
            clave = (
                discount.store,
                discount.entidad,
                discount.porcentaje_descuento,
                discount.dias_validos,
                discount.tope_reintegro,
                discount.tope_periodo,
            )
            if clave in vistos:
                self._discard("duplicado")
                continue
            vistos.add(clave)
            unicos.append(discount)
        return unicos
