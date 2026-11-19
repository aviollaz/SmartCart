"""
Los supermercados: el único lugar del backend donde se declara uno.

Todo lo que es un *dato* de la tienda (sus ids, su nombre, su mínimo de compra,
su envío por defecto, su dominio de checkout) sale de acá: `shelves.STORE_IDS`,
`optimizer.DEFAULT_MIN_SPEND_LIMITS`, `promotions.models.KNOWN_STORES`,
`api.VTEX_CHECKOUT_STORES`. Lo que es *código* propio de cada tienda (scrapers,
transformador de promos) sigue en su registro, pero `tests/test_stores.py` exige
que esos registros nombren exactamente a estas tiendas, así un olvido rompe
pytest en vez de la demo. El frontend tiene su espejo en
`frontend/src/utils/constants.js`, bajo el mismo test.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Store:
    key: str              # "coto": CLI --store, columna de SHELVES, dump de taxonomía
    id: str               # "coto_online": store_products, optimizador, frontend
    name: str             # "Coto"
    min_spend: float      # mínimo de compra
    delivery_cost: float  # envío por defecto (cuando el request no trae delivery_costs)
    checkout_domain: str | None = None  # VTEX con carrito por URL; None = no arma link
    sales_channel: int = 1  # el `sc` de VTEX para el carrito por URL
    # Motivo para que la tienda arranque DESHABILITADA en el frontend, o None.
    # Sigue en el catálogo y en el optimizador; el usuario tiene que habilitarla
    # a mano en "Supermercados", y ahí ve el aviso (el texto vive en el `warning`
    # de constants.js). Es el interruptor para una tienda en la que no confiamos
    # sin sacarla del registro: limpiarla es borrar este campo, en los dos lados.
    warning: str | None = None


# El orden es la prioridad de imagen (api.IMAGE_STORE_PRIORITY).
STORES = (
    Store("coto", "coto_online", "Coto", 15000, 3000),
    Store("dia", "dia_online", "Día", 12000, 3000, "diaonline.supermercadosdia.com.ar"),
    Store("carrefour", "carrefour_online", "Carrefour", 20000, 3500, "www.carrefour.com.ar"),
    # Vea es Cencosud y vende por el canal 34: con `sc=1` el carrito por URL
    # contesta "ítem no encontrado". El mínimo es el `minimumOrderValue` de su
    # simulación de checkout (0; para Día ese campo coincide con su mínimo real),
    # sin confirmar todavía en un checkout de verdad.
    #
    # Arrancó deshabilitada (`warning`) por un skimmer de tarjetas en las
    # descripciones de vea.com.ar (oct-2026). El 13-nov-2026 ya no estaba: 0 de
    # 1.551 productos muestreados con onerror/atob/eval en `description`.
    Store("vea", "vea_online", "Vea", 0, 3499, "www.vea.com.ar", sales_channel=34),
    # ChangoMás (masonline.com.ar). El mínimo sale del checkout real ($20.000,
    # nov 2026): ningún endpoint lo publica, y la prop `minPurchaseAmount` del
    # minicart de su tema dice 2000, desactualizada. El precio es por sucursal (la
    # simulación cotiza la misma yerba $5.289 en CABA y $4.399 en Córdoba); el
    # catálogo sin `regionId` trae el de CABA.
    Store("changomas", "changomas_online", "ChangoMás", 20000, 3999, "www.masonline.com.ar"),
    # Jumbo es Cencosud como Vea: mismo árbol de categorías, mismo ListPrice roto,
    # misma entidad de promos bancarias. Vende por el canal 32 (con `sc=1` el
    # checkout contesta error). El mínimo ($20.000) sale del checkout real
    # (nov 2026): la simulación dice `minimumOrderValue` 0, y no es cierto.
    Store("jumbo", "jumbo_online", "Jumbo", 20000, 3999, "www.jumbo.com.ar", sales_channel=32),
)

STORE_IDS = {s.key: s.id for s in STORES}
