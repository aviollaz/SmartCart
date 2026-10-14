from src.scrapers.vtex import VtexCatalogScraper, storefront_url, run_standalone

BASE_URL = "https://www.carrefour.com.ar"


def build_carrefour_url(link: str | None) -> str | None:
    """
    URL absoluta a partir del `link` que devuelve VTEX.

    El campo viene relativo ("/vinagre-de-alcohol-alcazar-1-lt-100650/p"), así
    que guardarlo crudo deja links rotos en la ficha del producto — el mismo
    problema que en su momento tuvo Coto y que resolvió build_coto_url(). Si
    viniera absoluto tampoco se confía en su dominio: a Día le llegó el interno
    de VTEX, que manda al login del admin (ver `storefront_url`).
    """
    return storefront_url(link, BASE_URL)


class CarrefourScraper(VtexCatalogScraper):
    STORE_KEY = "carrefour"
    LABEL = "CARREFOUR"
    BASE_URL = BASE_URL


if __name__ == "__main__":
    run_standalone(CarrefourScraper)
