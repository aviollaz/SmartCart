from src.dietary_parser import detect_dietary_flags


def test_sin_tacc_en_el_nombre():
    gluten_free, _ = detect_dietary_flags("Mostaza Menoyo sin tacc 60 Gr.")
    assert gluten_free is True


def test_libre_de_gluten():
    gluten_free, _ = detect_dietary_flags("Salsa de Soja Libre de Gluten Dos Anclas 500 Ml.")
    assert gluten_free is True


def test_sin_tacc_con_puntos_y_mayusculas():
    gluten_free, _ = detect_dietary_flags("Galletitas SIN T.A.C.C. Smams 200 Gr")
    assert gluten_free is True


def test_vegano():
    _, vegan = detect_dietary_flags("Hamburguesa Vegana NotCo 226 Gr")
    assert vegan is True


def test_plant_based_con_y_sin_guion():
    assert detect_dietary_flags("Milanesa Plant Based")[1] is True
    assert detect_dietary_flags("Milanesa plant-based")[1] is True


def test_evidencia_desde_multiples_campos():
    """Los scrapers pasan nombre, marca, ruta de categoría y properties."""
    gluten_free, _ = detect_dietary_flags(
        "Fideos Tirabuzon", "Marca X", ["almacen", "pastas"], ["Sin TACC"]
    )
    assert gluten_free is True


def test_contiene_gluten_no_es_falso_positivo():
    """El token suelto 'gluten' no debe marcar el producto como apto."""
    gluten_free, _ = detect_dietary_flags("Pan de Molde - contiene gluten")
    assert gluten_free is False


def test_vegetales_no_es_vegano():
    """'vegetal' suelto está excluido a propósito: daría falsos positivos."""
    _, vegan = detect_dietary_flags("Semola Vegetales Vitina Luchetti 250g")
    assert vegan is False


def test_copy_de_marca_que_enumera_productos_hermanos():
    """
    Regresión de un falso positivo real: la descripción del Ketchup Hellmann's
    lista toda la línea de la marca, incluida la mayonesa vegana, y el ketchup
    quedaba marcado como vegano.

    Ninguna regla de frases evita esto (el reclamo es legítimo, pero es sobre
    otro producto), así que la defensa es no pasarle descripciones de marketing
    a detect_dietary_flags. Este test fija el contrato: si alguien vuelve a
    sumar `description` como fuente en los scrapers, falla acá.
    """
    descripcion_de_marca = (
        "En Hellmann's estamos a favor de la buena comida. Conocé nuestros "
        "productos disponibles: mayonesa Hellmann's light, clásica, suave, "
        "vegana, oliva, salsa golf y nuestros riquísimos aderezos."
    )
    _, vegan = detect_dietary_flags("Ketchup Hellmanns Regular Doypack 500 Gr.", "Hellmanns")
    assert vegan is False

    # La frase sí contiene el término: el punto es que esa fuente no se usa.
    _, vegan_si_se_usara = detect_dietary_flags(descripcion_de_marca)
    assert vegan_si_se_usara is True


def test_property_estructurada_de_la_tienda():
    """De acá sale ~92% de la señal real: la property "Otros" de VTEX."""
    gluten_free, _ = detect_dietary_flags(
        "Ketchup Hellmanns Regular Doypack 250 Gr.", "Hellmanns", [["21"], ["1 Kg"], ["Sin Tacc"]]
    )
    assert gluten_free is True


def test_no_apto_invalida_la_evidencia():
    gluten_free, vegan = detect_dietary_flags("No apto para veganos ni sin tacc")
    assert gluten_free is False
    assert vegan is False


def test_sin_evidencia_devuelve_false():
    assert detect_dietary_flags("Aceite de Girasol Natura 1,5 Lt.") == (False, False)


def test_entrada_vacia_o_none():
    assert detect_dietary_flags() == (False, False)
    assert detect_dietary_flags(None, "", []) == (False, False)
