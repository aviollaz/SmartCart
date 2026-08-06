"""
Extracción de promociones bancarias de las cadenas.

Es un paquete aparte de src/scrapers/ a propósito: aquello ingesta catálogo
(productos, precios, promos por producto) hacia Postgres, y esto releva las
promociones bancarias de la cadena entera, que no cuelgan de ningún producto y
terminan en un archivo, no en la base.

Uso:
    from src.promotions import CotoScraper
    descuentos = CotoScraper().scrape()
"""
from src.promotions.base import DiscountScraper, DiscountScrapeError
from src.promotions.models import CANONICAL_DAYS, BankDiscount, InvalidDiscount
from src.promotions.playwright_base import PlaywrightScraper
from src.promotions.scraper_carrefour import CarrefourScraper
from src.promotions.scraper_coto import CotoScraper
from src.promotions.scraper_dia import DiaScraper

#: Los tres scrapers, indexados por el nombre corto que usa la CLI.
SCRAPERS = {
    "coto": CotoScraper,
    "dia": DiaScraper,
    "carrefour": CarrefourScraper,
}

__all__ = [
    "BankDiscount",
    "CANONICAL_DAYS",
    "CarrefourScraper",
    "CotoScraper",
    "DiaScraper",
    "DiscountScrapeError",
    "DiscountScraper",
    "InvalidDiscount",
    "PlaywrightScraper",
    "SCRAPERS",
]
