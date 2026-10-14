from src.scrapers.vtex import VtexCatalogScraper, run_standalone


class DiaScraper(VtexCatalogScraper):
    STORE_KEY = "dia"
    LABEL = "DÍA"
    # El `link` que devuelve VTEX trae a veces el dominio interno, que redirige
    # al login del admin; `storefront_url` lo reemplaza siempre por éste.
    BASE_URL = "https://diaonline.supermercadosdia.com.ar"


if __name__ == "__main__":
    run_standalone(DiaScraper)
