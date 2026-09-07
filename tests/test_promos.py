# tests/test_promos.py
from src.promotion_parser import PromoTransformer

def test_coto_transformer():
    # Ejemplo: Descuento directo de Coto
    coto_raw_direct = [{
        "id": "36294792",
        "takingText": None,
        "discountText": "25%Dto",
        "discountPrice": "$2248.95",
        "regularPriceText": "Precio Contado: $2999"
    }]
    
    parsed_direct = PromoTransformer.coto(coto_raw_direct)
    assert len(parsed_direct) == 1
    assert parsed_direct[0]["type"] == "direct_discount"
    assert parsed_direct[0]["discount_price_per_unit"] == 2248.95


def test_dia_transformer():
    # Ejemplo: Promo 3x2 en Día
    dia_raw_offer_teaser = {
        "ListPrice": 1500.0,
        "Price": 1500.0,
        "AvailableQuantity": 10,
        "teasers": [{
            "name": "3x2 ",
            "conditions": {"minimumQuantity": 3},
            "effects": {}
        }]
    }
    
    base_price, parsed_teaser = PromoTransformer.dia(dia_raw_offer_teaser, "311925")
    assert base_price == 1500.0
    assert len(parsed_teaser) == 1
    assert parsed_teaser[0]["type"] == "multi_buy"

# --- Paridad entre banks.py y el selector del frontend ----------------------
#
# `optimize_cart` compara `promo["card"] in user_cards` por IGUALDAD EXACTA, así
# que una entidad que el scraper emite pero la UI no ofrece se scrapea todas las
# noches y ningún usuario puede activarla nunca: descuento real, invisible, sin
# que falle nada. El comentario de ProfileDrawer.jsx ya advertía la regla; esto
# la vuelve verificable. Así se encontraron Provincia, HSBC, Itaú e Hipotecario.


def _opciones_del_frontend(nombre_const):
    """Los `{value, label}` de una constante de ProfileDrawer.jsx."""
    import pathlib
    import re

    ruta = pathlib.Path(__file__).parent.parent / "frontend/src/components/profile/ProfileDrawer.jsx"
    fuente = ruta.read_text(encoding="utf-8")
    inicio = fuente.index(f"const {nombre_const} = [")
    bloque = fuente[inicio:fuente.index("];", inicio)]
    return [
        (m.group(1), m.group(2))
        for m in re.finditer(r'\{ value: "([^"]+)", label: "([^"]+)" \}', bloque)
    ]


def test_todo_slug_del_frontend_existe_en_banks():
    from src.promotions.banks import BANK_ALIASES

    emitibles = set(BANK_ALIASES.values())
    opciones = _opciones_del_frontend("CARD_OPTIONS") + _opciones_del_frontend("MEMBERSHIP_OPTIONS")

    desconocidos = [value for value, _ in opciones if value not in emitibles]
    assert not desconocidos, f"La UI ofrece entidades que el scraper no emite: {desconocidos}"


def test_toda_entidad_scrapeable_se_puede_activar():
    from src.promotions.banks import BANK_ALIASES

    opciones = _opciones_del_frontend("CARD_OPTIONS") + _opciones_del_frontend("MEMBERSHIP_OPTIONS")
    ofrecidos = {value for value, _ in opciones}

    faltantes = sorted(set(BANK_ALIASES.values()) - ofrecidos)
    assert not faltantes, f"El scraper emite entidades que nadie puede activar: {faltantes}"


def test_membresias_y_tarjetas_no_se_mezclan():
    """
    Las membresías viajan en `user_memberships` y las tarjetas en `user_cards`.
    Una membresía ofrecida en la lista equivocada no se activa nunca.
    """
    from src.promotions.banks import MEMBERSHIP_ENTITIES

    tarjetas = {value for value, _ in _opciones_del_frontend("CARD_OPTIONS")}
    membresias = {value for value, _ in _opciones_del_frontend("MEMBERSHIP_OPTIONS")}

    assert not (tarjetas & set(MEMBERSHIP_ENTITIES))
    assert membresias == set(MEMBERSHIP_ENTITIES)


def test_las_etiquetas_coinciden_con_las_del_backend():
    """
    El backend escribe el nombre de la entidad en la descripción de la promo
    ("21% Off con Mi Carrefour"). Si la UI lo escribiera distinto, el usuario
    vería dos nombres para lo mismo en la misma pantalla.
    """
    from src.promotions.banks import display_name

    opciones = _opciones_del_frontend("CARD_OPTIONS") + _opciones_del_frontend("MEMBERSHIP_OPTIONS")
    distintos = [(v, l, display_name(v)) for v, l in opciones if display_name(v) != l]
    assert not distintos, f"Etiquetas desalineadas: {distintos}"
