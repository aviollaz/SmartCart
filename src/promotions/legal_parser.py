"""
Parseo del texto legal de una promoción bancaria.

Funciones puras, sin red ni I/O: es la pieza que más se va a tocar cuando las
cadenas cambien la redacción, y la única que se puede testear exhaustivamente
contra textos reales sin levantar un navegador.

Las redacciones que hay que soportar no son hipotéticas — salen del relevamiento
del endpoint de Coto, donde el mismo concepto aparece escrito de seis formas:

    "Aplican exclusiones. Ver legales - Tope de Reintegro de $20.000"
    "Tope de reintegro $12.000 por semana para clientes adheridos a Plan Épico"
    "Tope de reintegro $ 9.500 por semana ..."            <- espacio tras el $
    "Tope de Reintegro $15000 semanal por usuario."        <- sin separador de miles
    "Tope de Reintegro $10.000 por transacción."
    "Sin tope de reintegro. Aplican exclusiones. Ver legal."
"""
import re

from src.promotions.models import CANONICAL_DAYS
from src.text_utils import normalize_label

# Un porcentaje puede venir con decimales ("12,5%") aunque hoy todos sean enteros.
_PORCENTAJE_RE = re.compile(r"(\d{1,3}(?:[.,]\d+)?)\s*%")

# Palabras que señalan que un porcentaje es el beneficio y no una tasa.
_BENEFICIO = r"(?:descuento|reintegro|ahorro|cashback|bonificacion|beneficio consiste)"

# Los dos órdenes en que aparece: el número antes de la palabra o después. Se
# prohíben '.' y '%' en el medio para no saltar de una oración —o de un
# porcentaje— a la siguiente.
_PORCENTAJE_ESTRICTO_RES = (
    re.compile(r"(\d{1,3}(?:[.,]\d+)?)\s*%[^.%]{0,60}?" + _BENEFICIO),
    re.compile(_BENEFICIO + r"[^.%]{0,40}?(\d{1,3}(?:[.,]\d+)?)\s*%"),
)

# El monto sólo se acepta si viene precedido por una palabra de tope dentro de una
# ventana corta. Sin esa guarda, un legal que mencione "compra mínima $5.000"
# aportaría un monto que no es un tope y, al quedarnos con el menor, ganaría.
_TOPE_RE = re.compile(r"(?:tope|reintegro|limite|maximo)[^$]{0,40}\$\s*([\d.,]+)")

# Los legales suelen cerrar con un ejemplo numérico, y ahí aparecen montos que no
# son topes: el de Banco Columbia dice "TOPE DE REINTEGRO $10.000 ... EJEMPLO:
# COMPRA REALIZADA EN 1 PAGO DE $1000 RECIBIRÁ UN REINTEGRO DE $200", y quedarse
# con el menor daba un tope de $200 — cincuenta veces más chico que el real.
_EJEMPLO_RE = re.compile(r"\bejemplo\b")

# Se corta por punto SEGUIDO DE ESPACIO: un punto pelado también separa los miles
# ("$10.000") y partir por ahí rompería los montos justo antes de leerlos.
_ORACION_RE = re.compile(r"(?<=\.)\s+")

# "Sin tope" / "sin límite de reintegro" / "sin limite". Es un resultado afirmativo
# ("no hay tope"), distinto de no haber encontrado nada.
_SIN_TOPE_RE = re.compile(r"sin\s+(?:tope|limite)")

_PERIODOS = (
    ("transaccion", (r"por\s+transaccion", r"por\s+compra", r"por\s+operacion", r"por\s+ticket")),
    ("semanal", (r"por\s+semana", r"semanal")),
    ("mensual", (r"por\s+mes", r"mensual")),
)

_DIA_A_DIA_RE = re.compile(
    r"(" + "|".join(CANONICAL_DAYS) + r")\s+a\s+(" + "|".join(CANONICAL_DAYS) + r")"
)

# Se aplica sobre texto ya normalizado (sin acentos), por eso "dias" y no "días".
_TODOS_LOS_DIAS_RE = re.compile(r"todos\s+los\s+dias|toda\s+la\s+semana")


# Un monto escrito como grupos de tres ("12.000", "1.234.567"): el punto es
# separador de miles, no decimal.
_MILES_RE = re.compile(r"\d{1,3}(?:\.\d{3})+")


