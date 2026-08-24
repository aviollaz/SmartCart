# src/scrapers/errors.py
"""
La excepción que corta el barrido de una categoría.

Existe porque las tres tiendas comparten un modo de falla que no se distingue
solo: el bucle de páginas tiene una salida legítima —una página válida con cero
productos, o sea la categoría agotada— y varias salidas por error que antes
usaban ese mismo `break`. La categoría cerraba corta y `_run_store` la contaba
OK, así que `StoreRunResult.complete` quedaba en True y habilitaba el pruning:
todo lo que el barrido no llegó a recorrer parece discontinuado y se borra.

La regla que impone esta excepción es una sola, igual en Coto, Día y Carrefour:
se hace `break` SÓLO ante una página vacía legítima; cualquier otro final
anticipado la levanta. Nadie la atrapa dentro del scraper — sube hasta
`_run_store`, que ya tolera la caída de una categoría (la cuenta como fallida y
sigue con la siguiente). Perder una categoría es estrictamente mejor que borrar
catálogo vivo, y con el pruning acotado por categoría esa pérdida además ya no
arrastra al resto de la tienda.
"""


class CategoryScrapeError(RuntimeError):
    """El barrido de una categoría terminó sin poder recorrerla entera."""
