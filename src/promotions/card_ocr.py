"""
Texto de la cara de una tarjeta de promoción, leído con OCR.

Existe por Día: cada tarjeta de /medios-de-pago-y-promociones es una imagen
(el DOM sólo dice "ONLINE / TIENDAS / Ver Legales"), y el legal a veces no
expresa el porcentaje ("MODO 20%" sólo está dibujado) o lista varios planes con
el mismo texto (Naranja X 20/25/30%). Sin leer la imagen esas promos se perdían
o salían con un porcentaje mayor que el publicado.

Usa el binario `tesseract` y no un paquete de Python: hace falta sólo en la
máquina que corre get_bank_promos, igual que Chromium para Playwright. Sin él,
o ante cualquier fallo, devuelve None y el scraper sigue con el legal.

Medido contra las 12 tarjetas de Día (nov-2026): tal cual, Tesseract no lee el
texto rojo sobre blanco (2 de 12); con el canal verde binarizado, 12 de 12.
"""
import io
import logging
import subprocess

import httpx
from PIL import Image

logger = logging.getLogger(__name__)

TIMEOUT_S = 30
# En el canal verde el rojo de Día queda oscuro y el blanco claro: un umbral
# fijo los separa sin depender de la paleta de cada banco.
UMBRAL = 128


def read_card(url: str) -> str | None:
    """Baja la imagen de la tarjeta y devuelve su texto, o None."""
    try:
        respuesta = httpx.get(url, timeout=TIMEOUT_S, follow_redirects=True)
        respuesta.raise_for_status()
        verde = Image.open(io.BytesIO(respuesta.content)).convert("RGB").split()[1]
        binaria = verde.point(lambda v: 255 if v > UMBRAL else 0)
        png = io.BytesIO()
        binaria.save(png, format="PNG")
    except Exception as exc:
        logger.warning("No se pudo bajar o preparar la tarjeta %s: %s", url, exc)
        return None
    return ocr_png(png.getvalue())


def ocr_png(png: bytes) -> str | None:
    # psm 11: texto disperso. La tarjeta no es un párrafo sino bloques sueltos
    # (logo, porcentaje, días, tope), y el modo por defecto pierde el porcentaje.
    try:
        salida = subprocess.run(
            ["tesseract", "stdin", "stdout", "--psm", "11"],
            input=png, capture_output=True, timeout=TIMEOUT_S, check=True,
        ).stdout
    except FileNotFoundError:
        logger.warning("Tesseract no está instalado: las tarjetas se leen sólo del legal.")
        return None
    except Exception as exc:
        logger.warning("Falló el OCR de una tarjeta: %s", exc)
        return None
    return " ".join(salida.decode("utf-8", errors="replace").split()) or None
