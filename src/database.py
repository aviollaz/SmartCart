# src/database.py
import json
import logging

import psycopg
from psycopg.rows import dict_row

from src.db_pool import connection as pooled_connection
from src.promotion_parser import PromoTransformer
from src.schema import ensure_schema, resolve_conn_string

logger = logging.getLogger(__name__)


class SmartCartDB:
    def __init__(self, conn_string: str | None = None):
        # La resolución de la cadena (explícita > DATABASE_URL > docker-compose)
        # vive en src/schema.py, para que el DDL pueda correrse sin instanciar el
        # repositorio y para que haya una sola definición de a qué base apunta el
        # proyecto. Se resuelve acá y no a nivel módulo porque `load_dotenv()`
        # corre en el entry point, después de importar.
        self.conn_string = resolve_conn_string(conn_string)
        self._schema_ready = False

    def _ensure_schema(self, conn):
        """
        Aplica el DDL idempotente de `src/schema.py`, una vez por instancia.

        El esquema entero (tablas, columnas e índices) vive allá; acá sólo queda el
        cacheo, para no reemitir el DDL en cada categoría guardada.
        """
        if self._schema_ready:
            return

        ensure_schema(conn)
        self._schema_ready = True

    def save_store_products(self, products: list, store_id: str) -> int:
        """
        Persiste el lote de una categoría y devuelve cuántas filas se guardaron.

        LEVANTA si la escritura falla, a diferencia de la versión anterior que
        imprimía el error y devolvía normalmente. Ese `except` no salvaba ningún
        dato —psycopg3 envuelve todo el lote en una transacción, así que un error a
        mitad de camino ya revertía la categoría entera— pero sí escondía la
        pérdida: con Postgres caído el scrapeo reportaba éxito con cero filas
        escritas y después podaba contra un `seen_skus` que nunca aterrizó.

        El llamador decide qué hacer con la excepción; el orquestador la usa para
        marcar la categoría como fallida, bloquear el pruning de esa tienda y
        registrar el error real en la telemetría.
        """
        if not products:
            return 0

        logger.info("Estandarizando y guardando %d productos en '%s'...", len(products), store_id)
        try:
            with psycopg.connect(self.conn_string) as conn:
                self._ensure_schema(conn)
                with conn.cursor() as cur:
                    for prod in products:
                        # 1. Resolver identificador único
                        unified_id = f"prod_{prod['ean']}" if prod['ean'] else f"{store_id}_{prod['store_sku']}"
                        
                        # 2. TRANSFORMACIÓN: Normalizamos precio y promos según el origen
                        base_price = prod['base_price']
                        standardized_promos = []

                        if store_id == "coto_online":
                            standardized_promos = PromoTransformer.coto(prod['raw_promos'])
                        elif store_id == "dia_online":
                            # Para día, raw_promos contiene el 'commertialOffer' crudo de VTEX
                            base_price, standardized_promos = PromoTransformer.dia(
                                prod['raw_promos'],
                                prod['store_sku']
                            )
                        elif store_id == "carrefour_online":
                            # Carrefour también es VTEX: mismo 'commertialOffer' crudo,
                            # pero su hueco ListPrice/Price puede ser precio de socio
                            # (ver PromoTransformer.carrefour).
                            base_price, standardized_promos = PromoTransformer.carrefour(
                                prod['raw_promos'],
                                prod['store_sku']
                            )

                        # 2.5 Góndola y categoría de origen: las dos se exigen, no
                        # se leen con .get(). Un scraper que dejara de mandarlas no
                        # rompería nada visible —se escribiría NULL en silencio— y a
                        # partir de ahí todo barrido parcial podaría CERO filas
                        # reportando `deleted: 0` con `skipped: False`, que es
                        # indistinguible de "no se dio de baja nada". La góndola en
                        # NULL es igual de silenciosa: el producto desaparece de
                        # GET /category y deja de tener sustitutos posibles.
                        shelf = prod['shelf']
                        source_category = prod['source_category']

                        # 3. Guardar el Producto Unificado
                        # Los flags dietarios se PISAN en cada scrapeo en vez de
                        # acumularse con OR. Acumular preservaba la evidencia de
                        # ambas tiendas, pero volvía los flags monotónicos: un
                        # falso positivo no se podía corregir nunca, ni siquiera
                        # arreglando el parser. Para un campo del que depende
                        # alguien celíaco eso es inaceptable, y la asimetría
                        # juega a favor de pisar: un FALSE de más solo significa
                        # "sin evidencia" (seguro), mientras que un TRUE de más
                        # es el error peligroso.
                        cur.execute("""
                            INSERT INTO unified_products (
                                id, ean, name, brand, unit_type, shelf, total_volume_weight,
                                is_gluten_free, is_vegan
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (id) DO UPDATE SET
                                name = EXCLUDED.name,
                                brand = EXCLUDED.brand,
                                shelf = EXCLUDED.shelf,
                                -- unit_type va junto con total_volume_weight: los
                                -- dos salen de la misma llamada a
                                -- extract_real_volume() y describen una sola
                                -- medida. Actualizar el número sin la unidad
                                -- dejaba el peso nuevo pegado a la unidad vieja
                                -- del primer INSERT, y así quedaron en la base
                                -- cosas como "Fritolim 120 g" guardado en 'ml'.
                                -- Además congelaba en 'un' a todo producto cuyo
                                -- tamaño el parser no supo leer la primera vez,
                                -- volviendo inútil cualquier arreglo posterior
                                -- del parser sin borrar la tabla.
                                unit_type = EXCLUDED.unit_type,
                                total_volume_weight = EXCLUDED.total_volume_weight,
                                is_gluten_free = EXCLUDED.is_gluten_free,
                                is_vegan = EXCLUDED.is_vegan
                        """, (
                            unified_id,
                            prod['ean'],
                            prod['name'],
                            prod['brand'],
                            prod['unit_type'],
                            shelf,
                            prod['total_volume_weight'],
                            bool(prod.get('is_gluten_free', False)),
                            bool(prod.get('is_vegan', False))))

                        # 4. Guardar la Instancia Comercial con el JSON de promos y la IMAGEN
                        cur.execute("""
                            INSERT INTO store_products (
                                unified_product_id, store_id, store_sku, store_item_id, product_url, base_price, in_stock, promotions_json, image_url, source_category
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (store_id, store_sku) DO UPDATE SET
                                store_item_id = EXCLUDED.store_item_id,
                                product_url = EXCLUDED.product_url,
                                base_price = EXCLUDED.base_price,
                                in_stock = EXCLUDED.in_stock,
                                promotions_json = EXCLUDED.promotions_json,
                                image_url = EXCLUDED.image_url,
                                -- Va en el DO UPDATE SET como todo lo demás: una
                                -- columna que falte acá queda congelada en lo que
                                -- escribió el primer INSERT, y un re-scrapeo es el
                                -- único mecanismo del proyecto para corregir datos.
                                -- Congelada, además, dejaría el alcance del pruning
                                -- apuntando a una categoría que ya no es la que
                                -- ofrece el producto.
                                source_category = EXCLUDED.source_category,
                                last_updated = CURRENT_TIMESTAMP
                        """, (
                            unified_id,
                            store_id,
                            prod['store_sku'],
                            # Sólo lo mandan los scrapers VTEX. Va también en el
                            # DO UPDATE SET: una columna que falte ahí queda
                            # congelada en lo que escribió el primer INSERT, y un
                            # re-scrapeo es el único mecanismo del proyecto para
                            # corregir datos.
                            prod.get('store_item_id'),
                            prod['url'],
                            base_price,
                            prod['in_stock'],
                            json.dumps(standardized_promos),
                            prod.get('image_url'),  # <-- Guardamos la URL de la imagen extraída del scraper
                            source_category
                        ))
            logger.info("Guardado exitoso: %d filas en '%s'.", len(products), store_id)
            return len(products)
        except Exception:
            logger.exception("Error guardando %d productos en '%s'.", len(products), store_id)
            raise


    # Fracción de las filas de una tienda que un pruning puede borrar antes de
    # considerarse sospechoso. Un catálogo real se mueve de a poco; perder un
    # tercio de golpe es la firma de un scrapeo roto, no de productos discontinuados.
    MAX_PRUNE_RATIO = 0.30

    def prune_missing_store_products(self, store_id: str, seen_skus: set,
                                     dry_run: bool = False,
                                     categories: set | None = None) -> dict:
        """
        Borra las filas de `store_id` cuyo SKU no apareció en el scrapeo actual.

        Sin esto un producto que la tienda discontinúa queda para siempre con
        `in_stock = TRUE`, y el optimizador lo sigue ofreciendo — incluso puede
        armar el split entero alrededor de algo que ya no se puede comprar.

        El invariante que lo hace seguro es que `seen_skus` sea el universo COMPLETO
        de lo que la tienda ofrece: con un recorrido parcial, todo lo que faltó
        recorrer parece discontinuado. Pero ese invariante **también vale por
        categoría**, y de ahí sale `categories`:

          * `None` — se poda la tienda entera. Exige un barrido completo.
          * un set de claves de categoría — el borrado se limita a las filas cuya
            `source_category` está ahí, o sea a las categorías que terminaron bien.
            Una categoría caída deja de costarle el pruning al resto de la tienda,
            que es lo que pasaba cuando el único gate era `StoreRunResult.complete`:
            con 30 categorías por tienda, una sola caída dejaba a esa tienda sin
            podar, acumulando filas `in_stock = TRUE` de productos que ya no
            existen. No se afloja nada a cambio — las categorías que fallaron
            simplemente quedan fuera del alcance del DELETE.

        Las filas con `source_category` en NULL (las anteriores a esa columna) nunca
        entran en un alcance acotado. Es la dirección segura y se resuelve solo
        después de un barrido completo.

        Dos frenos, porque el costo de los dos errores no es simétrico: dejar una
        fila muerta de más molesta, borrar el catálogo entero rompe la app. (1) Un
        `seen_skus` vacío no borra nada — ese es exactamente el modo de falla que
        documenta CLAUDE.md, el hash de la persisted query de VTEX rotado
        devolviendo 200 con `errors` y cero productos. (2) Si el borrado se lleva
        más de MAX_PRUNE_RATIO, se aborta y se avisa: es más probable que se haya
        roto el scraper a que la tienda haya discontinuado un tercio de su góndola.

        **El denominador de ese ratio se cuenta dentro del mismo alcance.** Contra
        el total de la tienda, una categoría rota que vale el 3% del catálogo jamás
        tocaría el freno del 30%; contra el total de esa categoría, sí.

        Devuelve {'deleted', 'orphans', 'skipped', 'reason'}.
        """
        resultado = {"deleted": 0, "orphans": 0, "skipped": False, "reason": None}

        if not seen_skus:
            resultado.update(skipped=True, reason="el scrapeo no devolvió ningún SKU")
            logger.warning("Pruning de '%s' omitido: %s.", store_id, resultado["reason"])
            return resultado

        if categories is not None and not categories:
            resultado.update(skipped=True, reason="ninguna categoría terminó su barrido")
            logger.warning("Pruning de '%s' omitido: %s.", store_id, resultado["reason"])
            return resultado

        # El alcance viaja como fragmento SQL + params para que las tres consultas
        # (los dos count y el DELETE) usen literalmente la misma condición. Que se
        # separen es lo que haría que el freno del ratio mida sobre un universo y
        # el borrado corra sobre otro.
        alcance = " AND source_category = ANY(%s)" if categories is not None else ""
        params_alcance = (list(categories),) if categories is not None else ()
        ambito = "toda la tienda" if categories is None else f"{len(categories)} categoría(s)"

        try:
            with psycopg.connect(self.conn_string) as conn:
                self._ensure_schema(conn)
                with conn.cursor() as cur:
                    cur.execute(
                        f"SELECT count(*) FROM store_products WHERE store_id = %s{alcance}",
                        (store_id, *params_alcance),
                    )
                    total = cur.fetchone()[0]

                    cur.execute(
                        f"""
                        SELECT count(*) FROM store_products
                        WHERE store_id = %s{alcance} AND store_sku <> ALL(%s)
                        """,
                        (store_id, *params_alcance, list(seen_skus)),
                    )
                    obsoletas = cur.fetchone()[0]

                    if obsoletas == 0:
                        logger.info("Pruning de '%s' sobre %s: no hay filas obsoletas.",
                                    store_id, ambito)
                        return resultado

                    if total and (obsoletas / total) > self.MAX_PRUNE_RATIO:
                        resultado.update(
                            skipped=True,
                            reason=(f"borraría {obsoletas} de {total} filas "
                                    f"de {ambito} ({obsoletas / total:.0%}), por encima del "
                                    f"{self.MAX_PRUNE_RATIO:.0%} permitido"),
                        )
                        logger.error(
                            "ATENCIÓN: pruning de '%s' abortado: %s. "
                            "Revisá el scraper antes de insistir.",
                            store_id, resultado["reason"],
                        )
                        return resultado

                    cur.execute(
                        f"""
                        DELETE FROM store_products
                        WHERE store_id = %s{alcance} AND store_sku <> ALL(%s)
                        """,
                        (store_id, *params_alcance, list(seen_skus)),
                    )
                    resultado["deleted"] = cur.rowcount

                    # Un unified_product que se quedó sin ninguna oferta ya no lo
                    # vende nadie: dejarlo lo mantiene visible en /search y en el
                    # catálogo, con un precio que no existe.
                    cur.execute(
                        """
                        DELETE FROM unified_products u
                        WHERE NOT EXISTS (
                            SELECT 1 FROM store_products sp WHERE sp.unified_product_id = u.id
                        )
                        """
                    )
                    resultado["orphans"] = cur.rowcount

                    # El dry-run corre el borrado de verdad y lo deshace, en vez de
                    # estimarlo con un COUNT: así los dos números que informa son
                    # exactamente los que vería un run real. Contar los huérfanos
                    # sin borrar primero exigiría replicar en un SELECT la
                    # condición del DELETE, y esa copia es justo lo que haría que
                    # el dry-run mienta el día que alguien cambie una de las dos.
                    if dry_run:
                        conn.rollback()
                        logger.info(
                            "Pruning de '%s' sobre %s (dry-run): borraría %d de %d "
                            "filas y %d productos sin ofertas.",
                            store_id, ambito, resultado["deleted"], total,
                            resultado["orphans"],
                        )
                        return resultado

            logger.info(
                "Pruning de '%s' sobre %s: %d filas obsoletas borradas, "
                "%d productos sin ofertas eliminados.",
                store_id, ambito, resultado["deleted"], resultado["orphans"],
            )
        except Exception as e:
            # Acá SÍ se atrapa, a diferencia de save_store_products: quedarse con
            # filas de más deja la base degradada, no rota, y no vale tumbar por eso
            # un scrapeo que ya terminó bien. El motivo viaja en `reason` y el
            # orquestador lo registra en la telemetría como PARTIAL.
            logger.exception("Error en el pruning de '%s'.", store_id)
            resultado.update(skipped=True, reason=str(e))

        return resultado

    def get_market_prices_for_cart(self, unified_ids: list) -> list:
        """
        Precios base y promociones de todas las tiendas que tienen en stock alguno
        de estos productos unificados.

        Proyecta exactamente lo que su único consumidor lee: `flatten_cart_prices`
        (src/flattener.py) usa `unified_product_id`, `store_id`, `base_price` y
        `promotions_json`, y nada más. `in_stock` e `image_url` se traían y se
        tiraban — `in_stock` sigue estando, pero como predicado del WHERE.
        """
        if not unified_ids:
            return []

        query = """
            SELECT
                unified_product_id,
                store_id,
                base_price,
                promotions_json
            FROM store_products
            WHERE unified_product_id = ANY(%s) AND in_stock = TRUE;
        """
        
        # Único camino de lectura de este módulo que corre por request, y el que
        # más conexiones abre: lo llama `flatten_cart_prices`, que /optimize
        # invoca una vez para el carrito y la heurística de cierre de tienda una
        # vez por cantidad distinta de cada simulación. Por eso va por el pool
        # (ver src/db_pool.py) y no por `psycopg.connect` directo como el resto
        # del módulo, que son caminos de scrapeo de una sola pasada.
        try:
            with pooled_connection(self.conn_string) as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (unified_ids,))
                    return cur.fetchall()
        except Exception:
            logger.exception("Error al recuperar precios para el carrito.")
            return []