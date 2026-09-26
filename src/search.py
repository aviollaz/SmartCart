# src/search.py
"""
La consulta de GET /search, en un solo lugar.

Existe para que `src/api.py` y `src/scripts/medir_busqueda.py` corran **el mismo
SQL**. Antes el script copiaba la consulta a mano (y sin el bonus por
disponibilidad), así que medía algo parecido a lo que recibe el usuario, no lo
mismo — que es justo la clase de diferencia que invalida una medición.

Dos modos:

  * **denso** — recuperar-y-reordenar sobre el embedding (el de siempre): los
    SEARCH_POOL_SIZE vecinos más cercanos, reordenados por distancia menos el
    bonus por disponibilidad.
  * **híbrido** — suma una mitad léxica (tsvector + `ts_rank_cd` sobre
    `unified_products.name_tsv`) y fusiona las dos listas por Reciprocal Rank
    Fusion. Para queries cortas y precisas ("oreo", "coca cola 2.25") el
    léxico le gana al embedding casi siempre; el vector sigue ganando en las
    vagas ("algo para untar"). RRF combina RANKINGS, no puntajes, así que no hay
    que calibrar una distancia coseno contra un `ts_rank` (dos escalas sin
    relación). La mitad densa entra con el orden que ya tenía —bonus incluido—,
    así que la constante calibrada de abajo sigue significando lo mismo.

`distance` se devuelve CRUDA en los dos modos, también para los productos que
sólo trajo la mitad léxica: es la relevancia semántica y el frontend la puede
leer; el puntaje de orden no sale de acá.
"""
import re

# Qué modo usa GET /search. Queda en "denso" hasta que `medir_busqueda.py
# --modo hibrido` demuestre que el híbrido no pierde contra el actual (ver
# docs/TODO.md, búsqueda híbrida): mismo criterio que el ítem del modelo
# multilingüe, que se midió y se descartó.
DEFAULT_SEARCH_MODE = "denso"
SEARCH_MODES = ("denso", "hibrido")

# ---------------------------------------------------------------- ranking
# El orden de /search era distancia coseno pura, así que un producto que está
# en las tres tiendas no tenía ninguna ventaja sobre uno que está en una sola.
# Para una app cuyo objetivo es comparar precios, eso deja arriba resultados
# sobre los que el optimizador no puede hacer nada.
#
# No se puede arreglar en el frontend: el cliente solo recibe los `limit`
# vecinos que Postgres ya eligió, así que un producto de 3 tiendas en el puesto
# 25 no existe para él. Reordenar allá cambia el ORDEN del top-N pero nunca su
# COMPOSICIÓN. Por eso se recupera un pool más grande y se reordena en SQL.
SEARCH_POOL_SIZE = 100

# `hnsw.ef_search` vale 40 por defecto en pgvector, y es un techo sobre las
# filas que el índice devuelve: con el default, un `LIMIT 100` devuelve 40 y el
# pool de arriba es una ilusión — el rerank reordena siempre los mismos 40
# candidatos y el feature parece andar sin hacer nada. Se sube por conexión.
SEARCH_EF_SEARCH = 200

# Bonus por tienda extra, en unidades de distancia coseno. Calibrado sobre 15
# queries reales del catálogo: el spread natural del top-20 (d@20 - d@1) tiene
# mediana 0.110, así que la pérdida máxima de relevancia que habilita este
# bonus —`STORE_BONUS * STORE_BONUS_CAP` = 0.02— es ~18% de ese spread. Medido:
# cambia el 5% del top-20 y sube las tiendas promedio de 1.49 a 1.57.
#
# NO subirlo para "mejorar" el efecto. Con 0.02 la query "yogur bebible" saca
# dos yogures BEBIBLES (d=0.368, 0.370) y mete tres Yogurísimo GRIEGO (d≈0.39)
# que están en 3 tiendas: el embedding no trata "bebible" como restricción
# dura, así que un bonus moderado compra disponibilidad con relevancia literal.
# Con 0.05 el 31% del top-20 cambia y un producto puede saltar del puesto 79,
# cruzando entero el gap de relevancia entre el rank 20 y el 100 (0.105) — en
# los hechos, ordenar por cantidad de tiendas. La disciplina es la del proyecto:
# un umbral se acota por el daño que no debe causar, no se sube hasta que "traiga
# más".
STORE_BONUS = 0.01

