# tests/test_size_parser.py
from src.size_parser import extract_real_volume


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
