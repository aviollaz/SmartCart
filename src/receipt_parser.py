# src/receipt_parser.py
"""
Lectura de un ticket de supermercado fotografiado: de la imagen a una lista de
fragmentos de texto candidatos a nombre de producto.

Es OCR local (Tesseract vía pytesseract), no un modelo de visión pago: el
endpoint que lo usa (`POST /receipt/parse` en src/api.py) no tiene
autenticación, así que un costo por imagen sería una superficie de gasto sin
techo — peor que el riesgo ya documentado de Cloud Run ("no hay tope duro de
gasto", CLAUDE.md etapa 10). La contrapartida es precisión: Tesseract sobre una
impresora térmica argentina se equivoca seguido (nombres abreviados, saltos de
línea raros, dígitos pegados al texto). Por eso el matching contra el catálogo
(en src/api.py) usa el mismo embedding semántico que ya usa /search en vez de
exigir texto exacto, y por eso el resultado SIEMPRE pasa por una pantalla de
revisión del usuario antes de tocar el carrito real — nunca se agrega nada en
silencio, misma asimetría que el resto del proyecto (dietético, disponibilidad).

Este módulo es puro (sin red, sin DB): sólo imagen -> líneas de texto -> texto
limpio para embeber. El matching contra `unified_products` vive en la API.
"""
import os
import re
import shutil
import sys
from io import BytesIO

import pytesseract
from PIL import Image, ImageOps

# En el contenedor (Dockerfile instala tesseract-ocr vía apt) el binario ya
# queda en el PATH. En Windows, el instalador de Chocolatey no siempre lo
# agrega — pytesseract entonces falla con "tesseract is not installed" aunque
# el binario exista. Sólo se pisa `tesseract_cmd` cuando el PATH no lo
# resuelve, así que esto es un no-op en cualquier entorno donde sí está.
_WINDOWS_DEFAULT_TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if sys.platform == "win32" and shutil.which("tesseract") is None:
    if os.path.exists(_WINDOWS_DEFAULT_TESSERACT):
        pytesseract.pytesseract.tesseract_cmd = _WINDOWS_DEFAULT_TESSERACT

# Relevado contra una Factura B real (docs/references/ticket_dia.png): el
# formato de DIA separa cantidad/precio-unitario en SU PROPIA línea ("4,00 X
# 4990,00"), sin nombre, y el nombre va en la línea siguiente pegado a un
# "(%IVA)" justo antes del importe final: "ATUN LOM N DIA 354GR (21,00)
# 19960,00" -- es la columna "Descripcion (%IVA) [%BI] Importe" que exige
# cualquier Factura B/C. Otras líneas del mismo ticket (código de barras solo,
# CUIT, N° de comprobante, fecha/hora, "Cant./Precio Unit.", subtotales) NO
# tienen esa forma. Estas regex no intentan cubrir todos los formatos de todas
# las cadenas -- sacan lo que con certeza no es parte de un nombre de producto
# y dejan el resto para que lo resuelva la búsqueda semántica, no esta función.
_SEPARADOR_REPETIDO = re.compile(r"[.\-_]{2,}")
# El decimal es OBLIGATORIO: un importe real de Factura B siempre termina en
# coma (o punto) + 2 dígitos. Exigirlo, en vez de sólo recortarlo si aparece,
# es lo que saca de encima casi todo el ruido de cabecera/pie (CUIT, dirección,
# N° de comprobante, fecha/hora) sin necesitar una lista de frases a excluir:
# ninguna de esas líneas termina en un importe.
#
# **Sin ancla `$` a propósito.** La primera versión exigía que el precio fuera
# literalmente lo último de la línea, y sobre una foto real (no un scan plano)
# eso rompió más de lo que arregló: el OCR deja basura DESPUÉS del precio con
# frecuencia (una mancha, un reflejo, un borde del ticket) -- "ALFAJOR DE
# MAICENA — (21,00)  3990,00 je" perdía la línea ENTERA por el "je" final. Se
# busca el ÚLTIMO precio de la línea y se trunca ahí: todo lo que sigue
# (precio incluido) se descarta igual, pero un token de basura después ya no
# tira abajo un nombre perfectamente legible antes del precio.
_PRECIO_FINAL = re.compile(r"\$?\s*\d+(?:[.,]\d{3})*[.,]\d{2}")
# El "(21,00)" de %IVA queda pegado al nombre, justo antes del importe -- misma
# columna que Tesseract no respeta. Sólo matchea paréntesis con un número
# adentro (no cualquier paréntesis: una aclaración real como "(sabor original)"
# tiene que sobrevivir).
_IVA_ENTRE_PARENTESIS = re.compile(r"\(\s*\d{1,3}(?:[.,]\d{2})?\s*\)")
_CODIGO_INICIAL = re.compile(r"^\s*\d{4,}\s+")
_CANTIDAD_INICIAL = re.compile(r"^\s*\d+\s*[xX]?\s+")
# La "X" de "4,00 X" (línea de cantidad separada, sin nombre) es un signo de
# multiplicar, no una palabra. Sin sacarla, "4,00 X" sobrevive a todo lo demás
# como si fuera un nombre de producto de una sola letra.
_MULTIPLICADOR_SUELTO = re.compile(r"\b[xX]\b")
_RUIDO = re.compile(r"[^\w\sáéíóúñÁÉÍÓÚÑ%/-]")
# Al menos 3 letras SEGUIDAS, no sólo "una letra en algún lado": un código de
# barras mal leído como "B4g0017a51250 e" tiene letras sueltas intercaladas
# entre dígitos (ruido de OCR), no una palabra real. Medido contra el ticket
# real: sin este mínimo, esa clase de residuo sobrevivía como candidato.
_TIENE_PALABRA = re.compile(r"[a-zA-ZáéíóúñÁÉÍÓÚÑ]{3,}")


