import re
import unicodedata


def normalize_label(label: str) -> str:
    """Casefold + sin acentos/diacríticos + espacios colapsados, solo para matchear."""
    decomposed = unicodedata.normalize("NFKD", label)
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(without_accents.casefold().split())


def slugify_segment(label: str) -> str:
    """
    Normaliza una etiqueta de categoría a un token estable para usar como tag
    en Postgres (ej. "Aceites y Aderezos" -> "aceites-y-aderezos").

    Colapsa cualquier corrida de caracteres no alfanuméricos en un solo guión,
    no sólo los espacios. Reemplazar espacios alcanzaba mientras las categorías
    scrapeadas no tuvieran puntuación, pero las taxonomías la usan —
    "Sal, aderezos y saborizadores" salía como `sal,-aderezos-y-saborizadores`,
    con la coma adentro del tag. Un tag así no rompe nada visible: simplemente
    no matchea nunca con el `&&` de Postgres, que es la peor forma de fallar.
    """
    return re.sub(r"[^a-z0-9]+", "-", normalize_label(label)).strip("-")