def _normalizar(texto: str | None) -> str:
    """Casefold sin acentos, para que 'Transacción' y 'transaccion' sean lo mismo."""
    if not texto:
        return ""
    return normalize_label(str(texto))


def parse_money_ars(raw: str | None) -> int | None:
    """
    Convierte un monto en pesos escrito por un humano a entero.

    Deliberadamente NO reusa parse_amount() de src/coto_logistics.py, aunque se
    parezcan: esa función documenta que "sin coma, el punto se lee como decimal",
    que es correcto para el back-office de Coto (devuelve "3399") y exactamente lo
    contrario de lo que significa en un texto legal. Con esa regla "$12.000" da 12
    y "$ 9.500" da 10 (redondeando 9,5), o sea topes mil veces menores que los
    reales. Un tope demasiado chico no rompe nada ruidosamente: el optimizador
    simplemente deja de contar un ahorro que existe, y nadie se entera.

    La regla acá es la del castellano rioplatense: la coma decide los decimales, y
    el punto es separador de miles cuando agrupa de a tres.
    """
    if raw is None:
        return None

    texto = str(raw).strip().replace("$", "").replace(" ", "")
    # La captura del regex puede arrastrar la puntuación que cierra la oración
    # ("...reintegro $18.000."), y ese punto colgado rompe el float().
    texto = texto.rstrip(".,")
    if not texto:
        return None

    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif _MILES_RE.fullmatch(texto):
        texto = texto.replace(".", "")

    try:
        return int(round(float(texto)))
    except ValueError:
        return None


def is_installment_offer(texto: str | None) -> bool:
    """
    ¿Es una oferta de financiación ("18 CUOTAS SIN INTERÉS") y no un descuento?

    En Coto son 17 de 31 promociones digitales. No reducen el precio del carrito
    —difieren el pago— así que el optimizador no las puede modelar y hay que
    descartarlas. Se expone como función propia para poder contarlas en el log:
    17 registros que desaparecen sin explicación parecen un scraper roto.
    """
    normalizado = _normalizar(texto)
    return "cuota" in normalizado and not _PORCENTAJE_RE.search(normalizado)


def extract_percentage(texto: str | None, strict: bool = False) -> float | None:
    """
    Devuelve el porcentaje de descuento, o None si el texto no expresa uno.

    Dos modos, porque las fuentes son de naturaleza distinta:

    - `strict=False` (Coto): la entrada es el titular de la promo, un texto corto
      donde el único número es el descuento ("30% DE DESCUENTO", "COMUNIDAD COTO
      15%"). Cualquier porcentaje sirve.

    - `strict=True` (Día, Carrefour): la entrada es el legal completo, un párrafo
      largo donde conviven el descuento y las tasas de financiación —
      "COSTO FINANCIERO TOTAL (CFT) 0% TASA EFECTIVA ANUAL (TEA) 0%", "T.N.A.
      (IVA INCLUIDO): 0,00% FIJO". Ahí se exige que el porcentaje esté pegado a
      una palabra de beneficio, en cualquiera de los dos órdenes en que aparece:
      "UN 15% (QUINCE POR CIENTO) DE REINTEGRO" y "EL BENEFICIO CONSISTE EN 10%".

    Si hay varios se queda con el mayor, que es el que la tienda publicita.
    """
    normalizado = _normalizar(texto)
    patron = _PORCENTAJE_ESTRICTO_RES if strict else (_PORCENTAJE_RE,)

    encontrados = []
    for regex in patron:
        for match in regex.finditer(normalizado):
            valor = match.group(1).replace(",", ".")
            try:
                numero = float(valor)
            except ValueError:
                continue
            # El 0% siempre es una tasa de financiación, nunca un descuento.
            if 0 < numero <= 100:
                encontrados.append(numero)

    if not encontrados:
        return None
    return max(encontrados)


