"""
Scraper de promociones bancarias de Jumbo: la misma entidad de Master Data de
Cencosud que lee src/promotions/scraper_vea.py, filtrada por el sitio de Jumbo.
"""
from src.promotions.scraper_vea import VeaScraper


class JumboScraper(VeaScraper):
    """Descuentos bancarios de Jumbo, vía la entidad de Master Data de Cencosud."""

    STORE_ID = "jumbo_online"
    WEBSITE = "jumboargentina"
    PREFIX = "jumbo"


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    for descuento in JumboScraper().scrape():
        print(descuento)