# Tope de tiendas extra que puede acumular el bonus. Con 3 tiendas en total, 2
# es el máximo posible; existir como constante es lo que le da a la pérdida de
# relevancia una cota dura (`STORE_BONUS * STORE_BONUS_CAP`) en vez de dejarla
# crecer con la cantidad de tiendas que se sumen en el futuro.
STORE_BONUS_CAP = 2

# Constante de Reciprocal Rank Fusion. 60 es el valor del paper original
# (Cormack et al., 2009) y el default de prácticamente todas las
# implementaciones: aplana la diferencia entre los primeros puestos para que
# ninguna de las dos listas domine sola. No se calibró contra este catálogo.
RRF_K = 60

# Palabras: letras (con acentos) o números, con decimales ("2.25", "1,5"). Todo
# lo demás es separador, y eso es lo que hace imposible inyectar sintaxis de
# tsquery (`&`, `!`, `:`, paréntesis) desde lo que escribe el usuario.
_TOKEN = re.compile(r"\d+(?:[.,]\d+)?|[^\W\d_]+")


def build_lexical_query(q: str) -> str | None:
    """
    La query del usuario como tsquery en modo OR con prefijo: "oreo 354g" ->
    "oreo:* | 354:*".

    OR y no AND: con AND, "yerba playadito 1kg" no encuentra nada si el nombre
    dice "1 Kg." — un solo token que no matchea tira el resultado entero.
    `ts_rank_cd` ya premia a los productos que matchean más términos, que es lo
    que AND intentaba conseguir. El prefijo (`:*`) cubre la búsqueda a medio
    escribir ("galleti").

    Descarta tokens de una sola letra que no sean números ("g" de "354g" matchea
    cualquier cosa en gramos). Devuelve None si no queda nada: el llamador cae a
    la mitad densa sola.
    """
    tokens = []
    for token in _TOKEN.findall((q or "").lower()):
        if len(token) < 2 and not token.isdigit():
            continue
        token = token.replace(",", ".")
        if token not in tokens:
            tokens.append(token)
    if not tokens:
        return None
    return " | ".join(f"{token}:*" for token in tokens)


_ROW_COLUMNS = """
    u.id, u.ean, u.name, u.brand, u.shelf, u.unit_type, u.total_volume_weight,
    u.is_gluten_free, u.is_vegan
"""

# Etapa 1 (`pool`): los SEARCH_POOL_SIZE vecinos más cercanos con el ORDER BY por
# distancia pura, que es lo único que el índice HNSW puede acelerar. Etapa 2:
# reordenar ese pool por distancia menos el bonus de disponibilidad, y recién
# ahí cortar a `limit`. El pool tiene que ser más grande que `limit`, si no el
# rerank no puede cambiar QUÉ productos se muestran, sólo en qué orden.
_DENSE_SQL = """
    WITH pool AS (
        SELECT id, name_embedding <=> %(vec)s AS distance
        FROM unified_products
        WHERE name_embedding IS NOT NULL
        {dietary}
        ORDER BY distance ASC
        LIMIT %(pool)s
    )
    SELECT {columns}, p.distance,
           count(DISTINCT sp.store_id) AS store_count
    FROM pool p
    JOIN unified_products u ON u.id = p.id
    -- LEFT y no INNER: un producto sin ofertas con stock tiene que seguir
    -- apareciendo (la query de ofertas tampoco filtra por in_stock). Un INNER
    -- lo borraría sin que nada lo indique.
    LEFT JOIN store_products sp
           ON sp.unified_product_id = u.id AND sp.in_stock
    GROUP BY u.id, p.distance
    -- GREATEST(... , 0) porque un producto sin ofertas da -1 y convertiría el
    -- bonus en penalización por accidente.
    ORDER BY p.distance - %(bonus)s * LEAST(
                 GREATEST(count(DISTINCT sp.store_id) - 1, 0), %(cap)s
             ) ASC, u.id
    LIMIT %(limit)s
"""

