from src.scrapers.vtex import VtexCatalogScraper, run_standalone


class VeaScraper(VtexCatalogScraper):
    STORE_KEY = "vea"
    LABEL = "VEA"
    BASE_URL = "https://www.vea.com.ar"


if __name__ == "__main__":
    run_standalone(VeaScraper)
