"""
Tests de src/search_intent.py: qué góndola y qué tipo nombra el texto de una
búsqueda. Suite pura.

Tres resultados posibles:
- `listing`: todas las palabras son de la góndola o de sus tipos ("vino tinto"):
  se muestra la góndola entera con el filtro.
- `within`: la búsqueda empieza por la góndola y sigue con otras palabras
  ("vino reserva"): búsqueda semántica dentro de la góndola.
- None: no nombra ninguna góndola al principio ("vinagre de vino"): la búsqueda
  de siempre.
"""
from src.search_intent import read_intent


def test_vino_tinto_es_la_gondola_vinos_con_el_filtro_tinto():
    # ejecutar
    intent = read_intent("vino tinto")

    # verificar
    assert intent.shelf == "vinos"
    assert intent.types == ["Tinto"]
    assert intent.mode == "listing"


def test_tinto_vino_es_lo_mismo_que_vino_tinto():
    intent = read_intent("tinto vino")

    assert (intent.shelf, intent.types, intent.mode) == ("vinos", ["Tinto"], "listing")


def test_vinos_tintos_en_plural_y_con_mayusculas_tambien():
    intent = read_intent("Vinos Tintos")

    assert (intent.shelf, intent.types, intent.mode) == ("vinos", ["Tinto"], "listing")


def test_solo_el_nombre_de_la_gondola_es_la_gondola_entera():
    intent = read_intent("vinos")

    assert (intent.shelf, intent.types, intent.mode) == ("vinos", [], "listing")


def test_vino_con_una_palabra_desconocida_busca_dentro_de_vinos_sin_filtro():
    intent = read_intent("vino reserva")

    assert (intent.shelf, intent.types, intent.mode) == ("vinos", [], "within")


def test_vinagre_de_vino_no_es_la_gondola_vinos():
    # "vino" aparece, pero lo que se busca es vinagre: manda la primera palabra,
    # que es de aceites y aderezos.
    intent = read_intent("vinagre de vino")

    assert (intent.shelf, intent.types, intent.mode) == ("aceites-y-aderezos", ["Vinagre"], "within")


def test_una_palabra_que_es_gondola_y_tipo_aplica_el_filtro():
    intent = read_intent("jamon crudo")

    assert (intent.shelf, intent.types, intent.mode) == ("fiambres", ["Jamón crudo"], "listing")


def test_dulce_de_leche_es_su_gondola_y_no_leches():
    # gana la frase más larga
    intent = read_intent("dulce de leche")

    assert (intent.shelf, intent.mode) == ("dulce-de-leche", "listing")


def test_el_tipo_puede_incluir_la_palabra_de_la_gondola():
    # "aceite" es la góndola y también el tipo Aceite, pero "aceite de oliva" es
    # otro tipo: gana la frase más larga.
    assert read_intent("aceite de oliva").types == ["Aceite de oliva"]
    assert read_intent("te verde").types == ["Té verde"]


def test_un_texto_sin_gondola_no_detecta_nada():
    assert read_intent("coca cola") is None
