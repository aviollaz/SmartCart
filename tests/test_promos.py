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