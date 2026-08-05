"""
Tests del parser de texto legal (src/promotions/legal_parser.py) y de la
normalización de entidades (src/promotions/banks.py).

Sin red, sin DB, sin modelo. Todos los textos son **capturas reales** del
relevamiento de Coto, Día y Carrefour, no ejemplos inventados: cada caso raro que
aparece acá rompió una versión anterior del parser, y ése es el motivo de que
esté en la lista.
"""
import pytest

from src.promotions.banks import display_name, is_membership, normalize_entity
from src.promotions.legal_parser import (
    extract_cap,
    extract_days,
    extract_percentage,
    is_installment_offer,
    parse_legal_text,
    parse_money_ars,
    says_no_cap,
)


# --------------------------------------------------------------- montos en pesos

@pytest.mark.parametrize("crudo, esperado", [
    ("12.000", 12000),      # punto = separador de miles, NO decimal
    ("$12.000", 12000),
    ("$ 9.500", 9500),      # espacio después del signo
    ("15000", 15000),       # sin separador
    ("1.234.567", 1234567),
    ("1.500,50", 1500),     # con coma, la coma manda: 1500,50 -> 1500
    ("18.000.", 18000),     # punto final de la oración pegado al monto
    ("3399", 3399),
    ("", None),
    (None, None),
    ("abc", None),
])
def test_parse_money_ars(crudo, esperado):
    """
    El punto es separador de miles.

    Es exactamente al revés que parse_amount() de src/coto_logistics.py, que lee
    el punto como decimal porque su fuente es un back-office. Con aquella regla
    "$12.000" daba 12 y "$ 9.500" daba 10: topes mil veces más chicos que los
    reales, y un tope chico de menos no falla ruidosamente, sólo hace que el
    optimizador deje de contar un ahorro que existe.
    """
    assert parse_money_ars(crudo) == esperado


# ------------------------------------------------------------------------ topes

@pytest.mark.parametrize("texto, tope, periodo", [
    # --- Coto: las 8 redacciones distintas del mismo campo `observacion`.
    ("Aplican exclusiones. Ver legales - Tope de Reintegro de $20.000", 20000, None),
    ("Tope de reintegro $12.000 por semana para clientes adheridos", 12000, "semanal"),
    ("Tope de reintegro $ 9.500 por semana para clientes", 9500, "semanal"),
    ("Tope de reintegro: $3.000 por semana para clientes", 3000, "semanal"),
    ("Tope de Reintegro $15000 semanal por usuario.Ver legales.", 15000, "semanal"),
    ("Aplica exclusiones. Tope de Reintegro $10.000 por transacción.", 10000, "transaccion"),
    ("Sin tope de reintegro. Aplican exclusiones. Ver legal.", None, None),
    ("Ver legales - Sin límite de reintegro.", None, None),
    # Dos topes según segmento (Comafi): se toma el MENOR, porque el scraper no
    # sabe a qué segmento pertenece el usuario y prometer el alto sería prometer
    # un ahorro que en la caja no aparece.
    ("Cartera general con tope de reintegro $ 13.000, para Segmento Unico "
     "tope de reintegro $ 18.000 por transacción.", 13000, "transaccion"),
    # --- Día / Carrefour: legales largos en mayúsculas.
    ("CON UN TOPE DE HASTA $20.000 (VEINTE MIL) MENSUAL POR CLIENTE.", 20000, "mensual"),
    ("TOPE DE REINTEGRO $20.000 POR BANCO POR MES PARA COMPRAS MAYORES A $35.000.", 20000, "mensual"),
    ("Tope de devolución $10.000.", 10000, None),
    # Un monto sin palabra de tope adelante no es un tope.
    ("compra minima $5.000 y nada mas", None, None),
])
def test_extract_cap(texto, tope, periodo):
    assert extract_cap(texto) == (tope, periodo)


