"""
Las tiendas VTEX, por su `key`. Sumar una es crear su subclase de
`VtexCatalogScraper` y listarla acá: los runners (`run_scrapers`,
`curar_frescos`) y el generador de taxonomía (`get_vtex_categories`) la toman
de este registro.
"""
from src.scrapers.scraper_carrefour import CarrefourScraper
from src.scrapers.scraper_dia import DiaScraper
from src.scrapers.scraper_vea import VeaScraper

VTEX_SCRAPERS = {cls.STORE_KEY: cls for cls in (DiaScraper, CarrefourScraper, VeaScraper)}
