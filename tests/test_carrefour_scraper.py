# tests/test_carrefour_scraper.py
"""
Suite pura (sin Postgres ni sentence-transformers) del scraper de Carrefour.

Los fixtures son inline y recortados a mano a partir de respuestas reales de
`productSearchV3`: se conservan sólo los campos que el parser lee.
"""
import pytest

from src.flattener import evaluate_best_promo
from src.promotion_parser import PromoTransformer
from src.scrapers.errors import CategoryScrapeError
from src.scrapers.vtex import read_availability
from src.scrapers.scraper_carrefour import CarrefourScraper, build_carrefour_url
from src.scrapers.vtex import extract_search_payload


def _producto_vtex(**overrides):
    producto = {
        "productId": "680457",
        "productName": "Aceite de girasol alto omega Carrefour Classic 1.5 lt.",
        "brand": "Carrefour Classic",
        # VTEX manda el link RELATIVO, sin dominio.
        "link": "/aceite-de-girasol-alto-omega-carrefour-classic-pet-1-5-lts-680457/p",
        "categories": ["/Almacén/Aceites y vinagres/Aceites comunes/", "/Almacén/"],
        "properties": [],
        "clusterHighlights": [],
        "items": [{
            "ean": "7791720025123",
            "images": [{"imageUrl": "https://carrefourar.vtexassets.com/ids/680457/aceite.jpg"}],
            "sellers": [{
                "commertialOffer": {
                    "ListPrice": 5750.0,
                    "Price": 5750.0,
                    "teasers": [],
                    "discountHighlights": [],
                }
            }],
        }],
    }
    producto.update(overrides)
    return producto


def _respuesta(products):
    return {"data": {"productSearch": {"recordsFiltered": len(products), "products": products}}}


def test_payload_deriva_el_map_de_la_cantidad_de_segmentos():
    # Un "c" por facet: las categorías MVP tienen dos y tres niveles, y mandar
    # menos "c" que selectedFacets desalinea el contrato de VTEX.
    dos = CarrefourScraper._build_payload("almacen/aceites-y-vinagres", 0, 15)["variables"]
    assert dos["map"] == "c,c"
    assert dos["selectedFacets"] == [
        {"key": "c", "value": "almacen"},
        {"key": "c", "value": "aceites-y-vinagres"},
    ]

    tres = CarrefourScraper._build_payload(
        "desayuno-y-merienda/golosinas-y-chocolates/alfajores", 16, 31
    )["variables"]
    assert tres["map"] == "c,c,c"
    assert len(tres["selectedFacets"]) == 3
    assert (tres["from"], tres["to"]) == (16, 31)


def test_url_absoluta():
    assert build_carrefour_url("/aceite-123/p") == "https://www.carrefour.com.ar/aceite-123/p"
    # Idempotente si algún día VTEX empezara a mandarla completa.
    assert build_carrefour_url("https://www.carrefour.com.ar/x/p") == "https://www.carrefour.com.ar/x/p"
    assert build_carrefour_url(None) is None


def test_process_products_extrae_los_campos_del_producto():
    scraper = CarrefourScraper()

    parsed = scraper.process_products(
        _respuesta([_producto_vtex()]),
        "aceites-y-aderezos",
        "Almacén -> Aceites y vinagres",
        "almacen/aceites-y-vinagres",
    )

    assert len(parsed) == 1
    p = parsed[0]
    assert p["store_sku"] == "680457"
    assert p["ean"] == "7791720025123"
    assert p["base_price"] == 5750.0
    assert p["url"].startswith("https://www.carrefour.com.ar/")
    assert p["image_url"].endswith("aceite.jpg")
    # La góndola canónica, no la hoja de la taxonomía de Carrefour: es el mismo
    # slug que escriben Coto y Día para el mismo estante.
    assert p["shelf"] == "aceites-y-aderezos"
    assert p["source_category"] == "almacen/aceites-y-vinagres"
    # Tamaño parseado del nombre, no de la property.
    assert (p["total_volume_weight"], p["unit_type"]) == (1500.0, "ml")


def test_errores_de_graphql_no_se_confunden_con_categoria_vacia():
    # La persisted query vencida contesta HTTP 200 con `errors` y sin `data`. Si
    # eso se leyera como "no hay más productos", el scrapeo cerraría en silencio
    # con 0 filas y sin un solo error visible.
    #
    # Antes esto devolvía None y una lista vacía, que es exactamente el contrato
    # equivocado: detectar el problema y después seguir con un `break` silencioso
    # deja la categoría corta y reportada OK, y habilita el pruning a borrar todo
    # lo que el barrido no alcanzó. Ahora levanta y `_run_store` la marca fallida.
    respuesta_rota = {
        "errors": [{"message": "PersistedQueryNotFound", "extensions": {"code": "PERSISTED_QUERY_NOT_FOUND"}}]
    }
    scraper = CarrefourScraper()

    with pytest.raises(CategoryScrapeError, match="PersistedQueryNotFound"):
        extract_search_payload(respuesta_rota, "CARREFOUR")
    with pytest.raises(CategoryScrapeError):
        scraper.process_products(respuesta_rota)

    # Una categoría realmente agotada sí es un payload válido con 0 productos, y
    # ese es el único final que NO es un error.
    vacia = _respuesta([])
    assert extract_search_payload(vacia, "CARREFOUR") == {"recordsFiltered": 0, "products": []}
    assert scraper.process_products(vacia) == []