def test_extract_cap_ignora_el_ejemplo():
    """
    Los legales cierran con un ejemplo numérico, y sus montos NO son el tope.

    Texto real de Banco Columbia en Día. Antes de filtrar los ejemplos, la regla
    del menor se quedaba con los $200 del ejemplo en vez de los $10.000 del tope
    — cincuenta veces más chico.
    """
    texto = (
        "20% DE AHORRO EN COMPRAS EN UN PAGO, TOPE DE REINTEGRO $10.000 (DIEZ MIL PESOS) "
        "POR TRANSACCION. EJEMPLO: COMPRA REALIZADA EN 1 PAGO DE $1000 RECIBIRÁ UN "
        "REINTEGRO DE $200. LA BONIFICACIONES SE VERÁN REFLEJADAS EN EL RESUMEN."
    )
    assert extract_cap(texto) == (10000, "transaccion")


def test_says_no_cap_distingue_negacion_de_silencio():
    """"Sin tope" es una afirmación; no mencionar el tope es otra cosa."""
    assert says_no_cap("Sin tope de reintegro. Aplican exclusiones.") is True
    assert says_no_cap("Ver legales - Sin límite de reintegro.") is True
    assert says_no_cap("Aplican exclusiones. Ver legales.") is False
    # Las dos igual colapsan a None, porque para el optimizador significan lo mismo.
    assert extract_cap("Sin tope de reintegro.") == extract_cap("Aplican exclusiones.")


# ------------------------------------------------------------------ porcentajes

@pytest.mark.parametrize("texto, esperado", [
    ("30% DE DESCUENTO", 30.0),
    ("COMUNIDAD COTO 15%", 15.0),   # el titular no nombra "descuento"
    ("25% DE DESCUENTO", 25.0),
    ("12,5%", 12.5),
    ("18 CUOTAS SIN INTERÉS", None),
    ("", None),
])
def test_extract_percentage_titulo_corto(texto, esperado):
    """Modo laxo: la entrada es el titular de Coto, donde el único número es el descuento."""
    assert extract_percentage(texto) == esperado


@pytest.mark.parametrize("texto, esperado", [
    ("SE OTORGARÁ UN 35% (TREINTA Y CINCO POR CIENTO) DE DESCUENTO SOBRE EL IMPORTE", 35.0),
    ("LA PROMOCIÓN CONSISTE EN UN 15% (QUINCE POR CIENTO) DE REINTEGRO PAGANDO CON", 15.0),
    ("20% DE AHORRO EN COMPRAS EN UN PAGO", 20.0),
    ("EL BENEFICIO CONSISTE EN 10% EN PRODUCTOS O SERVICIOS SELECCIONADOS", 10.0),
    # Las tasas de financiación NO son descuentos, aunque lleven el signo %.
    ("PLAN Z CERO INTERÉS COSTO FINANCIERO TOTAL (CFT) 0% TASA EFECTIVA ANUAL (TEA) 0%", None),
    ("T.N.A., T.E.A. Y C.F.T.N.A. (IVA INCLUIDO): 0,00% FIJO. TASA NOMINAL ANUAL", None),
    ("PLAN 3 CUOTAS SIN INTERÉS CON LAS TARJETAS VISA, MASTERCARD. CFTNA: 0%", None),
])
def test_extract_percentage_legal_estricto(texto, esperado):
    """
    Modo estricto: la entrada es el legal completo, donde el descuento convive
    con las tasas de financiación. Se exige que el porcentaje esté pegado a una
    palabra de beneficio, en cualquiera de los dos órdenes.
    """
    assert extract_percentage(texto, strict=True) == esperado


def test_estricto_rechaza_lo_que_el_laxo_acepta():
    """La diferencia entre los dos modos es real y está testeada."""
    tasa = "COSTO FINANCIERO TOTAL 25% ANUAL SOBRE SALDOS"
    assert extract_percentage(tasa) == 25.0
    assert extract_percentage(tasa, strict=True) is None


