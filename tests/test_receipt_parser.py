# tests/test_receipt_parser.py
"""
Suite pura (sin Postgres, sin Tesseract) de `clean_line_for_matching()`.

Fixtures con texto acentuado y ruido real de impresora térmica a propósito:
`test_coto_url.py` tuvo fixtures puramente ASCII durante mucho tiempo, y eso
fue exactamente lo que dejó pasar el bug de `_slugify()` con un "%" real (ver
CLAUDE.md etapa 1). El texto de OCR sobre tickets argentinos es la superficie
más nueva del proyecto en este sentido, así que arranca con acentos y ruido en
vez de esperar a que un ticket real lo revele.

Las fixtures de cabecera/pie/cantidad-separada salen de una Factura B real
(docs/references/ticket_dia.png), no inventadas: la primera versión de este
módulo asumía "cantidad nombre precio" en una sola línea, y esa foto mostró que
DIA separa la cantidad/precio-unitario del nombre en dos líneas distintas, con
el nombre terminando en un "(%IVA)" pegado al importe.
"""
from src.receipt_parser import clean_line_for_matching


def test_saca_el_precio_final():
    assert clean_line_for_matching("GALLETITAS OREO 118G        450.00") == "GALLETITAS OREO 118G"


def test_saca_el_precio_con_miles_y_coma_decimal():
    assert clean_line_for_matching("ACEITE NATURA 900ML       1.250,00") == "ACEITE NATURA 900ML"


def test_saca_el_codigo_de_barras_inicial():
    assert (
        clean_line_for_matching("7790040123456 LECHE LA SERENISIMA 1L   890,50")
        == "LECHE LA SERENISIMA 1L"
    )


def test_saca_la_cantidad_inicial():
    assert clean_line_for_matching("2 GALLETITAS OREO 118G   450.00") == "GALLETITAS OREO 118G"


def test_saca_la_cantidad_inicial_con_x():
    assert clean_line_for_matching("2x CERVEZA QUILMES 1L   899.99") == "CERVEZA QUILMES 1L"


def test_colapsa_puntos_de_relleno():
    assert (
        clean_line_for_matching("ACEITE NATURA 900ML .......... 1.250,00")
        == "ACEITE NATURA 900ML"
    )


def test_preserva_acentos_y_enie():
    assert clean_line_for_matching("2 YOGURISIMO GRIEGO FRUTILLA 140G  380,00") == \
        "YOGURISIMO GRIEGO FRUTILLA 140G"
    assert clean_line_for_matching("DULCE DE LECHE SER 400G   520,00") == "DULCE DE LECHE SER 400G"
    assert clean_line_for_matching("2 MAÑANITA GALLETITAS 170G  310,00") == "MAÑANITA GALLETITAS 170G"


def test_preserva_porcentaje_y_barra():
    assert clean_line_for_matching("LECHE LA SERENISIMA 0% 1L   450,00") == "LECHE LA SERENISIMA 0% 1L"
    assert clean_line_for_matching("QUESO CREMOSO 1/4 KG   680,00") == "QUESO CREMOSO 1/4 KG"


def test_linea_sin_precio_se_descarta_entera():
    # Antes esto sobrevivía tal cual ("FIDEOS MATARAZZO"). Cambió a propósito:
    # una línea sin importe no es una fila de producto (ver el docstring de
    # _PRECIO_FINAL) -- es exactamente la forma de la cabecera/pie de una
    # Factura B real, que no debe llegar a la búsqueda semántica.
    assert clean_line_for_matching("  FIDEOS MATARAZZO  ") == ""


def test_linea_vacia_da_vacio():
    assert clean_line_for_matching("   ") == ""


def test_saca_el_iva_entre_parentesis():
    # El punto de "BCA.MALLA" lo saca `_RUIDO`, no `_IVA_ENTRE_PARENTESIS` --
    # ese comportamiento (sin puntuación en el texto a embeber) ya existía y
    # no es parte de este cambio.
    assert (
        clean_line_for_matching("ATUN LOM N DIA 354GR (21,00) 19960,00")
        == "ATUN LOM N DIA 354GR"
    )
    assert clean_line_for_matching("PAPA BCA.MALLA (10,50) 7521,15") == "PAPA BCA MALLA"