def test_precio_de_socio_queda_condicionado_a_la_membresia():
    # "Doble Precio" de Mi Carrefour: el hueco ListPrice/Price NO está abierto
    # a cualquiera, así que el descuento tiene que exigir la membresía.
    oferta = {
        "ListPrice": 5750.0,
        "Price": 5405.0,
        "teasers": [{"name": "Tarjeta Carrefour 15%"}],
        "discountHighlights": [{"name": "PROMO-Mi CRF -mfl-1-6-Dto de 6% Doble Precio"}],
    }

    base_price, promos = PromoTransformer.carrefour(oferta, "680457")

    assert base_price == 5750.0
    directo = next(p for p in promos if p["type"] == "direct_discount")
    assert directo["promo_id"] == "carrefour_direct_680457"
    assert directo["requires_membership"] == "mi_carrefour"

    # Sin la membresía declarada, se cotiza el precio de lista.
    sin_socio = evaluate_best_promo(base_price, promos, 1, user_memberships=[])
    assert sin_socio["total_cost"] == 5750.0
    assert sin_socio["applied_promo_id"] is None

    # Declarándola, se desbloquea.
    con_socio = evaluate_best_promo(base_price, promos, 1, user_memberships=["mi_carrefour"])
    assert con_socio["total_cost"] == 5405.0


def test_descuento_general_de_carrefour_es_incondicional():
    # Sin mención a tarjeta ni a fidelidad, el descuento rige para cualquiera.
    oferta = {
        "ListPrice": 6165.0,
        "Price": 4007.25,
        "teasers": [],
        "discountHighlights": [{"name": "PROMO-35% Off Max 24 unidades -Reg-1-35-Gigante"}],
    }

    _, promos = PromoTransformer.carrefour(oferta, "999")

    directo = next(p for p in promos if p["type"] == "direct_discount")
    assert directo["requires_membership"] is None
    assert evaluate_best_promo(6165.0, promos, 1)["total_cost"] == 4007.25


def test_teaser_de_segunda_unidad_de_carrefour():
    # Redacción real de Carrefour, más larga que la de Día pero con el mismo
    # "2do al 50" adentro.
    oferta = {
        "ListPrice": 2986.67,
        "Price": 2986.67,
        "teasers": [{"name": "PROMO-2do al 50% Max 24 unidades Combinable LA SERENISIMA-Reg-2-50-Gigante"}],
    }

    base_price, promos = PromoTransformer.carrefour(oferta, "555")

    assert len(promos) == 1
    assert promos[0]["type"] == "conditional_discount"
    assert promos[0]["promo_id"] == "carrefour_teaser_555_0"
    assert promos[0]["discount_percentage_on_next"] == 50.0
    # Una sola unidad no gatilla nada; dos pagan una y media.
    assert evaluate_best_promo(base_price, promos, 1)["total_cost"] == base_price
    assert evaluate_best_promo(base_price, promos, 2)["total_cost"] == pytest.approx(base_price * 1.5)


def test_dia_conserva_sus_promo_id_tras_el_refactor():
    # .dia() y .carrefour() comparten implementación: este test es la guarda de
    # que compartirla no le cambió los ids ni el comportamiento a Día.
    oferta = {"ListPrice": 1500.0, "Price": 1200.0, "teasers": [{"name": "3x2 "}]}

    base_price, promos = PromoTransformer.dia(oferta, "311925")

    assert base_price == 1500.0
    assert {p["promo_id"] for p in promos} == {"dia_direct_311925", "dia_teaser_311925_0"}
    assert all(p["requires_membership"] is None for p in promos)


# --- Disponibilidad (compartida con Día, src/scrapers/vtex.py) --------------


def test_availability_lee_lo_que_dijo_la_tienda():
    """
    Con los parámetros de hoy VTEX filtra lo agotado del lado del servidor y
    todo vuelve con 10000, así que este camino parece decorativo. No lo es:
    con `hideUnavailableItems: False` la misma categoría devuelve 14 de 50
    productos con `AvailableQuantity: 0` (medido en vivo), y aflojar ese filtro
    es un cambio de una palabra.
    """
    disponible = {"sellers": [{"commertialOffer": {"AvailableQuantity": 10000}}]}
    agotado = {"sellers": [{"commertialOffer": {"AvailableQuantity": 0}}]}

    assert read_availability(disponible) is True
    assert read_availability(agotado) is False


def test_availability_default_true_si_el_campo_no_esta():
    """
    El `sha256Hash` fija el conjunto de campos del lado del servidor. Si la
    tienda lo rota y `AvailableQuantity` desaparece, un default `False` marcaría
    el catálogo entero como agotado y el optimizador no armaría ningún carrito.
    Ausencia es "la tienda no dijo", no "no hay".
    """
    assert read_availability({"sellers": [{"commertialOffer": {"Price": 100}}]}) is True
    assert read_availability({"sellers": []}) is True
    assert read_availability({}) is True


def test_availability_tolera_un_valor_ilegible():
    assert read_availability({"sellers": [{"commertialOffer": {"AvailableQuantity": None}}]}) is True
    assert read_availability({"sellers": [{"commertialOffer": {"AvailableQuantity": "x"}}]}) is True
