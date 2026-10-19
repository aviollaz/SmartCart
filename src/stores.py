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


# El orden es la prioridad de imagen (api.IMAGE_STORE_PRIORITY).
STORES = (
    Store("coto", "coto_online", "Coto", 15000, 3000),
    Store("dia", "dia_online", "Día", 12000, 3000, "diaonline.supermercadosdia.com.ar"),
    Store("carrefour", "carrefour_online", "Carrefour", 20000, 3500, "www.carrefour.com.ar"),
    # Vea está APAGADA desde el 19-oct-2026: vea.com.ar sigue sirviendo un
    # skimmer de tarjetas en las descripciones de sus productos, y SmartCart
    # manda al usuario a ese checkout. Su código queda (scraper, promos,
    # logística, columnas `vea=` de SHELVES); lo que se sacó es el registro.
    # Reactivarla es volver a poner esta fila y sus entradas en VTEX_SCRAPERS,
    # promotions.SCRAPERS, PROMO_TRANSFORMERS, la etapa de logística de api.py,
    # constants.js, deliveryCosts.js y scrape.yml (tests/test_stores.py avisa
    # cuál falta), y correr un barrido.
    #
    # Vea es Cencosud y vende por el canal 34: con `sc=1` el carrito por URL
    # contesta "ítem no encontrado". El mínimo es el `minimumOrderValue` de su
    # simulación de checkout (0), sin confirmar en un checkout de verdad.
    # Store("vea", "vea_online", "Vea", 0, 3499, "www.vea.com.ar", sales_channel=34),
)

STORE_IDS = {s.key: s.id for s in STORES}
