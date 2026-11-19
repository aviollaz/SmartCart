from src.scrapers.vtex import VtexCatalogScraper, run_standalone


class ChangomasScraper(VtexCatalogScraper):
    STORE_KEY = "changomas"
    LABEL = "CHANGOMAS"
    BASE_URL = "https://www.masonline.com.ar"


if __name__ == "__main__":
    run_standalone(ChangomasScraper)