def extract_days(texto: str | None) -> tuple[str, ...]:
    """
    Devuelve los días en los que aplica la promo, en orden canónico.

    Soporta las tres formas que usan las cadenas: días sueltos ("los lunes y
    martes"), rangos ("de lunes a viernes") y la universal ("todos los días").
    Una tupla vacía significa "el texto no dice nada de días", que el llamador
    tiene que resolver — no significa "ningún día".
    """
    normalizado = _normalizar(texto)
    if not normalizado:
        return ()

    if _TODOS_LOS_DIAS_RE.search(normalizado):
        return tuple(CANONICAL_DAYS)

    encontrados: set[str] = set()

    # Los rangos se expanden primero. Se permite que den la vuelta a la semana
    # ("viernes a domingo" y también "sabado a lunes") porque los fines de semana
    # promocionales se escriben de las dos maneras.
    for inicio, fin in _DIA_A_DIA_RE.findall(normalizado):
        i, f = CANONICAL_DAYS.index(inicio), CANONICAL_DAYS.index(fin)
        largo = (f - i) % 7
        encontrados.update(CANONICAL_DAYS[(i + paso) % 7] for paso in range(largo + 1))

    # Después los sueltos. Se busca por substring y no por palabra entera para que
    # los plurales ("sábados", "domingos") entren sin una regla aparte.
    for dia in CANONICAL_DAYS:
        if dia in normalizado:
            encontrados.add(dia)

    return tuple(sorted(encontrados, key=CANONICAL_DAYS.index))


def extract_cap(texto: str | None) -> tuple[int | None, str | None]:
    """
    Devuelve (tope_reintegro, tope_periodo).

    `(None, None)` cubre dos casos que el llamador puede querer distinguir y que
    acá se colapsan a propósito, porque para el optimizador significan lo mismo
    (no hay límite conocido): que el texto diga "sin tope de reintegro", y que no
    mencione ningún tope. Quien necesite separarlos puede llamar a
    `says_no_cap()`.

    Cuando el texto trae más de un tope se devuelve el MENOR. La redacción real
    que fuerza esto es la de Comafi: "Cartera general con tope de reintegro
    $13.000, para Segmento Unico tope de reintegro $18.000". El scraper no sabe a
    qué segmento pertenece el usuario, y sobreestimar el tope hace que el
    optimizador prometa un ahorro que en la caja no aparece. Es el mismo criterio
    con el que el repo resuelve los multipacks y los flags dietarios.
    """
    normalizado = _normalizar(texto)
    if not normalizado:
        return None, None

    if _SIN_TOPE_RE.search(normalizado):
        return None, None

    montos = []
    for crudo in _TOPE_RE.findall(_strip_examples(normalizado)):
        monto = parse_money_ars(crudo)
        if monto is not None and monto > 0:
            montos.append(monto)

    if not montos:
        return None, None

    return min(montos), _extract_period(normalizado)


def says_no_cap(texto: str | None) -> bool:
    """¿El texto afirma explícitamente que no hay tope? Distinto de no decir nada."""
    return bool(_SIN_TOPE_RE.search(_normalizar(texto)))


def _strip_examples(normalizado: str) -> str:
    """
    Saca las oraciones que son un ejemplo numérico.

    Un ejemplo ilustra el beneficio con una compra ficticia, así que los montos
    que menciona son consecuencias del tope, no el tope. Dejarlos adentro hacía
    que la regla del menor (ver extract_cap) eligiera siempre el número del
    ejemplo, que por construcción es más chico que el límite.
    """
    return " ".join(o for o in _ORACION_RE.split(normalizado) if not _EJEMPLO_RE.search(o))


def _extract_period(normalizado: str) -> str | None:
    for periodo, patrones in _PERIODOS:
        if any(re.search(patron, normalizado) for patron in patrones):
            return periodo
    return None


def parse_legal_text(texto: str | None) -> dict:
    """
    Parsea un bloque de texto legal completo.

    Es la entrada de alto nivel que usan los scrapers de Día y Carrefour, donde
    todo (porcentaje, días y tope) viene mezclado en un solo párrafo del modal
    "Ver Legales". Coto no la usa entera: su endpoint ya trae los días
    estructurados, así que llama a extract_cap() sobre `observacion` y a
    extract_percentage() sobre `textoDescuento` por separado.

    Devuelve siempre las cuatro claves. Un valor en None significa "no se pudo
    extraer", nunca un default inventado.
    """
    tope, periodo = extract_cap(texto)
    return {
        "porcentaje_descuento": extract_percentage(texto),
        "dias_validos": extract_days(texto),
        "tope_reintegro": tope,
        "tope_periodo": periodo,
    }
