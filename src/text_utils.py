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
    """
    return normalize_label(label).replace(" ", "-")