def extract_lines_from_image(image_bytes: bytes) -> list[str]:
    """
    Corre Tesseract sobre la foto y devuelve las líneas no vacías.

    Medido contra una foto real de un ticket DIA (docs/references/ticket_dia.png,
    sacada de costado sobre una mesada, con brillo y perspectiva, nada de un
    scan plano): dos ajustes marcaron la diferencia entre "casi todo legible" y
    "CALDO GALLINA C/VEGE" leído como "pag C/VESE".

    **`--psm 6`** (asumir un único bloque uniforme de texto) es el que más
    importa. El modo automático de Tesseract intenta segmentar la página en
    columnas/bloques, y sobre una columna angosta de texto disperso —exactamente
    la forma de un ticket— confunde el layout y garabatea nombres enteros. Un
    ticket es la definición de "un bloque uniforme": no hace falta que Tesseract
    adivine la estructura.

    **Duplicar la resolución (LANCZOS)** es el segundo factor: la fuente de una
    impresora térmica fotografiada a la distancia normal de un celular queda
    chica para el reconocimiento LSTM. Con el mismo `--psm 6`, upscalear subió
    perceptiblemente la fidelidad de nombres Y de precios (ej. "7000,00" en vez
    de "700,00" con un dígito perdido). Un threshold binario duro (Otsu) se
    probó también y salió PEOR que sólo autocontraste — se probó y se descartó,
    no se dejó afuera por intuición.

    El resto del preprocesado sigue simple a propósito (gris + autocontraste +
    rotación EXIF): esto no busca ser un pipeline de visión completo para un
    dato que de todas formas pasa por revisión humana antes de tocar el
    carrito, sólo cerrar la brecha que la medición mostró que importaba.
    """
    image = Image.open(BytesIO(image_bytes))
    # Las fotos de celular casi siempre traen la orientación real sólo en el
    # metadato EXIF, no en los píxeles: sin esto, una foto "vertical" que el
    # teléfono guardó rotada 90° llega a Tesseract literalmente de costado.
    image = ImageOps.exif_transpose(image)
    image = image.convert("L")
    image = ImageOps.autocontrast(image)
    image = image.resize((image.width * 2, image.height * 2), Image.LANCZOS)

    texto = pytesseract.image_to_string(image, lang="spa", config="--psm 6")
    return [linea.strip() for linea in texto.splitlines() if linea.strip()]


def clean_line_for_matching(line: str) -> str:
    """
    Recorta una línea OCR'd a lo que vale la pena embeber para buscar contra el
    catálogo: sin precio final, sin %IVA, sin código de barras ni cantidad al
    principio, sin ruido de impresora térmica (puntos de relleno, guiones
    repetidos, "X" de multiplicar suelta).

    **Una línea sin un importe al final no es una fila de producto y se
    descarta entera** (devuelve `""`), no se "limpia a medias". Es la regla que
    saca de encima el ruido de cabecera/pie sin necesitar una lista de frases a
    excluir -- ver el comentario de `_PRECIO_FINAL`. La contrapartida es un
    formato de ticket real que no imprima precio por línea: ese caso da una
    lista vacía (falla ruidoso, el usuario ve "no leímos nada"), no una lista
    con basura mezclada.

    Tampoco intenta reconstruir el nombre real del producto -- para eso está la
    búsqueda semántica contra el catálogo (src/api.py). Acá sólo se saca lo que
    con certeza NO es parte de un nombre de producto.
    """
    texto = _SEPARADOR_REPETIDO.sub(" ", line)

    # Último precio de la línea: todo desde ahí en adelante se descarta (el
    # precio y cualquier basura que el OCR haya dejado después).
    precios = list(_PRECIO_FINAL.finditer(texto))
    if not precios:
        return ""
    texto = texto[: precios[-1].start()]

    texto = _IVA_ENTRE_PARENTESIS.sub("", texto)
    texto = _CODIGO_INICIAL.sub("", texto)
    texto = _CANTIDAD_INICIAL.sub("", texto)
    texto = _MULTIPLICADOR_SUELTO.sub("", texto)
    texto = _RUIDO.sub(" ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()

    # Lo que sobrevive a todo lo anterior sin una palabra real no es un nombre
    # de producto: es el residuo de una línea que sólo tenía cantidad y código
    # (ej. "4,00 X 4990,00" -- sin nombre, en su propia línea -- queda "4,00"
    # después de sacar el importe y la "X" suelta) o un código de barras mal
    # leído con letras sueltas intercaladas.
    if not _TIENE_PALABRA.search(texto):
        return ""

    return texto