# Las dos listas se arman por separado (cada una con su índice: HNSW y GIN), se
# unen, y cada candidato suma 1/(k + puesto) por cada lista en la que aparece.
# Un producto que sólo trajo una mitad no queda afuera: suma sólo lo suyo.
_HYBRID_SQL = """
    WITH dense AS (
        SELECT id, name_embedding <=> %(vec)s AS distance
        FROM unified_products
        WHERE name_embedding IS NOT NULL
        {dietary}
        ORDER BY distance ASC
        LIMIT %(pool)s
    ),
    lex AS (
        SELECT id, ts_rank_cd(name_tsv, q) AS lex_score
        FROM unified_products,
             to_tsquery('spanish'::regconfig, smartcart_unaccent(%(tsq)s)) AS q
        WHERE name_tsv @@ q
          -- Mismo universo que la mitad densa: un producto sin embedding
          -- todavía no está indexado, y sin distancia no tiene qué reportar.
          AND name_embedding IS NOT NULL
          {dietary}
        ORDER BY lex_score DESC, id
        LIMIT %(pool)s
    ),
    scored AS (
        SELECT {columns},
               u.name_embedding <=> %(vec)s AS distance,
               count(DISTINCT sp.store_id) AS store_count
        FROM (SELECT id FROM dense UNION SELECT id FROM lex) c
        JOIN unified_products u ON u.id = c.id
        LEFT JOIN store_products sp
               ON sp.unified_product_id = u.id AND sp.in_stock
        GROUP BY u.id
    ),
    dense_ranked AS (
        -- El orden de la mitad densa es exactamente el del modo denso (distancia
        -- menos el bonus), así que STORE_BONUS conserva su calibración.
        SELECT s.id, row_number() OVER (
                   ORDER BY s.distance - %(bonus)s * LEAST(GREATEST(s.store_count - 1, 0), %(cap)s),
                            s.id
               ) AS r
        FROM scored s
        WHERE s.id IN (SELECT id FROM dense)
    ),
    lex_ranked AS (
        SELECT id, row_number() OVER (ORDER BY lex_score DESC, id) AS r
        FROM lex
    )
    SELECT s.*
    FROM scored s
    LEFT JOIN dense_ranked dr ON dr.id = s.id
    LEFT JOIN lex_ranked lr ON lr.id = s.id
    ORDER BY COALESCE(1.0 / (%(k)s + dr.r), 0) + COALESCE(1.0 / (%(k)s + lr.r), 0) DESC,
             s.distance ASC, s.id
    LIMIT %(limit)s
"""


def search_rows(cur, vector_literal: str, q: str, limit: int,
                dietary_clause: str = "", mode: str = DEFAULT_SEARCH_MODE) -> list:
    """
    Corre la búsqueda y devuelve las filas ya ordenadas y cortadas a `limit`.

    `vector_literal` es el embedding de la query como literal de pgvector
    ("[0.1,0.2,...]"). `dietary_clause` sale de `_dietary_filter_clause` de
    src/api.py y se aplica a las DOS mitades: filtrar después de fusionar
    devolvería menos de `limit` resultados.

    Sube `hnsw.ef_search` en la conexión antes de consultar: sin eso el pool
    queda topeado en 40 filas (default de pgvector) sin ningún error a la vista.
    `set_config()` y no `SET`: SET no acepta parámetros ligados.
    """
    if mode not in SEARCH_MODES:
        raise ValueError(f"Modo de búsqueda desconocido: {mode!r}")

    cur.execute("SELECT set_config('hnsw.ef_search', %s, false)", (str(SEARCH_EF_SEARCH),))

    params = {"vec": vector_literal, "pool": SEARCH_POOL_SIZE, "bonus": STORE_BONUS,
              "cap": STORE_BONUS_CAP, "limit": limit}
    tsquery = build_lexical_query(q) if mode == "hibrido" else None

    if tsquery is None:
        sql = _DENSE_SQL
    else:
        sql = _HYBRID_SQL
        params.update(tsq=tsquery, k=RRF_K)

    cur.execute(sql.format(dietary=dietary_clause, columns=_ROW_COLUMNS), params)
    return cur.fetchall()
