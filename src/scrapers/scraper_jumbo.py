from src.scrapers.vtex import VtexCatalogScraper, run_standalone


class JumboScraper(VtexCatalogScraper):
    STORE_KEY = "jumbo"
    LABEL = "JUMBO"
    BASE_URL = "https://www.jumbo.com.ar"


if __name__ == "__main__":
    run_standalone(JumboScraper)
