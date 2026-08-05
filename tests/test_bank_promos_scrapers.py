"""
Tests de los scrapers de promociones bancarias (src/promotions/).

Sin red: el payload de Coto va inline y el transporte se simula con
httpx.MockTransport, igual que en tests/test_coto_logistics.py. Día y Carrefour
se ejercitan alimentando `_to_discount()` con los dicts que devolvería el
navegador, que es el mismo patrón con el que tests/test_carrefour_scraper.py
prueba `process_products` sobre una respuesta ya decodificada.

Los registros son capturas reales recortadas, no invenciones.
"""
import httpx
import pytest

from src.promotions import CarrefourScraper, CotoScraper, DiaScraper, DiscountScrapeError
from src.promotions.models import BankDiscount, InvalidDiscount

# --------------------------------------------------------------- payload de Coto

def _promo_coto(**overrides):
    """Una promoción digital de Coto, con la forma exacta del actor ATG."""
    base = {
        "id": "171",
        "banco": 5,
        "icono": "logo_icbc_1.png",
        "descripcion": "En un pago con tarjetas de crédito Visa, Mastercard y Visa débito",
        "textoDescuento": "30% DE DESCUENTO",
        "observacion": "Aplican exclusiones. Ver legales - Tope de Reintegro de $20.000",
        "dias": [{"descripcion": "Lunes", "id": 2}],
        "formaPago": 7,
    }
    base.update(overrides)
    return base


def _respuesta_coto(promos, fisicas=None):
    return {
        "codigoError": "0",
        "result": {
            "@class": "atg.dto.backOffice.DtoPromocionesMulticanal",
            "promocionesDigitales": promos,
            "promocionesSucursalesFisicas": fisicas if fisicas is not None else [],
        },
    }


