"""
Tests de src/meat_cuts.py: el tipo de corte de un producto de la góndola de
carnes, leído de su nombre. Suite pura; los nombres son reales (nov 2026).
"""
import pytest

from src.meat_cuts import product_type


@pytest.mark.parametrize("nombre, corte", [
    ("Vacío Envasado al Vacío x Kg.", "Vacío"),
    ("Asado de Novillito Envasado al Vacío x 1 Kg.", "Asado"),
    ("Matambre De Cerdo (peso Mínimo De La Unidad 810g) X KG", "Matambre de cerdo"),
    ("Carne Picada de Nalga x 500 Gr.", "Carne picada"),
    ("Milanesa de nalga x kg", "Milanesa"),
    ("Ojo de Bife de Novillito Envasado al Vacío x 1 Kg.", "Bife ancho"),
    ("Colita De Cuadril (peso Aproximado De La Unidad 930g) X KG", "Colita de cuadril"),
    ("Lomo de Novillito Envasado al Vacío x 1 Kg.", "Lomo"),
])
def test_el_corte_sale_del_nombre(nombre, corte):
    assert product_type("carnes", nombre) == corte


@pytest.mark.parametrize("nombre, corte", [
    # "asado" y "bife" están adentro de cortes más específicos
    ("Tapa De Asado Ahumada Y Condimentada Las Dinas X 1kg", "Tapa de asado"),
    ("Bife de chorizo Huella Natural trozado x kg.", "Bife de chorizo"),
    ("Bife De Chorizo Churrasco Novillito", "Bife de chorizo"),
])
def test_gana_el_corte_mas_especifico(nombre, corte):
    assert product_type("carnes", nombre) == corte


def test_un_nombre_sin_corte_conocido_va_a_otros():
    assert product_type("carnes", "Pack parrillero Etiqueta Negra x kg") == "Otros"


def test_fuera_de_carnes_no_hay_tipo():
    assert product_type("yerba-mate", "Yerba Mate Suave 1 Kg Playadito") is None
