import re


def extract_real_volume(name: str) -> tuple[float, str]:
    """
    Parsea el nombre del producto para extraer el volumen/peso real usando Regex.
    Normaliza todo a gramos (g) o mililitros (ml) para poder comparar magnitudes.
    """
    if not name:
        return 1.0, 'un'

    match = re.search(r'(\d+(?:[,.]\d+)?)\s*(kg|gr|grm|g|l|ltr|ml|cc)\b', name, re.IGNORECASE)
    if match:
        try:
            val = float(match.group(1).replace(',', '.'))
            u = match.group(2).lower()
            if u in ['kg']:
                return val * 1000.0, 'g'
            if u in ['l', 'ltr']:
                return val * 1000.0, 'ml'
            if u in ['gr', 'grm', 'g']:
                return val, 'g'
            if u in ['ml', 'cc']:
                return val, 'ml'
        except ValueError:
            pass
    return 1.0, 'un'
