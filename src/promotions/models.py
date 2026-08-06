"""
El objeto estricto que devuelven todos los scrapers de promociones bancarias.

Es un dataclass y no un modelo pydantic a propósito: en este repo pydantic se usa
sólo para el I/O de FastAPI (src/api.py), mientras que la salida de los módulos
offline es dataclass (ver src/strategic_swaps.py). Mantener esa división evita que
el paquete de scraping arrastre validación de request al proceso de ingesta.
"""
from dataclasses import dataclass, replace
from datetime import date

# Orden canónico de la semana. Coincide con date.weekday() (lunes = 0), así que
# CANONICAL_DAYS[hoy.weekday()] es el día de hoy sin tabla intermedia.
CANONICAL_DAYS = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")
_DAY_ORDER = {day: index for index, day in enumerate(CANONICAL_DAYS)}

# Los mismos ids de tienda que usa el optimizador. Son las claves de
# DEFAULT_MIN_SPEND_LIMITS en src/optimizer.py: si no coinciden, la promo se
# scrapea bien y después no se aplica nunca.
KNOWN_STORES = ("coto_online", "dia_online", "carrefour_online")

# Períodos en los que puede estar expresado un tope de reintegro.
CAP_PERIODS = ("transaccion", "semanal", "mensual")


class InvalidDiscount(ValueError):
    """Un registro scrapeado que no puede convertirse en un BankDiscount usable."""


@dataclass(frozen=True)
class BankDiscount:
    """
    Un descuento bancario de una tienda, ya normalizado.

    Es inmutable para que nadie la mute después de validada, y `dias_validos` es
    tupla (no lista) para que la instancia siga siendo hashable: eso permite
    usarla como clave o en un set sin copiarla.
    """

    store: str
    entidad: str
    porcentaje_descuento: float
    dias_validos: tuple[str, ...]
    tope_reintegro: int | None
    tope_periodo: str | None
    descripcion: str
    promo_id: str
    texto_legal: str
    scraped_at: str

    def __post_init__(self):
        """
        Valida al construir en vez de al persistir.

        Un registro que no cumple estas condiciones no se corrige silenciosamente:
        se rechaza y el llamador lo descarta con log. Es la misma asimetría que
        siguen los flags dietarios y los multipacks — cotizar de más sólo pierde un
        ahorro, cotizar de menos rompe la promesa que el producto le hace al usuario.
        """
        if self.store not in KNOWN_STORES:
            raise InvalidDiscount(f"tienda desconocida: {self.store!r}")

        if not self.entidad:
            raise InvalidDiscount("entidad vacía")

        if not isinstance(self.porcentaje_descuento, (int, float)) or isinstance(self.porcentaje_descuento, bool):
            raise InvalidDiscount(f"porcentaje no numérico: {self.porcentaje_descuento!r}")

        if not 0 < self.porcentaje_descuento <= 100:
            raise InvalidDiscount(f"porcentaje fuera de rango: {self.porcentaje_descuento!r}")

        if not self.dias_validos:
            raise InvalidDiscount("sin días válidos")

        desconocidos = [d for d in self.dias_validos if d not in _DAY_ORDER]
        if desconocidos:
            raise InvalidDiscount(f"días no canónicos: {desconocidos}")

        if self.tope_reintegro is not None:
            if isinstance(self.tope_reintegro, bool) or not isinstance(self.tope_reintegro, int):
                raise InvalidDiscount(f"tope no entero: {self.tope_reintegro!r}")
            if self.tope_reintegro <= 0:
                raise InvalidDiscount(f"tope no positivo: {self.tope_reintegro!r}")

        if self.tope_periodo is not None and self.tope_periodo not in CAP_PERIODS:
            raise InvalidDiscount(f"período de tope desconocido: {self.tope_periodo!r}")

        # Se ordenan y deduplican acá y no en cada scraper: los tres arman
        # `dias_validos` por caminos distintos (Coto desde un array estructurado,
        # los VTEX desde texto libre) y sin esto el mismo descuento tendría dos
        # representaciones según de dónde salió.
        ordenados = tuple(sorted(set(self.dias_validos), key=_DAY_ORDER.__getitem__))
        if ordenados != self.dias_validos:
            object.__setattr__(self, "dias_validos", ordenados)

    def aplica_en(self, dia: date) -> bool:
        """¿Está vigente este descuento en esa fecha?"""
        return CANONICAL_DAYS[dia.weekday()] in self.dias_validos

    def to_json_dict(self) -> dict:
        """Forma serializable. `dias_validos` sale como lista porque JSON no tiene tuplas."""
        return {
            "store": self.store,
            "entidad": self.entidad,
            "porcentaje_descuento": self.porcentaje_descuento,
            "dias_validos": list(self.dias_validos),
            "tope_reintegro": self.tope_reintegro,
            "tope_periodo": self.tope_periodo,
            "descripcion": self.descripcion,
            "promo_id": self.promo_id,
            "texto_legal": self.texto_legal,
            "scraped_at": self.scraped_at,
        }

    @classmethod
    def from_json_dict(cls, data: dict) -> "BankDiscount":
        """
        Inversa de to_json_dict(). Vuelve a pasar por __post_init__, así que un
        archivo editado a mano con un registro inválido falla al cargarse y no se
        cuela hasta el optimizador.
        """
        return cls(
            store=data["store"],
            entidad=data["entidad"],
            porcentaje_descuento=data["porcentaje_descuento"],
            dias_validos=tuple(data.get("dias_validos") or ()),
            tope_reintegro=data.get("tope_reintegro"),
            tope_periodo=data.get("tope_periodo"),
            descripcion=data.get("descripcion", ""),
            promo_id=data.get("promo_id", ""),
            texto_legal=data.get("texto_legal", ""),
            scraped_at=data.get("scraped_at", ""),
        )

    def with_fields(self, **cambios) -> "BankDiscount":
        """Copia con campos cambiados, revalidando. Azúcar sobre dataclasses.replace."""
        return replace(self, **cambios)
