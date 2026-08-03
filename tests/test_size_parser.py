# tests/test_size_parser.py
import pytest

from src.size_parser import extract_pack_count, extract_real_volume, normalize_magnitude


def test_extract_ml():
    weight, unit = extract_real_volume("Aceite Fritolim Clásico Cocinero 120 Ml.")
    assert weight == 120.0
    assert unit == "ml"


def test_extract_grams():
    weight, unit = extract_real_volume("Dulce De Leche MILKAUT Clásico 400g")
    assert weight == 400.0
    assert unit == "g"


def test_extract_kg_normalizes_to_grams():
    weight, unit = extract_real_volume("Harina para Pizza Pureza con Levadura 1 Kg.")
    assert weight == 1000.0
    assert unit == "g"


def test_extract_liters_normalizes_to_ml():
    weight, unit = extract_real_volume("Leche Larga Vida Entera CIUDAD DEL LAGO Ttb 1 L")
    assert weight == 1000.0
    assert unit == "ml"


def test_extract_lt_abbreviation_used_by_carrefour():
    weight, unit = extract_real_volume("Aceite de girasol alto omega Carrefour Classic 1.5 lt.")
    assert weight == 1500.0
    assert unit == "ml"


def test_no_size_in_name_falls_back_to_un():
    weight, unit = extract_real_volume("Polenta Molinos Ala")
    assert weight == 1.0
    assert unit == "un"


def test_empty_name():
    weight, unit = extract_real_volume("")
    assert weight == 1.0
    assert unit == "un"


# "grs" aparecía 64 veces en el catálogo y "lts" 4, y las dos caían al genérico
# (1.0, 'un'): el \b después de "gr" chocaba contra la "s".
@pytest.mark.parametrize("name, esperado", [
    ("Aceite de coco prensado en frio Sri Sri 300 grs", (300.0, "g")),
    ("Alfajor Chocolinas chocotorta 71.5 grs", (71.5, "g")),
    ("Aceite mezcla Carrefour Classic 2 lts", (2000.0, "ml")),
    ("Aceite de girasol alto omega Carrefour Classic pet 1.5 lts", (1500.0, "ml")),
])
def test_sufijos_en_plural(name, esperado):
    assert extract_real_volume(name) == esperado


def test_el_tamano_del_pack_no_se_multiplica():
    """
    El número que figura al lado del "xN" tanto puede ser el total del pack como
    el de cada unidad, y nada en el nombre los distingue. Se devuelve tal cual;
    ver el docstring de extract_pack_count.
    """
    assert extract_real_volume("Alfajor Blanco Con Dulce De Leche X6 ALFA PAMPA 360g") == (360.0, "g")
    assert extract_real_volume("Alfajor de chocolate negro Entre Dos x6 45 g.") == (45.0, "g")


@pytest.mark.parametrize("name, esperado", [
    # Las tres formas que usa el catálogo.
    ("Alfajor Carrefour extra de chocolate negro x6 60 g.", 6),
    ("Alfajor chocolate triple Vimar 60 g. x 3 uni", 3),
    ("Alfajor Happy food coco y dulce de leche sin azúcar 3x 50 g.", 3),
    ("Alfajor Cachafaz chocolate blanco 6 u.", 6),
    ("Mini Alfajores MILKA Mousse 19g X 6 Unidades", 6),
    ("Alfajor De Maizena CACHAFAZ 6u", 6),
    ("Mini Alfajor Chocolate X10 Uni Alfa Pampa Cja 320 Grm", 10),
    # Sin marca de pack.
    ("Dulce De Leche MILKAUT Clásico 400g", 1),
    ("", 1),
])
def test_extract_pack_count(name, esperado):
    assert extract_pack_count(name) == esperado


@pytest.mark.parametrize("name", [
    # Sin el lookahead negativo estos devolvían packs de 800 y de 1500.
    "Leche modificada en polvo armonia bolsa x 800 grs",
    "Harina leudante Caserita x 1 kg",
    "Aceite de girasol Pureza x 1500 cc.",
])
def test_un_tamano_precedido_de_x_no_es_un_pack(name):
    """Un número seguido de una unidad de magnitud es un tamaño, no una cantidad."""
    assert extract_pack_count(name) == 1


# --- normalize_magnitude: vocabulario canónico g / ml / un -------------------

@pytest.mark.parametrize("value, unit, esperado", [
    # Lo que producía el fallback de Coto: 'kg' sin convertir.
    (1.5, "kg", (1500.0, "g")),
    (1.0, "Kg.", (1000.0, "g")),
    (2.0, "kilos", (2000.0, "g")),
    # Etiquetas crudas de la property "UnidaddeMedida" de VTEX.
    (200.0, "gr", (200.0, "g")),
    (400.0, "GRS", (400.0, "g")),
    (1.5, "lt", (1500.0, "ml")),
    (2.0, "litros", (2000.0, "ml")),
    (500.0, "cc", (500.0, "ml")),
    # Ya canónicas: idempotente.
    (750.0, "g", (750.0, "g")),
    (330.0, "ml", (330.0, "ml")),
])
def test_normalize_magnitude(value, unit, esperado):
    assert normalize_magnitude(value, unit) == esperado


@pytest.mark.parametrize("unit", ["un", "unidad", "", None, "bandeja", "paquete"])
def test_normalize_magnitude_unidad_desconocida_es_sin_tamano(unit):
    """
    Inventar una equivalencia sería peor que admitir que no se sabe: se devuelve
    el mismo (1.0, 'un') que usa extract_real_volume cuando no encuentra talla.
    """
    assert normalize_magnitude(7.0, unit) == (1.0, "un")


def test_normalize_magnitude_es_idempotente():
    """Se aplica después de las ramas que ya convirtieron a g/ml; no debe re-escalar."""
    once = normalize_magnitude(1.5, "kg")
    assert normalize_magnitude(*once) == once


def test_todo_sufijo_del_regex_lo_entiende_normalize_magnitude():
    """
    `extract_real_volume` delega la conversión en `normalize_magnitude`, así que
    un sufijo agregado al regex pero no a los sets se traduciría en silencio a
    (1.0, 'un') — el producto quedaría sin tamaño sin que nada falle. Este test
    es el que ata las dos listas.
    """
    from src.size_parser import _UNIT_SUFFIXES

    for suffix in _UNIT_SUFFIXES.split("|"):
        valor, unidad = normalize_magnitude(2.0, suffix)
        assert unidad in ("g", "ml"), f"el regex acepta {suffix!r} pero normalize_magnitude no"
        assert valor in (2.0, 2000.0)