@pytest.mark.parametrize("texto, esperado", [
    ("18 CUOTAS SIN INTERÉS", True),
    ("6 CUOTAS SIN INTERÉS", True),
    ("30% DE DESCUENTO", False),
    ("COMUNIDAD COTO 15%", False),
])
def test_is_installment_offer(texto, esperado):
    """17 de las 31 promos digitales de Coto son financiación, no ahorro."""
    assert is_installment_offer(texto) is esperado


# -------------------------------------------------------------------------- días

@pytest.mark.parametrize("texto, esperado", [
    ("Válido únicamente los lunes 03/08, 10/08", ("lunes",)),
    ("VÁLIDO DE LUNES A VIERNES DEL MES", ("lunes", "martes", "miercoles", "jueves", "viernes")),
    ("Todos los días de agosto", ("lunes", "martes", "miercoles", "jueves", "viernes",
                                  "sabado", "domingo")),
    ("Todos los Sábados y Domingos de Agosto", ("sabado", "domingo")),
    # Rango que da la vuelta a la semana.
    ("Martes a Domingo de Agosto", ("martes", "miercoles", "jueves", "viernes",
                                    "sabado", "domingo")),
    ("Lunes, Martes, Miércoles de Agosto", ("lunes", "martes", "miercoles")),
    ("Lunes y Miércoles de Agosto", ("lunes", "miercoles")),
    # Encabezado real de Carrefour: el día está enterrado en la frase.
    ("Programando la entrega de tu pedido para los días Miércoles de Agosto", ("miercoles",)),
    # No dice nada de días.
    ("Válido en el mes de Agosto", ()),
    ("", ()),
])
def test_extract_days(texto, esperado):
    assert extract_days(texto) == esperado


def test_extract_days_no_confunde_plazos_con_dias():
    """
    "DENTRO DE LOS 15 DÍAS HÁBILES" es un plazo de acreditación, no un día de
    vigencia: no tiene que activar el atajo de "todos los días".
    """
    texto = ("EL BENEFICIO SERÁ ACREDITADO DENTRO DE LOS 15 DÍAS HÁBILES POSTERIORES "
             "A LA COMPRA, TODOS LOS LUNES.")
    assert extract_days(texto) == ("lunes",)


def test_extract_days_ordena_y_deduplica():
    assert extract_days("domingo, lunes, domingo y viernes") == ("lunes", "viernes", "domingo")


# ------------------------------------------------------------- entrada de alto nivel

def test_parse_legal_text_devuelve_las_cuatro_claves():
    """La función que consumen los scrapers VTEX, sobre un legal real de Día."""
    texto = (
        "PROMOCIÓN OFRECIDA POR EL BANCO DE LA CIUDAD DE BUENOS AIRES, VÁLIDA DESDE EL "
        "20/07/2026 HASTA EL 31/08/2026, TODOS LOS LUNES. SE OTORGARÁ UN 35% (TREINTA Y "
        "CINCO POR CIENTO) DE DESCUENTO SOBRE EL IMPORTE DE LA COMPRA, CON UN TOPE DE "
        "HASTA $20.000 (VEINTE MIL) MENSUAL POR CLIENTE."
    )
    assert parse_legal_text(texto) == {
        "porcentaje_descuento": 35.0,
        "dias_validos": ("lunes",),
        "tope_reintegro": 20000,
        "tope_periodo": "mensual",
    }


# ------------------------------------------------------------- normalización de entidades

