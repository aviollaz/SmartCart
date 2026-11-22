"""
Tests de src/shelf_types.py: el filtro "Tipo" de una góndola, leído del nombre
del producto. Suite pura; los nombres son reales (nov 2026).
"""
import pytest

from src.shelf_types import product_type, type_label


@pytest.mark.parametrize("nombre, tipo", [
    ("Vino Tinto Malbec Trapiche 750 Ml", "Tinto"),
    ("Vino Cab.Sauv Reserve Los Helecho Bot 750 Ml", "Tinto"),
    ("Vino Blanco Chardonnay Alamos 750cc", "Blanco"),
    ("Vino Rosado Dulce Termidor 1 Lt", "Rosado"),
])
def test_el_color_del_vino_sale_del_nombre(nombre, tipo):
    assert product_type("vinos", nombre) == tipo


def test_un_malbec_rose_es_rosado_y_no_tinto():
    # preparar / ejecutar / verificar: lo específico gana sobre el varietal
    assert product_type("vinos", "Vino Malbec Rosé Santa Julia 750 Ml") == "Rosado"


def test_un_vino_sin_color_reconocible_va_a_otros():
    assert product_type("vinos", "Vino Dada Art 9 Caramel 750cc") == "Otros"


def test_carnes_sigue_leyendo_el_corte():
    assert product_type("carnes", "Milanesa de nalga x kg") == "Milanesa"


def test_una_gondola_sin_tabla_no_tiene_tipo():
    assert product_type("huevos", "Huevos Blancos x 12") is None
    assert type_label("huevos") is None


def test_cada_gondola_con_tabla_nombra_su_filtro():
    assert type_label("carnes") == "Tipo de corte"
    assert type_label("vinos") == "Tipo"


@pytest.mark.parametrize("gondola, nombre, tipo", [
    ("galletitas", "Galletitas Crackers Express 101 Gr", "Saladas"),
    ("galletitas", "Galletitas Dulces Rellenas Oreo 118 Gr", "Dulces"),
    ("galletitas", "Galletas De Arroz Gallo Snacks Sabor Queso 100 Gr", "De arroz"),
    ("aceites-y-aderezos", "Aceite De Girasol Natura 1,5 Lt", "Aceite"),
    ("aceites-y-aderezos", "Mayonesa Hellmann's Clásica 475 Gr", "Mayonesa"),
    ("aceites-y-aderezos", "Vinagre De Alcohol Menoyo 500 Ml", "Vinagre"),
    ("fiambres", "Jamon Cocido Paladini Feteado 200 Gr", "Jamón cocido"),
    ("fiambres", "Salame Milan Cagnoli x 100 Gr", "Salame"),
    ("cafe", "Café Molido La Virginia Clásico 500 Gr", "Molido"),
    ("cafe", "Cápsulas De Café Nescafé Dolce Gusto Cortado", "En cápsulas"),
])
def test_las_gondolas_grandes_tambien_tienen_tipo(gondola, nombre, tipo):
    assert product_type(gondola, nombre) == tipo