def test_preserva_parentesis_con_texto_real():
    # Sólo se saca el paréntesis de %IVA (un número adentro): un paréntesis
    # con texto real adentro no lo toca `_IVA_ENTRE_PARENTESIS`. Los propios
    # paréntesis después los saca `_RUIDO` igual que cualquier otra puntuación
    # -- lo que importa acá es que "SABOR ORIGINAL" sobrevive como palabras.
    assert (
        clean_line_for_matching("GASEOSA COCA COLA (SABOR ORIGINAL) 2.25L   1.200,00")
        == "GASEOSA COCA COLA SABOR ORIGINAL 2 25L"
    )


def test_basura_de_ocr_despues_del_precio_no_pierde_la_linea():
    # Casos reales de docs/references/ticket_dia.png, con basura de OCR
    # (manchas, reflejos) después del importe. La primera versión exigía el
    # precio pegado al final de la línea y perdía estas tres enteras.
    assert (
        clean_line_for_matching("ALFAJOR DE MAICENA — (21,00)  3990,00 je")
        == "ALFAJOR DE MAICENA"
    )
    assert (
        clean_line_for_matching("CEBOLLA GRANEL ELÉGI (10,50)  4157,10 27")
        == "CEBOLLA GRANEL ELÉGI"
    )
    assert (
        clean_line_for_matching("CREMA DE LECHE P/COC (21,00) 9740,00 MEN : :")
        == "CREMA DE LECHE P/COC"
    )


def test_codigo_de_barras_mal_leido_con_letras_sueltas_no_matchea_nada():
    # "B4g0017a51250 e" (código de barras real, mal leído): tiene letras, pero
    # sueltas entre dígitos -- no una palabra. `_TIENE_PALABRA` exige 3
    # seguidas, no sólo una letra en algún lado.
    assert clean_line_for_matching("3 B4g0017a51250 e (21,00)  19960,00") == ""


def test_cabecera_de_factura_no_matchea_nada():
    # Líneas reales de docs/references/ticket_dia.png: ninguna termina en un
    # importe, así que ninguna debe generar un candidato para buscar.
    assert clean_line_for_matching("DIA ARGENTINA SA") == ""
    assert clean_line_for_matching("CUIT:30-68584975-1") == ""
    assert clean_line_for_matching("CAPITAL FEDERAL") == ""
    assert clean_line_for_matching("IVA RESPONSABLE INSCRIPTO") == ""
    assert clean_line_for_matching("FACTURA B ORIGINAL (COD. 006)") == ""
    assert clean_line_for_matching("TDA:01097 CAJA:02 NTrx:010970200842143") == ""
    assert clean_line_for_matching("Cant./Precio Unit.") == ""
    assert clean_line_for_matching("Descripcion (%IVA) [%BI] IMPORTE") == ""


def test_codigo_de_barras_solo_no_matchea_nada():
    assert clean_line_for_matching("8480017451255") == ""


def test_linea_de_cantidad_separada_del_nombre_no_matchea_nada():
    # El formato real de DIA: "4,00 X 4990,00" en su propia línea, sin nombre
    # (el nombre viene en la línea siguiente). Sin este caso cubierto, "4,00 X"
    # sobrevivía como si fuera un producto de una letra.
    assert clean_line_for_matching("4,00 X 4990,00") == ""
    assert clean_line_for_matching("1,00 X 3990,00") == ""


def test_linea_de_peso_no_matchea_nada():
    # Continuación de un producto pesado ("90090 1,8850 Kg"): no termina en un
    # importe con dos decimales, así que no es una fila de producto.
    assert clean_line_for_matching("90090 1,8850 Kg") == ""


def test_lineas_de_resumen_fiscal_sobreviven_como_ruido_conocido():
    # "SUBTOTAL:", "TOTAL", "IVA CONTENIDO" también terminan en un importe con
    # forma válida (Factura B real), así que la regla de "termina en precio"
    # no las saca -- quedan como candidatos y las descarta la pantalla de
    # revisión, no esta función. Documentado en vez de "arreglado" a propósito:
    # una lista de frases a excluir por cadena es la clase de heurística
    # frágil que el proyecto evita (ver CLAUDE.md etapa 4, discusión del 0.90).
    assert clean_line_for_matching("SUBTOTAL:              63991,05") == "SUBTOTAL"
    assert clean_line_for_matching("TOTAL              $ 63991.05") == "TOTAL"