@pytest.mark.parametrize("icono, esperado", [
    ("logo_galicia.png", "galicia"),
    ("logo_naranjax2.png", "naranja_x"),   # el sufijo de versión no puede estorbar
    ("logo_icbc_1.png", "icbc"),
    ("logo_ciudad1.png", "ciudad"),
    ("bbva2.png", "bbva"),
    ("logo_comunidad2.png", "comunidad_coto"),
    ("logo_amex1.png", "amex"),
    ("logo_supervielle2.png", "supervielle"),
    ("logo_patagonia2.png", "patagonia"),
    ("logo_macro_bma3.png", "macro"),
    ("logo_tci.png", "coto_tci"),
    # Una promo de cuotas con logo de Visa no identifica ningún banco.
    ("logo_visa1.png", None),
])
def test_normalize_entity_desde_el_icono_de_coto(icono, esperado):
    """
    El nombre del archivo del logo es la fuente confiable en Coto: el campo
    `banco` es un código numérico que además se reutiliza (banco=0 aparece tanto
    en Comunidad Coto como en una promo Visa genérica).

    Los sufijos de versión ("ciudad1", "naranjax2") obligan a que el borde de
    palabra permita dígitos; con un \\b clásico ninguno de estos matchearía.
    """
    assert normalize_entity(icono) == esperado


@pytest.mark.parametrize("texto", [
    "BENEFICIO DE ALCANCE NACIONAL, VÁLIDO LOS DÍAS JUEVES",
    "PROMOCIÓN VÁLIDA A NIVEL NACIONAL",
])
def test_nacional_no_es_banco_nacion(texto):
    """
    Falso positivo real: "ALCANCE NACIONAL" activaba "nacion" y le asignaba a una
    promo de Personal Pay un descuento de Banco Nación. Lo tapa el borde de
    palabra, que bloquea letras a los costados.
    """
    assert normalize_entity(texto) is None


def test_domicilio_no_es_banco_ciudad():
    """
    Otro falso positivo real: el domicilio legal del anunciante ("CIUDAD AUTÓNOMA
    DE BUENOS AIRES") le daba a Banco del Sol una promo de Banco Ciudad. Acá el
    borde de palabra no alcanza —"ciudad" sí es una palabra— así que la frase se
    borra antes de matchear.
    """
    texto = ("BANCO DEL SOL S.A., CON DOMICILIO EN AV. LEANDRO N. ALEM 1058, PB, "
             "CIUDAD AUTÓNOMA DE BUENOS AIRES")
    assert normalize_entity(texto) == "banco_del_sol"


def test_el_banco_ciudad_de_verdad_si_matchea():
    """La contracara: borrar el domicilio no puede tapar al banco homónimo real."""
    assert normalize_entity("PROMOCIÓN OFRECIDA POR EL BANCO DE LA CIUDAD DE BUENOS AIRES") == "ciudad"


def test_normalize_entity_respeta_el_orden_de_confianza():
    """Devuelve la primera fuente que reconoce, no la primera que existe."""
    assert normalize_entity(None, "", "logo_galicia.png", "naranja") == "galicia"
    assert normalize_entity("marca inventada", "logo_galicia.png") == "galicia"


def test_alias_largo_le_gana_al_corto():
    """"Naranja X" no puede resolverse como "naranja" a secas, ni al revés."""
    assert normalize_entity("Naranja X") == "naranja_x"
    assert normalize_entity("Comunidad Coto") == "comunidad_coto"
    # Carrefour Banco (el banco) y Mi Carrefour (fidelidad) comparten palabra.
    assert normalize_entity("Cuenta Digital de Carrefour Banco") == "carrefour_banco"
    assert normalize_entity("Mi Carrefour") == "mi_carrefour"


def test_membresias_van_por_el_otro_eje_del_perfil():
    """
    El optimizador compara las tarjetas contra user_cards y las membresías contra
    user_memberships. Marcar mal una entidad hace que no se aplique nunca.
    """
    assert is_membership("comunidad_coto") is True
    assert is_membership("mi_carrefour") is True
    assert is_membership("club_la_nacion") is True
    assert is_membership("galicia") is False
    assert is_membership("carrefour_banco") is False


def test_display_name_arregla_las_siglas():
    assert display_name("icbc") == "ICBC"
    assert display_name("naranja_x") == "Naranja X"
    assert display_name("galicia") == "Galicia"   # el default alcanza