def _cliente(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def _handler_json(payload, status_code=200):
    def handler(request):
        return httpx.Response(status_code, json=payload)
    return handler


# ------------------------------------------------------------------------- Coto

def test_coto_traduce_una_promocion_completa():
    scraper = CotoScraper()
    descuento = scraper._to_discount(_promo_coto())

    assert descuento.store == "coto_online"
    assert descuento.entidad == "icbc"
    assert descuento.porcentaje_descuento == 30.0
    assert descuento.dias_validos == ("lunes",)
    assert descuento.tope_reintegro == 20000
    assert descuento.promo_id == "coto_171"
    assert "ICBC" in descuento.descripcion


def test_coto_descarta_la_financiacion():
    """
    17 de las 31 promociones digitales son "N CUOTAS SIN INTERÉS": difieren el
    pago, no bajan el precio, y el modelo del optimizador no las representa.
    """
    scraper = CotoScraper()
    assert scraper._to_discount(_promo_coto(textoDescuento="18 CUOTAS SIN INTERÉS")) is None
    assert scraper.discards["cuotas sin interes"] == 1


def test_coto_descarta_si_no_reconoce_la_entidad():
    """Adivinar el banco produciría un descuento atribuido al equivocado."""
    scraper = CotoScraper()
    promo = _promo_coto(icono="logo_desconocido9.png",
                        descripcion="En un pago", textoDescuento="20% DE DESCUENTO")
    assert scraper._to_discount(promo) is None
    assert scraper.discards["entidad desconocida"] == 1


def test_coto_lee_los_dias_del_array_estructurado():
    """Coto ya los entrega estructurados; no hay que parsear texto libre."""
    promo = _promo_coto(dias=[{"descripcion": "Sabado"}, {"descripcion": "Miercoles"}])
    descuento = CotoScraper()._to_discount(promo)
    # Salen en orden canónico aunque hayan llegado desordenados.
    assert descuento.dias_validos == ("miercoles", "sabado")


def test_coto_ignora_dias_que_no_son_dias():
    scraper = CotoScraper()
    assert scraper._to_discount(_promo_coto(dias=[{"descripcion": "Feriados"}])) is None
    assert scraper.discards["sin dias"] == 1


def test_coto_no_repite_la_entidad_en_la_descripcion():
    """Los títulos mezclan formatos: "30% DE DESCUENTO" no nombra al banco, "COMUNIDAD COTO 15%" sí."""
    descuento = CotoScraper()._to_discount(
        _promo_coto(icono="logo_comunidad2.png", textoDescuento="COMUNIDAD COTO 15%",
                    observacion="Sin límite de reintegro.")
    )
    assert descuento.descripcion == "Comunidad coto 15%"


def test_coto_solo_mira_las_promociones_digitales():
    """`promocionesSucursalesFisicas` son de los locales; el optimizador compra online."""
    scraper = CotoScraper()
    payload = _respuesta_coto([_promo_coto()], fisicas=[_promo_coto(id="999")])
    assert len(list(scraper._iter_raw_promos(payload))) == 1


@pytest.mark.parametrize("payload", [{}, {"result": {}}, {"result": {"promocionesDigitales": None}}])
def test_coto_tolera_payloads_incompletos(payload):
    assert list(CotoScraper()._iter_raw_promos(payload)) == []


def test_coto_end_to_end_con_transporte_simulado():
    scraper = CotoScraper(client=_cliente(_handler_json(_respuesta_coto([_promo_coto()]))))
    descuentos = scraper.scrape()
    assert [d.entidad for d in descuentos] == ["icbc"]


def test_coto_rechaza_html_con_status_200():
    """
    www.coto.com.ar es un SPA que sirve su index.html con HTTP 200 para cualquier
    ruta desconocida: mirar sólo el status haría parsear una página web como si
    fuera la respuesta del actor.
    """
    def handler(request):
        return httpx.Response(200, text="<html><body>SPA</body></html>",
                              headers={"content-type": "text/html"})

    with pytest.raises(DiscountScrapeError):
        CotoScraper(client=_cliente(handler)).scrape()


def test_coto_no_manda_el_token_de_sesion():
    """
    El `_dynSessConf` que circula en la URL es irrelevante: se probó con token
    válido, con uno inventado y sin ninguno, y las tres respuestas son idénticas.
    Hardcodearlo sólo agregaría algo que caduca.
    """
    vistas = {}

    def handler(request):
        vistas["url"] = str(request.url)
        return httpx.Response(200, json=_respuesta_coto([_promo_coto()]))

    CotoScraper(client=_cliente(handler)).scrape()
    assert "_dynSessConf" not in vistas["url"]


# -------------------------------------------------------------------------- Día

def _tarjeta_dia(**overrides):
    base = {
        "indice": 0,
        "alt": "Promoción bancaria: Banco Columbia, Banco Columbia",
        "src": "https://diaio.vtexassets.com/imagen.jpg",
        "dias": ["lunes", "viernes"],
        "legal": (
            "CARTERA DE CONSUMO. PARA COMPRAS REALIZADAS ÚNICAMENTE LOS DIAS LUNES Y "
            "VIERNES CON LAS TARJETAS DE CREDITO VISA Y MASTERCARD EMITIDAS POR BANCO "
            "COLUMBIA. 20% DE AHORRO EN COMPRAS EN UN PAGO, TOPE DE REINTEGRO $10.000 "
            "(DIEZ MIL PESOS) POR TRANSACCION."
        ),
    }
    base.update(overrides)
    return base


def test_dia_traduce_una_tarjeta():
    descuento = DiaScraper()._to_discount(_tarjeta_dia())
    assert descuento.store == "dia_online"
    assert descuento.entidad == "columbia"
    assert descuento.porcentaje_descuento == 20.0
    assert descuento.dias_validos == ("lunes", "viernes")
    assert descuento.tope_reintegro == 10000
    assert descuento.tope_periodo == "transaccion"


def test_dia_prefiere_los_dias_de_los_tabs_sobre_el_texto():
    """
    Los tabs de la grilla filtran de verdad, así que dan los días como dato
    estructurado. El legal es sólo el respaldo.
    """
    descuento = DiaScraper()._to_discount(_tarjeta_dia(dias=["martes"]))
    assert descuento.dias_validos == ("martes",)


def test_dia_cae_al_texto_si_los_tabs_no_dijeron_nada():
    descuento = DiaScraper()._to_discount(_tarjeta_dia(dias=[]))
    assert descuento.dias_validos == ("lunes", "viernes")


def test_dia_descarta_el_legal_que_solo_trae_un_ejemplo():
    """
    Caso real de Credicoop: el legal no dice el porcentaje en ninguna parte, sólo
    "EN UN CONSUMO DE $60.000 RECIBIRÁ UN REINTEGRO DE $15.000". Deducir el 25%
    de esa división sería publicar un número que la tienda no publicó.
    """
    scraper = DiaScraper()
    legal = ("APLICA A CONSUMO DE TIPO FAMILIAR. VIGENTE LOS MIÉRCOLES. EJEMPLO: EN UN "
             "CONSUMO DE $60.000 RECIBIRÁ UN REINTEGRO DE $15.000 (TOPE MÁXIMO).")
    assert scraper._to_discount(_tarjeta_dia(legal=legal, dias=["miercoles"])) is None
    assert scraper.discards["sin porcentaje de descuento"] == 1


def test_dia_descarta_los_planes_de_cuotas():
    """El legal trae "0%" de CFT, que no es un descuento."""
    scraper = DiaScraper()
    legal = ("PLAN 3 CUOTAS SIN INTERÉS CON LAS TARJETAS VISA Y MASTERCARD. COSTO "
             "FINANCIERO TOTAL (CFT) 0% TASA EFECTIVA ANUAL (TEA) 0%.")
    assert scraper._to_discount(_tarjeta_dia(legal=legal)) is None
    assert scraper.discards["sin porcentaje de descuento"] == 1


def test_dia_limpia_el_prefijo_del_alt():
    assert DiaScraper()._clean_alt("Promoción bancaria: Banco Columbia") == "Banco Columbia"
    assert DiaScraper()._clean_alt("") == ""


# -------------------------------------------------------------------- Carrefour

def _tarjeta_carrefour(**overrides):
    base = {
        "indice": 0,
        "online": True,
        "fecha": "Todos los Jueves de Agosto",
        "porcentaje": "20",
        "rotulo": "De descuento",
        "titulo": "20% de descuento en un pago con Cuenta Digital de Carrefour Banco",
        "texto": "Descuento aplicado en el acto. Tope de devolución $10.000.",
        "legal": "DESCUENTO EXCLUSIVO ABONANDO CON CUENTA DIGITAL DE CARREFOUR BANCO.",
        "imagenes": ["cuentaDigital.webp", "carrefour-banco (2).webp"],
    }
    base.update(overrides)
    return base


def test_carrefour_traduce_una_tarjeta():
    descuento = CarrefourScraper()._to_discount(_tarjeta_carrefour())
    assert descuento.store == "carrefour_online"
    assert descuento.entidad == "carrefour_banco"
    assert descuento.porcentaje_descuento == 20.0
    assert descuento.dias_validos == ("jueves",)
    assert descuento.tope_reintegro == 10000


def test_carrefour_descarta_las_promos_de_local_fisico():
    """13 de las 32 tarjetas no aplican comprando por web."""
    scraper = CarrefourScraper()
    assert scraper._to_discount(_tarjeta_carrefour(online=False)) is None
    assert scraper.discards["solo local fisico"] == 1


def test_carrefour_no_confunde_cuotas_con_porcentaje():
    """
    La trampa principal de esta página: el bloque grande dice "6" tanto en
    "6% de descuento" como en "Hasta 6 Cuotas sin interés", y el símbolo "%" es un
    span aparte que se renderiza igual. Leer el número sin mirar el rótulo
    convierte un plan de 6 cuotas en un 6% que no existe.
    """
    scraper = CarrefourScraper()
    tarjeta = _tarjeta_carrefour(
        porcentaje="6", rotulo="sin interés",
        titulo="Hasta 6 Cuotas sin interés con Mercado Pago",
        imagenes=["mercadopago.png"],
    )
    assert scraper._to_discount(tarjeta) is None
    assert scraper.discards["cuotas sin interes"] == 1


def test_carrefour_cae_al_titulo_si_el_bloque_no_es_un_porcentaje():
    """Se observó una tarjeta cuyo rótulo era "Tope de devolución $..."."""
    descuento = CarrefourScraper()._to_discount(
        _tarjeta_carrefour(porcentaje="Tope de devolución", rotulo="")
    )
    assert descuento.porcentaje_descuento == 20.0


def test_carrefour_descarta_lo_que_no_nombra_ningun_dia():
    """
    "Programando la entrega de tu pedido" y "Válido en el mes de Agosto" no dicen
    ningún día. Asumir "todos" las aplicaría un martes sin que nadie lo haya
    dicho, y el filtro por día del loader existe justamente para no prometer un
    ahorro el día equivocado.
    """
    scraper = CarrefourScraper()
    assert scraper._to_discount(_tarjeta_carrefour(fecha="Válido en el mes de Agosto",
                                                   legal="SIN DIAS ACA")) is None
    assert scraper.discards["sin dias"] == 1


def test_carrefour_lee_el_dia_enterrado_en_la_frase():
    descuento = CarrefourScraper()._to_discount(
        _tarjeta_carrefour(fecha="Programando la entrega de tu pedido para los días Miércoles de Agosto")
    )
    assert descuento.dias_validos == ("miercoles",)


# ------------------------------------------------------- comportamiento de la base

def test_una_corrida_vacia_es_una_falla_y_no_un_catalogo_vacio():
    """
    Modo de falla documentado en CLAUDE.md para el sha256Hash rotado de
    Carrefour: la fuente responde 200 con un payload inservible, el scraper lo
    lee como una corrida limpia de 0 resultados, y nadie se entera. Un resultado
    vacío se trata como error para que el runner conserve el bloque anterior.
    """
    scraper = CotoScraper(client=_cliente(_handler_json(_respuesta_coto([]))))
    with pytest.raises(DiscountScrapeError):
        scraper.scrape()


def test_deduplica_por_identidad_semantica():
    """
    Día lista la misma promo de Naranja X en tres tarjetas. Comparar el objeto
    entero no deduplicaría nada, porque `promo_id` sale del índice de la tarjeta
    y `scraped_at` puede cambiar si la corrida cruza un segundo.
    """
    scraper = DiaScraper()
    tarjetas = [_tarjeta_dia(indice=i) for i in range(3)]
    descuentos = [scraper._to_discount(t) for t in tarjetas]
    assert len({d.promo_id for d in descuentos}) == 3      # son distintos objetos
    assert len(scraper._deduplicate(descuentos)) == 1      # pero una sola promo
    assert scraper.discards["duplicado"] == 2


def test_un_registro_invalido_se_descarta_sin_voltear_la_corrida():
    """
    Un porcentaje imposible no se corrige silenciosamente: se rechaza. Un
    descuento inventado se aplica de verdad sobre el precio que ve el usuario.
    """
    scraper = CotoScraper(client=_cliente(_handler_json(_respuesta_coto([
        _promo_coto(id="1", textoDescuento="150% DE DESCUENTO"),
        _promo_coto(id="2"),
    ]))))
    descuentos = scraper.scrape()
    assert [d.promo_id for d in descuentos] == ["coto_2"]


@pytest.mark.parametrize("campo, valor", [
    ("store", "jumbo_online"),
    ("porcentaje_descuento", 0),
    ("porcentaje_descuento", 101),
    ("dias_validos", ()),
    ("dias_validos", ("lunes", "feriado")),
    ("tope_reintegro", -5),
    ("tope_periodo", "quincenal"),
])
def test_el_modelo_valida_al_construir(campo, valor):
    campos = {
        "store": "coto_online", "entidad": "galicia", "porcentaje_descuento": 20.0,
        "dias_validos": ("lunes",), "tope_reintegro": 5000, "tope_periodo": "transaccion",
        "descripcion": "", "promo_id": "x", "texto_legal": "", "scraped_at": "",
    }
    campos[campo] = valor
    with pytest.raises(InvalidDiscount):
        BankDiscount(**campos)


def test_roundtrip_json():
    """El archivo es el único transporte entre el scraper y el optimizador."""
    original = CotoScraper()._to_discount(_promo_coto())
    assert BankDiscount.from_json_dict(original.to_json_dict()) == original
