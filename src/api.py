import re
import time
import logging
from contextlib import asynccontextmanager
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, Query, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import psycopg
from psycopg.rows import dict_row
from sentence_transformers import SentenceTransformer
from src.analytics import (
    analytics_status,
    build_cart_optimized_event,
    check_analyzer_health,
    send_cart_optimized_event,
)
from src.database import SmartCartDB
from src.optimizer import optimize_cart, DEFAULT_DELIVERY_COSTS, DEFAULT_MIN_SPEND_LIMITS
from src.flattener import flatten_cart_prices, evaluate_best_promo, parse_promotions_json
from src.category_tree import build_category_tree
from src.coto_logistics import check_coverage, resolve_coto_logistics
from src.strategic_swaps import find_strategic_swaps
from src.substitutions import build_semantic_suggestions


def _dietary_filter_clause(gluten_free: bool, vegan: bool, alias: str = "") -> str:
    """
    Cláusula SQL para los filtros dietarios. No lleva parámetros: los flags son
    booleanos ya validados por FastAPI, así que se interpolan como literales.

    Solo se emite el caso afirmativo. `is_gluten_free = FALSE` significa "el
    parser no encontró una declaración explícita", no "contiene gluten" (ver
    src/dietary_parser.py), así que un filtro "con TACC" sería una mentira.
    """
    prefix = f"{alias}." if alias else ""
    clauses = []
    if gluten_free:
        clauses.append(f"AND {prefix}is_gluten_free = TRUE")
    if vegan:
        clauses.append(f"AND {prefix}is_vegan = TRUE")
    return "\n                    ".join(clauses)


# Configuración de Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Modelos Pydantic para documentar y validar la API

class UnitInfo(BaseModel):
    units_per_pack: Optional[int] = Field(None, example=4)
    unit_type: Optional[str] = Field(None, example="gr")
    total_volume_weight: Optional[float] = Field(None, example=320.0)

class StorePromotion(BaseModel):
    promo_id: Optional[str] = None
    type: Optional[str] = None
    description: Optional[str] = None
    required_quantity: Optional[int] = None
    free_quantity: Optional[int] = None
    discount_percentage_on_next: Optional[float] = None
    requires_membership: Optional[str] = None
    valid_until: Optional[str] = None

class StoreOffer(BaseModel):
    store_id: str = Field(..., example="coto_online")
    product_url: Optional[str] = Field(None, example="https://www.cotodigital3.com.ar/...")
    base_price: float = Field(..., example=2500.0)
    in_stock: bool = Field(..., example=True)
    last_updated: Optional[str] = None
    image_url: Optional[str] = None
    promotions: List[StorePromotion] = []
    # Precio neto por unidad llevando UNA sola, ya con la mejor promo aplicable.
    # Va en None cuando ninguna promo mejora el precio a esa cantidad, que es lo
    # que pasa con las condicionales ("Llevando 2", "3x2", "2da al 50%"): recién
    # se activan cuando el usuario sube el selector, y ahí las calcula
    # /price-preview. Existe para que la grilla pueda mostrar de entrada el
    # precio con descuento directo en vez del de lista.
    promo_unit_price: Optional[float] = Field(None, example=2248.95)
    promo_description: Optional[str] = Field(None, example="50%Dto")

class ProductResponse(BaseModel):
    unified_id: str = Field(..., example="prod_7790000000123")
    ean: Optional[str] = Field(None, example="7790000000123")
    name: str = Field(..., example="Hamburguesa Paty Clásica")
    brand: Optional[str] = Field(None, example="Paty")
    category: Optional[str] = Field(None, example="congelados_hamburguesas")
    image_url: Optional[str] = None
    min_price: Optional[float] = None
    # OJO con la semántica: False significa "sin evidencia", NO "contiene gluten"
    # / "no es vegano". Ver src/dietary_parser.py — los flags solo se setean ante
    # una frase explícita del producto, así que solo el caso True es afirmable.
    is_gluten_free: bool = False
    is_vegan: bool = False
    unit_info: UnitInfo
    distance: float = Field(..., description="Distancia de coseno con respecto a la búsqueda (menor es más similar)")
    # Cuántas tiendas ofrecen el producto con stock. Es lo que desempata el
    # ranking (ver STORE_BONUS) y lo que permite verificar el feature desde la
    # API. Ojo: cuenta solo ofertas `in_stock`, mientras que
    # `available_at_stores` las trae todas, así que los dos números pueden no
    # coincidir. Opcional para no romper a ningún consumidor existente.
    store_count: Optional[int] = None
    available_at_stores: List[StoreOffer] = []

class CategorySubcategoryResponse(BaseModel):
    label: str
    leaves: List[str] = []

class CategoryTopLevelResponse(BaseModel):
    label: str
    has_direct_category_match: bool = Field(
        ...,
        description="True si este top-level existe literalmente en unified_products.category "
                    "(Lácteos/Golosinas/Almacén), permitiendo resolverlo vía GET /category/{label}. "
                    "Si es False, el frontend debe resolver el click vía GET /search?q=<label>."
    )
    subcategories: Dict[str, CategorySubcategoryResponse] = {}

class CartItem(BaseModel):
    unified_id: str
    quantity: int

class OptimizationRequest(BaseModel):
    cart: List[CartItem]
    user_memberships: Optional[List[str]] = []
    user_cards: Optional[List[str]] = []
    # Costos por zona que manda el frontend (frontend/src/utils/deliveryCosts.js).
    # Siguen siendo la fuente para Día y el fallback de Coto; cuando llegan
    # coordenadas, el envío de Coto se pisa con el valor real (ver más abajo).
    delivery_costs: Optional[Dict[str, float]] = None
    # Coordenadas del domicilio de entrega, geocodificadas en el frontend.
    # Opcionales: el usuario puede saltear el onboarding de dirección, y en ese
    # caso se cae al comportamiento por zona de siempre.
    lat: Optional[float] = None
    lng: Optional[float] = None
    # Los dos que siguen no los usa el optimizador: viajan sólo para el evento
    # analítico (src/analytics.py). Opcionales porque el contrato del analyzer
    # los acepta nulos y porque un perfil de localStorage anterior a la feature
    # no los trae — mejor un evento sin identificar que un 422 en el request.
    #
    # `anon_user_id` es un UUID de localStorage: identifica un navegador, no una
    # persona (SmartCart no tiene autenticación). Es lo que hace contable el KPI
    # de usuarios únicos.
    anon_user_id: Optional[str] = None
    # La zona la deriva el frontend de la dirección (utils/deliveryCosts.js), y
    # ya venía implícita en `delivery_costs`; acá viaja explícita porque un
    # diccionario de costos no se puede volver a mapear a una etiqueta.
    zone: Optional[str] = None

class PricePreviewRequest(BaseModel):
    items: List[CartItem]
    user_memberships: Optional[List[str]] = []

# Tope de ids por request a /products/by-ids. No hay un limite natural como el
# `limit` de /search: aca el llamador manda la lista, asi que sin tope un cliente
# roto puede pedir el catalogo entero en un round-trip. 100 es holgado para los
# dos usos reales (la grilla de habituales muestra ~12) y mantiene el `= ANY` en
# un tamano donde la query de ofertas sigue siendo un index scan.
#
# Si alguna vez se agrega una vista que precargue un carrito historico entero,
# revisar este numero antes que el cliente: un carrito grande lo pasa.
MAX_PRODUCTS_BY_IDS = 100


class ProductsByIdsRequest(BaseModel):
    unified_ids: List[str] = Field(..., min_length=1, max_length=MAX_PRODUCTS_BY_IDS)

# Estado global para mantener el modelo cargado en memoria
ml_models = {}

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
# los hechos, ordenar por cantidad de tiendas. Es el mismo tipo de umbral que
# category_tree.py documenta en su discusión del 0.90: se acota por el daño que
# no debe causar, no se sube hasta que "traiga más".
STORE_BONUS = 0.01

# Tope de tiendas extra que puede acumular el bonus. Con 3 tiendas en total, 2
# es el máximo posible; existir como constante es lo que le da a la pérdida de
# relevancia una cota dura (`STORE_BONUS * STORE_BONUS_CAP`) en vez de dejarla
# crecer con la cantidad de tiendas que se sumen en el futuro.
STORE_BONUS_CAP = 2

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Carga del modelo sentence-transformer en startup
    logger.info("Cargando modelo SentenceTransformer 'all-MiniLM-L6-v2'...")
    ml_models["model"] = SentenceTransformer("all-MiniLM-L6-v2")
    logger.info("Modelo SentenceTransformer cargado exitosamente.")

    # Construcción del árbol de categorías (Coto+Día) para el mega-menú.
    # Se calcula una sola vez acá (no en cada request) reutilizando el mismo
    # modelo ya cargado arriba para el merge semántico de subcategorías.
    logger.info("Construyendo árbol de categorías (Coto+Día)...")
    ml_models["category_tree"] = build_category_tree(ml_models["model"])
    logger.info(f"Árbol de categorías listo: {len(ml_models['category_tree'])} categorías de nivel superior.")

    # Inicialización de la base de datos para validar conexión
    try:
        db = SmartCartDB()
        with psycopg.connect(db.conn_string) as conn:
            logger.info("Conexión inicial con la base de datos exitosa.")
    except Exception as e:
        logger.error(f"Error al conectar con la base de datos en startup: {e}")

    # Estado de la emisión de eventos a SmartCart Performance Analyzer. Se dice
    # en el arranque porque los dos modos de no-emisión —falta la API key, o el
    # analyzer no responde— son deliberadamente silenciosos en tiempo de request
    # (la analítica no puede tumbar /optimize), y sin esta línea un server mal
    # configurado se ve igual que uno sano hasta que alguien abre el tablero y lo
    # encuentra vacío.
    status = analytics_status()
    if not status["enabled"]:
        logger.warning(f"Analitica: OFF - {status['reason']}. No se emiten eventos.")
    else:
        health = check_analyzer_health()
        if health["reachable"]:
            logger.info(f"Analitica: ON -> {status['url']} (analyzer OK, env={status['env']})")
        else:
            logger.warning(
                f"Analitica: ON -> {status['url']}, pero el analyzer no responde "
                f"({health['detail']}). Los eventos se van a perder hasta que vuelva."
            )

    yield
    # Limpieza
    ml_models.clear()
    logger.info("Modelo descargado de memoria.")

app = FastAPI(
    title="SmartCart Argentina - API de Búsqueda Semántica",
    description="Fase 2 del Motor de Similitud y Búsqueda Semántica usando NLP local y pgvector.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Middleware para facilitar integraciones de Frontend/UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    """
    Endpoint de salud que indica el estado general de la API.
    """
    return {
        "status": "online",
        "project": "SmartCart Argentina",
        "phase": "Fase 2: Motor de Similitud y Búsqueda Semántica",
        "model_loaded": "model" in ml_models,
        # Config, no ping: chequear el estado con un curl no puede costar una
        # llamada de red por request. Para saber si el analyzer está VIVO están
        # la línea "Analitica:" del arranque y su propio GET /health.
        "analytics": analytics_status(),
    }

def _build_store_offer(sp: dict) -> dict:
    """
    Arma la oferta de una tienda tal como la devuelven /search y /category.

    Estaba duplicado en los dos endpoints; se unificó al agregar el precio con
    promoción, para que no quedara la mitad del catálogo mostrando el precio de
    lista según por dónde entrara el usuario.

    El precio neto se calcula con la MISMA función que usa el optimizador
    (evaluate_best_promo, en src/flattener.py) sobre las promos crudas, no sobre
    las mapeadas de abajo: el mapeo descarta discount_price_per_unit y
    regular_price, que son justamente los campos que traen el precio con
    descuento de Coto. Se evalúa con quantity=1, así que solo puede ganar una
    promo que rija desde la primera unidad.

    user_memberships va vacío a propósito: la grilla es anónima y una promo que
    exige tarjeta o club no puede anunciarse como el precio por defecto.
    """
    base_price = float(sp["base_price"]) if sp["base_price"] is not None else 0.0
    raw_promos = parse_promotions_json(sp["promotions_json"]) if sp["promotions_json"] else []

    promotions = [
        {
            "promo_id": rp.get("promo_id") or rp.get("id"),
            "type": rp.get("type") or rp.get("promo_type"),
            "description": rp.get("description") or rp.get("name"),
            "required_quantity": rp.get("required_quantity"),
            "free_quantity": rp.get("free_quantity"),
            "discount_percentage_on_next": rp.get("discount_percentage_on_next") or rp.get("discount"),
            "requires_membership": rp.get("requires_membership"),
            "valid_until": rp.get("valid_until"),
        }
        for rp in raw_promos
    ]

    promo_unit_price = None
    promo_description = None
    if base_price > 0 and raw_promos:
        best = evaluate_best_promo(base_price, raw_promos, 1)
        if best["applied_promo_id"] is not None and best["total_cost"] < base_price:
            promo_unit_price = round(best["total_cost"], 2)
            promo_description = best["promo_description"]

    return {
        "store_id": sp["store_id"],
        "product_url": sp["product_url"],
        "base_price": base_price,
        "in_stock": bool(sp["in_stock"]),
        "last_updated": sp["last_updated"].isoformat() if sp["last_updated"] else None,
        "image_url": sp.get("image_url"),
        "promotions": promotions,
        "promo_unit_price": promo_unit_price,
        "promo_description": promo_description,
    }


# Mismo orden que resolveDisplayImage() en frontend/src/utils/formatters.js.
IMAGE_STORE_PRIORITY = ("coto_online", "dia_online", "carrefour_online")


def _fetch_offers_by_product(cur, product_ids: list) -> dict:
    """
    {unified_product_id: [oferta, ...]} para una lista de productos.

    La query estaba escrita a mano e identica en /search y /category; se extrajo
    al agregar /products/by-ids, que la necesitaba por tercera vez.

    NO filtra por in_stock a proposito, igual que antes: `available_at_stores`
    trae todas las ofertas y el que cuenta solo las disponibles es `store_count`
    (ver el LEFT JOIN de cada endpoint). Los dos numeros pueden discrepar y esa
    discrepancia es informacion, no un bug.
    """
    if not product_ids:
        return {}

    cur.execute("""
        SELECT unified_product_id, store_id, product_url, base_price, in_stock,
               promotions_json, image_url, last_updated
        FROM store_products
        WHERE unified_product_id = ANY(%s)
    """, (product_ids,))

    offers_by_product: Dict[str, List[Dict[str, Any]]] = {}
    for sp in cur.fetchall():
        offers_by_product.setdefault(sp["unified_product_id"], []).append(_build_store_offer(sp))
    return offers_by_product


def _build_product_response(row: dict, offers: list) -> dict:
    """
    Arma un ProductResponse a partir de una fila de unified_products y sus
    ofertas ya construidas por _build_store_offer().

    Estaba escrito a mano adentro de GET /category y se extrajo al agregar
    POST /products/by-ids: min_price y la eleccion de imagen son la unica parte
    de la respuesta que NO sale derecho de una columna, y dos copias significan
    que el mismo producto puede mostrar precio distinto segun por donde entro el
    usuario.

    `distance` va en 0.0 fija por la misma razon que en /category: ninguno de los
    dos endpoints tiene nocion de relevancia, y el campo es obligatorio en
    ProductResponse. Volverlo Optional cambiaria el contrato de /search a cambio
    de nada.

    GET /search NO usa esta funcion a proposito: no manda min_price ni image_url,
    y ese hueco esta documentado en CLAUDE.md (etapa 6) como preexistente y
    deliberado. Unificarlo aca le cambiaria la respuesta de refilon.

    Ojo con min_price: es el minimo de los precios de LISTA, promos ignoradas.
    Es una propiedad conocida que el frontend compensa en resolveDisplayPrice();
    "mejorarla" en un endpoint solo haria que el mismo producto tenga dos
    precios segun la pantalla desde la que se llegue.
    """
    min_price = min([o["base_price"] for o in offers if o["base_price"] > 0], default=0.0)

    best_image = None
    for preferido in IMAGE_STORE_PRIORITY:
        oferta = next((o for o in offers if o["store_id"] == preferido and o.get("image_url")), None)
        if oferta:
            best_image = oferta["image_url"]
            break

    return {
        "unified_id": row["id"],
        "ean": row["ean"],
        "name": row["name"],
        "brand": row["brand"],
        "category": row["category"],
        "min_price": min_price,
        "image_url": best_image,
        "is_gluten_free": bool(row["is_gluten_free"]),
        "is_vegan": bool(row["is_vegan"]),
        "unit_info": {
            "units_per_pack": row["units_per_pack"],
            "unit_type": row["unit_type"],
            "total_volume_weight": float(row["total_volume_weight"]) if row["total_volume_weight"] is not None else None
        },
        "distance": 0.0,
        "store_count": int(row["store_count"]),
        "available_at_stores": offers,
    }


@app.get("/search", response_model=List[ProductResponse])
def search_products(
    q: str = Query(..., description="Texto de búsqueda libre (ej. 'Puré de papas')", min_length=1),
    limit: int = Query(20, description="Cantidad máxima de resultados (entre 1 y 50)", ge=1, le=50),
    gluten_free: bool = Query(False, description="Devolver solo productos con declaración explícita 'sin TACC'"),
    vegan: bool = Query(False, description="Devolver solo productos con declaración explícita 'vegano'")
):
    """
    Realiza una búsqueda semántica en tiempo real sobre el catálogo de productos unificados.
    """
    if "model" not in ml_models:
        raise HTTPException(status_code=503, detail="El modelo de NLP no está inicializado.")

    logger.info(f"Procesando búsqueda semántica: '{q}' (limite={limit})")
    
    try:
        # 1. Generar embedding de la query
        query_embedding = ml_models["model"].encode(q)
        # Convertir a string de pgvector
        vector_str = f"[{','.join(map(str, query_embedding))}]"
        
        db = SmartCartDB()

        # Los filtros dietarios se resuelven en SQL y no en el cliente: el frontend
        # solo ve los `limit` vecinos más cercanos, así que filtrar ahí devolvería
        # un puñado de productos en vez de `limit` productos que cumplan el filtro.
        # Solo se filtra por TRUE — un FALSE en estas columnas es "sin evidencia".
        dietary_clause = _dietary_filter_clause(gluten_free, vegan)

        # 2. Recuperar y reordenar, en dos etapas dentro de la misma query.
        #
        # Etapa 1 (`pool`): los SEARCH_POOL_SIZE vecinos más cercanos con el
        # ORDER BY por distancia pura, que es lo único que el índice HNSW puede
        # acelerar. Etapa 2: reordenar ese pool por distancia menos el bonus de
        # disponibilidad, y recién ahí cortar a `limit`.
        #
        # El pool tiene que ser más grande que `limit`, si no el rerank no puede
        # cambiar QUÉ productos se muestran, solo en qué orden — que es
        # exactamente la limitación por la que esto no se resuelve en el cliente.
        with psycopg.connect(db.conn_string, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                # Sin esto el pool queda topeado en 40 filas (default de
                # pgvector) sin ningún error a la vista. Va por conexión.
                # `set_config()` y no `SET`: SET no acepta parámetros ligados
                # (`SET hnsw.ef_search = $1` es un error de sintaxis), y la
                # alternativa sería interpolar el número en un f-string.
                cur.execute(
                    "SELECT set_config('hnsw.ef_search', %s, false)",
                    (str(SEARCH_EF_SEARCH),),
                )

                cur.execute(f"""
                    WITH pool AS (
                        SELECT id, ean, name, brand, category, units_per_pack, unit_type,
                               total_volume_weight, is_gluten_free, is_vegan,
                               name_embedding <=> %s AS distance
                        FROM unified_products
                        WHERE name_embedding IS NOT NULL
                        {dietary_clause}
                        ORDER BY distance ASC
                        LIMIT %s
                    )
                    SELECT p.id, p.ean, p.name, p.brand, p.category, p.units_per_pack,
                           p.unit_type, p.total_volume_weight, p.is_gluten_free,
                           p.is_vegan, p.distance,
                           count(DISTINCT sp.store_id) AS store_count
                    FROM pool p
                    -- LEFT y no INNER: un producto sin ofertas con stock tiene
                    -- que seguir apareciendo (la query de ofertas de abajo
                    -- tampoco filtra por in_stock). Un INNER lo borraría sin
                    -- que nada lo indique.
                    LEFT JOIN store_products sp
                           ON sp.unified_product_id = p.id AND sp.in_stock
                    GROUP BY p.id, p.ean, p.name, p.brand, p.category, p.units_per_pack,
                             p.unit_type, p.total_volume_weight, p.is_gluten_free,
                             p.is_vegan, p.distance
                    -- GREATEST(... , 0) porque un producto sin ofertas da -1 y
                    -- convertiría el bonus en penalización por accidente.
                    ORDER BY p.distance - %s * LEAST(
                                 GREATEST(count(DISTINCT sp.store_id) - 1, 0), %s
                             ) ASC
                    LIMIT %s
                """, (vector_str, SEARCH_POOL_SIZE, STORE_BONUS, STORE_BONUS_CAP, limit))
                
                nearest_products = cur.fetchall()
                
                if not nearest_products:
                    logger.info("No se encontraron productos indexados con embeddings.")
                    return []
                
                # 3. Obtener ofertas asociadas de store_products para los productos unificados encontrados
                product_ids = [p["id"] for p in nearest_products]
                offers_by_product = _fetch_offers_by_product(cur, product_ids)

        # 4. Estructurar la respuesta final de búsqueda
        #
        # A diferencia de /category y /products/by-ids, este endpoint NO pasa por
        # _build_product_response(): no manda min_price ni image_url, y ese hueco
        # esta documentado en CLAUDE.md (etapa 6) como preexistente y deliberado.
        # Unificarlo aca seria cambiarle la respuesta de refilon.
        results = []
        for p in nearest_products:
            prod_id = p["id"]
            results.append({
                "unified_id": prod_id,
                "ean": p["ean"],
                "name": p["name"],
                "brand": p["brand"],
                "category": p["category"],
                "is_gluten_free": bool(p["is_gluten_free"]),
                "is_vegan": bool(p["is_vegan"]),
                "unit_info": {
                    "units_per_pack": p["units_per_pack"],
                    "unit_type": p["unit_type"],
                    "total_volume_weight": float(p["total_volume_weight"]) if p["total_volume_weight"] is not None else None
                },
                # Se devuelve la distancia CRUDA, no el score de ordenamiento:
                # es la relevancia semántica, y mezclarle el bonus volvería el
                # campo inservible para cualquier lectura futura.
                "distance": float(p["distance"]),
                "store_count": int(p["store_count"]),
                "available_at_stores": offers_by_product.get(prod_id, [])
            })
            
        return results

    except Exception as e:
        logger.error(f"Error interno durante la búsqueda semántica: {e}")
        raise HTTPException(status_code=500, detail=f"Error interno en el servidor: {e}")

def _compute_price_savings(result: dict, flat_prices: dict, excluded_stores: list) -> dict:
    """
    Cuánto se ahorra por elegir bien la tienda de cada producto: por cada línea
    del split, el precio MÁS CARO entre los supermercados que la tienen menos el
    que efectivamente se paga.

    Es una comparación producto a producto y nada más: no entra el envío ni el
    descuento bancario, así que este número NO es comparable contra
    `total_spent_net` ni contra ninguna diferencia de totales. La copia del panel
    lo dice; acá queda escrito para que nadie lo reinterprete después.

    Las tiendas excluidas no cuentan como "más caras": una que no entrega en la
    dirección infla el ahorro con una compra que el usuario no podía hacer.

    `items` sólo trae las líneas que aportan diferencia. Un producto que existe en
    una sola tienda da cero por definición, y listarlo sería puro relleno.
    """
    excluded = set(excluded_stores or [])
    items = []
    total = 0.0

    for store_id, checkout in (result.get("split") or {}).items():
        for line in checkout["products"]:
            uid = line["unified_id"]
            offers = {
                s: row["total_cost"]
                for s, row in flat_prices.get(uid, {}).items()
                if s not in excluded
            }
            if not offers:
                continue

            worst_store, worst_cost = max(offers.items(), key=lambda kv: kv[1])
            savings = worst_cost - line["total_cost"]
            if savings <= 0:
                continue

            total += savings
            items.append({
                "unified_id": uid,
                "actual_store": store_id,
                "actual_cost": round(line["total_cost"], 2),
                "worst_store": worst_store,
                "worst_cost": round(worst_cost, 2),
                "savings": round(savings, 2),
            })

    items.sort(key=lambda i: i["savings"], reverse=True)
    return {"total": round(total, 2), "items": items}


# Tiendas que corren sobre VTEX y por lo tanto aceptan un carrito armado por URL
# (/checkout/cart/add). Coto no está: su sitio es un SPA de ATG sin equivalente,
# y por eso sigue existiendo el fallback de abrir los productos de a uno.
#
# Agregar una tienda VTEX es agregar una fila acá, pero su scraper tiene que
# guardar `store_item_id` (ver save_store_products): sin esa columna la tienda
# no arma link, a propósito.
VTEX_CHECKOUT_DOMAINS = {
    "dia_online": "diaonline.supermercadosdia.com.ar",
    "carrefour_online": "www.carrefour.com.ar",
}


def generate_vtex_magic_link(store_domain: str, products: list, sales_channel: int = 1, seller_id: int = 1) -> str:
    """
    Genera un link de inyección directa de carrito para arquitecturas VTEX.
    
    :param store_domain: Dominio base (ej: 'diaonline.supermercadosdia.com.ar')
    :param products: Lista de diccionarios con el formato [{"store_sku": "12345", "quantity": 2}, ...]
    :param sales_channel: Canal de ventas de VTEX (suele ser 1)
    :param seller_id: ID del seller (1 para productos propios del super)
    :return: URL string o cadena vacía si no hay productos
    """
    if not products:
        return ""

    base_url = f"https://{store_domain}/checkout/cart/add?sc={sales_channel}"
    params = []
    
    for item in products:
        sku = item.get("store_sku")
        qty = item.get("quantity", 1)
        
        if sku:
            params.append(f"sku={sku}&qty={qty}&seller={seller_id}")

    if not params:
        return ""

    # Unimos todos los parámetros con un '&'
    return f"{base_url}&{'&'.join(params)}"

@app.post("/price-preview")
def preview_prices(request: PricePreviewRequest):
    """
    Devuelve el costo neto y el precio unitario aplanado de cada producto para una
    cantidad dada, por tienda, aplicando las promociones vigentes.

    Existe para que el frontend pueda mostrar "si llevás 2, te sale X c/u" sin
    replicar en JavaScript la lógica de promociones de src/flattener.py. Esa
    función es la única fuente de verdad de precios en el proyecto (la usa también
    el optimizador) y duplicarla en el cliente garantizaría que las dos versiones
    se separen apenas aparezca un tipo de promo nuevo.

    Los productos sin oferta en stock simplemente no aparecen como clave en la
    respuesta; el llamador tiene que contemplar ese caso.
    """
    if not request.items:
        return {}

    try:
        items = [item.model_dump() for item in request.items]
        return flatten_cart_prices(items, request.user_memberships)
    except Exception as e:
        logger.error(f"Error calculando el preview de precios: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------------------------
# Etapas de POST /optimize
#
# Cada una es una función con firma explícita en vez de un bloque dentro del
# endpoint. Lo que cada etapa lee y escribe ahora está en su firma: antes todas
# compartían las mismas variables locales del endpoint y el orden en que corrían
# era parte del contrato sin estar escrito en ningún lado.
# ---------------------------------------------------------------------------

def _optional_feature(nombre: str, default, fn, *args, **kwargs):
    """
    Corre una feature opcional y devuelve `default` si falla, dejando el error
    en el log.

    Todo lo que se le cuelga a un resultado exitoso —el ahorro contra el peor
    precio, las sugerencias, el cierre de tienda, los links— es explicación
    sobre una optimización que YA es correcta. Que cualquiera se caiga no puede
    costar ni la respuesta ni las otras features: misma doctrina fail-open que
    src/coto_logistics.py y src/analytics.py.

    Existe como helper y no como cuatro try/except copiados para que la política
    quede escrita una sola vez y no pueda divergir entre features, que es
    exactamente lo que le había pasado al motor de sustitución antes de
    unificarlo en src/substitutions.py.
    """
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        logger.error(f"Error en {nombre}: {e}")
        return default


def _resolve_coto_stage(request):
    """
    Etapa de logística: cobertura y envío real de Coto.

    Va antes del solver porque cambia dos de sus entradas: qué tiendas
    participan y cuánto cuesta el envío de Coto. Nunca lanza (fail-open, ver
    src/coto_logistics.py), así que un problema con el sitio de Coto no puede
    tumbar la optimización entera.

    :return: (delivery_costs, excluded_stores, coto_logistics)
    """
    delivery_costs = dict(request.delivery_costs) if request.delivery_costs else dict(DEFAULT_DELIVERY_COSTS)
    excluded_stores = []

    coto_logistics = resolve_coto_logistics(
        request.lat,
        request.lng,
        fallback_delivery_cost=delivery_costs.get("coto_online"),
    )

    if not coto_logistics["covered"]:
        excluded_stores.append("coto_online")
        logger.info(f"Coto excluido por falta de cobertura en ({request.lat}, {request.lng}).")
    elif coto_logistics["delivery_cost"] is not None:
        delivery_costs["coto_online"] = float(coto_logistics["delivery_cost"])

    return delivery_costs, excluded_stores, coto_logistics


def _attach_product_urls(cur, split: dict, flat_prices: dict) -> None:
    """
    Agrega a cada línea del split su link al producto y la promo que se le aplicó.

    Día y Carrefour tienen además un magic link de carrito completo
    (`_attach_vtex_checkout_links`); para el resto —Coto, que no expone un
    endpoint de carrito por URL— esto es lo que le permite al usuario abrir los
    productos de a uno.

    La promo aplicada viaja para que el desglose del frontend pueda explicar de
    dónde sale el `total_cost` en vez de mostrar un número sin justificar.

    Muta `split` in-place.
    """
    for store_id, store_result in split.items():
        store_products = store_result["products"]
        uids = [p["unified_id"] for p in store_products]
        if not uids:
            continue

        cur.execute("""
            SELECT unified_product_id, product_url
            FROM store_products
            WHERE store_id = %s AND unified_product_id = ANY(%s)
        """, (store_id, uids))

        url_map = {row["unified_product_id"]: row["product_url"] for row in cur.fetchall()}
        for p in store_products:
            p["product_url"] = url_map.get(p["unified_id"])

            line_flat = flat_prices.get(p["unified_id"], {}).get(store_id)
            if line_flat:
                p["applied_promo_id"] = line_flat["applied_promo_id"]
                p["promo_description"] = line_flat["promo_description"]
                p["effective_unit_price"] = line_flat["effective_unit_price"]


def _attach_vtex_checkout_links(cur, split: dict) -> None:
    """
    Agrega el link de carrito armado por URL a las tiendas VTEX del split.

    Muta `split` in-place.
    """
    for store_id, domain in VTEX_CHECKOUT_DOMAINS.items():
        if store_id not in split:
            continue

        store_products = split[store_id]["products"]
        uids = [p["unified_id"] for p in store_products]
        if not uids:
            continue

        # `store_item_id` y no `store_sku`: el segundo guarda el productId de
        # VTEX, y /checkout/cart/add espera el itemId. En Día los dos números
        # coinciden por cómo está armado su catálogo, pero en Carrefour no
        # (producto 100650 = item 17305), así que un COALESCE al store_sku
        # armaría un carrito equivocado en silencio. Una tienda sin la columna
        # poblada simplemente no muestra el botón y el frontend cae en los
        # links por producto.
        cur.execute("""
            SELECT unified_product_id, store_item_id
            FROM store_products
            WHERE store_id = %s AND unified_product_id = ANY(%s)
              AND store_item_id IS NOT NULL
        """, (store_id, uids))

        sku_map = {row["unified_product_id"]: row["store_item_id"] for row in cur.fetchall()}

        link_payload = [
            {"store_sku": sku_map[p["unified_id"]], "quantity": p["quantity"]}
            for p in store_products if p["unified_id"] in sku_map
        ]

        # Un carrito a medias es peor que ninguno: el usuario cree que ya tiene
        # todo cargado y paga menos productos de los que eligió.
        if len(link_payload) == len(store_products):
            split[store_id]["checkout_url"] = generate_vtex_magic_link(
                store_domain=domain,
                products=link_payload
            )
        elif link_payload:
            logger.warning(
                f"{store_id}: {len(store_products) - len(link_payload)} de "
                f"{len(store_products)} productos sin store_item_id; no se arma el "
                f"link de carrito. ¿Falta re-scrapear la tienda?"
            )


def _enrich_successful_result(result: dict, request, cart_data: list,
                              delivery_costs: dict, excluded_stores: list) -> None:
    """
    Cuelga del resultado óptimo todo lo que es explicación y no cálculo: cuánto
    se ahorró por elegir bien la tienda, qué alternativas hay, si conviene
    cerrar una tienda entera, y por dónde se compra.

    Nada de esto cambia el split ni el total. Cada feature va por
    `_optional_feature`, así que una puede fallar sin llevarse las otras.

    Muta `result` in-place.
    """
    db = SmartCartDB()
    flat_prices = flatten_cart_prices(cart_data, request.user_memberships)

    result["price_savings"] = _optional_feature(
        "el ahorro contra el peor precio", None,
        _compute_price_savings, result, flat_prices, excluded_stores,
    )

    # Una sola conexión para las cuatro features que tocan la base.
    with psycopg.connect(db.conn_string, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            split = result.get("split", {})

            result["suggestions"] = _optional_feature(
                "las sugerencias semánticas", [],
                build_semantic_suggestions,
                cur,
                cart_data,
                target_stores=[s for s in DEFAULT_MIN_SPEND_LIMITS if s not in excluded_stores],
                user_memberships=request.user_memberships,
            )

            result["strategic_swaps"] = _optional_feature(
                "la heurística de cierre de tienda", [],
                find_strategic_swaps,
                result=result,
                cart_items=cart_data,
                flat_prices=flat_prices,
                user_memberships=request.user_memberships,
                user_cards=request.user_cards,
                delivery_costs=delivery_costs,
                excluded_stores=excluded_stores,
                cur=cur,
            )

            _optional_feature("los links por producto", None,
                              _attach_product_urls, cur, split, flat_prices)
            _optional_feature("los magic links de VTEX", None,
                              _attach_vtex_checkout_links, cur, split)


def _ensure_optional_keys(result: dict) -> None:
    """
    Garantiza que las claves opcionales existan aunque el enriquecimiento entero
    se haya caído (ej. Postgres abajo a mitad de request). El frontend las lee
    sin chequear.
    """
    result.setdefault("suggestions", [])
    result.setdefault("strategic_swaps", [])
    result.setdefault("price_savings", None)


@app.post("/optimize")
def optimize_shopping_cart(request: OptimizationRequest, background_tasks: BackgroundTasks):
    """
    Recibe un carrito y devuelve la asignación óptima de supermercados
    considerando mínimos de compra, envíos y descuentos bancarios.
    """
    logger.info(f"Recibida solicitud de optimización para {len(request.cart)} productos.")

    started = time.perf_counter()

    def emit_analytics(payload_result: dict) -> None:
        """
        Encola el evento para SmartCart Performance Analyzer (src/analytics.py).

        Se llama desde las DOS salidas del endpoint —el resultado exitoso y el
        400 por carrito inviable—: el inviable es el KPI de fricción y el
        contrato del analyzer lo acepta explícitamente con `split` vacío.

        Lleva su propio try/except aunque `build_cart_optimized_event` sea pura:
        una optimización ya resuelta no puede perderse por un error armando su
        telemetría.
        """
        # El contrato exige `cart.items` no vacío, y un `success` sin split lo
        # rechaza con 422. Un carrito vacío no es una optimización medible, así
        # que no se emite en vez de garantizar un rechazo.
        if not request.cart:
            return

        try:
            duration_ms = int((time.perf_counter() - started) * 1000)
            event = build_cart_optimized_event(request, payload_result, duration_ms)
            background_tasks.add_task(send_cart_optimized_event, event)
        except Exception as e:
            logger.error(f"No se pudo armar el evento analítico: {e}")

    try:
        cart_data = [item.model_dump() for item in request.cart]

        delivery_costs, excluded_stores, coto_logistics = _resolve_coto_stage(request)

        result = optimize_cart(
            cart_items=cart_data,
            user_memberships=request.user_memberships,
            user_cards=request.user_cards,
            delivery_costs=delivery_costs,
            excluded_stores=excluded_stores
        )
        result["logistics"] = {"coto": coto_logistics}

        if result.get("status") == "success":
            # El enriquecimiento entero va detrás de un try porque comparte los
            # modos de falla que ninguna feature puede manejar sola: la conexión
            # a Postgres y el aplanado del carrito. Adentro cada feature tiene su
            # propia red (`_optional_feature`), así que acá sólo se llega si se
            # cayó algo común a todas.
            _optional_feature(
                "el enriquecimiento del resultado", None,
                _enrich_successful_result,
                result, request, cart_data, delivery_costs, excluded_stores,
            )
            _ensure_optional_keys(result)

    except Exception as e:
        logger.error(f"Error en el motor de optimización: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    if result.get("status") == "infeasible":
        msg = result.get("message", "El carrito no alcanza los montos mínimos requeridos por las tiendas ($15.000 Coto / $12.000 Día). Agregá más productos.")
        emit_analytics(result)
        # JSONResponse y no `raise HTTPException`, aunque la respuesta que sale
        # por el cable sea idéntica ({"detail": msg} con 400, que es exactamente
        # lo que arma el handler por defecto de FastAPI).
        #
        # El motivo es el BackgroundTask de arriba: FastAPI engancha las tareas a
        # la respuesta DESPUÉS de que el endpoint retorna (routing.py,
        # `if raw_response.background is None`). Si el endpoint lanza, el handler
        # de excepciones arma otra respuesta, sin `background`, y la tarea nunca
        # corre: el evento del carrito inviable —el que más interesa medir— se
        # perdería en silencio. Retornando un Response, FastAPI le engancha el
        # background igual.
        return JSONResponse(status_code=400, content={"detail": msg})

    emit_analytics(result)
    return result

@app.get("/logistics/coto/coverage")
def get_coto_coverage(
    lat: float = Query(..., description="Latitud del domicilio de entrega"),
    lng: float = Query(..., description="Longitud del domicilio de entrega")
):
    """
    Indica si Coto entrega en una coordenada dada.

    Existe para que el onboarding de dirección pueda avisar en el momento que
    Coto no llega, en vez de que el usuario lo descubra recién al optimizar un
    carrito ya armado.

    `ok=False` significa "no se pudo determinar" (Coto no respondió), y el
    frontend debe tratarlo como "sin novedad", no como falta de cobertura: la
    política es fail-open, sólo un veredicto afirmativo excluye la tienda.
    """
    return check_coverage(lat, lng)

@app.get("/categories/tree", response_model=Dict[str, CategoryTopLevelResponse])
def get_categories_tree():
    """
    Devuelve el árbol de categorías reales de Coto+Día (top-level -> subcategoría
    -> leaves), mergeado por texto normalizado, contención de tokens y
    similaridad semántica (ver src/category_tree.py). Pensado para alimentar
    el mega-menú del frontend.

    Regla de ruteo esperada en el frontend: un click en un top-level con
    has_direct_category_match=True (Lácteos/Golosinas/Almacén) debe resolverse
    vía GET /category/{label}; cualquier otro click (subcategoría, leaf, o un
    top-level sin match directo) debe resolverse vía GET /search?q=<label>.
    """
    return ml_models.get("category_tree", {})

@app.get("/categories")
def get_categories():
    """Devuelve una lista de todas las categorías únicas en la base de datos."""
    try:
        db = SmartCartDB()
        with psycopg.connect(db.conn_string) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT DISTINCT category FROM unified_products WHERE category IS NOT NULL ORDER BY category")
                return [row[0] for row in cur.fetchall()]
    except Exception as e:
        logger.error(f"Error obteniendo categorías: {e}")
        return []

@app.get("/category/{category_name}", response_model=List[ProductResponse])
def get_products_by_category(
    category_name: str,
    limit: int = 50,
    gluten_free: bool = Query(False, description="Devolver solo productos con declaración explícita 'sin TACC'"),
    vegan: bool = Query(False, description="Devolver solo productos con declaración explícita 'vegano'")
):
    """Devuelve productos filtrados por una categoría exacta."""
    try:
        db = SmartCartDB()
        # Con alias: la query lleva un JOIN a store_products, así que las
        # columnas dietarias tienen que quedar calificadas o Postgres las
        # rechaza por ambiguas.
        dietary_clause = _dietary_filter_clause(gluten_free, vegan, alias="u")
        with psycopg.connect(db.conn_string, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                # Este endpoint no tiene noción de relevancia (su `distance` es
                # 0.0 fija), así que ordenar por disponibilidad no resigna nada:
                # a diferencia de /search, acá no hay nada que el bonus pueda
                # desplazar. Además arregla un problema anterior: sin ORDER BY,
                # el LIMIT recortaba filas en el orden que Postgres tuviera a
                # mano y dos llamadas iguales podían devolver productos
                # distintos. El `name` desempata para que el orden sea estable.
                cur.execute(f"""
                    SELECT u.id, u.ean, u.name, u.brand, u.category, u.units_per_pack,
                           u.unit_type, u.total_volume_weight, u.is_gluten_free,
                           u.is_vegan, 0.0 AS distance,
                           count(DISTINCT sp.store_id) AS store_count
                    FROM unified_products u
                    LEFT JOIN store_products sp
                           ON sp.unified_product_id = u.id AND sp.in_stock
                    WHERE u.category = %s
                    {dietary_clause}
                    GROUP BY u.id, u.ean, u.name, u.brand, u.category, u.units_per_pack,
                             u.unit_type, u.total_volume_weight, u.is_gluten_free, u.is_vegan
                    ORDER BY store_count DESC, u.name ASC
                    LIMIT %s
                """, (category_name, limit))
                nearest_products = cur.fetchall()

                if not nearest_products:
                    return []

                product_ids = [p["id"] for p in nearest_products]
                offers_by_product = _fetch_offers_by_product(cur, product_ids)

        return [
            _build_product_response(p, offers_by_product.get(p["id"], []))
            for p in nearest_products
        ]
    except Exception as e:
        logger.error(f"Error en búsqueda por categoría: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/products/by-ids", response_model=List[ProductResponse])
def get_products_by_ids(request: ProductsByIdsRequest):
    """
    Devuelve los productos pedidos por unified_id, en el mismo orden en que se
    pidieron.

    Existe para el historial de compras del frontend, que guarda unified_ids en
    localStorage y necesita volver a resolverlos contra el catalogo de hoy.
    /price-preview no alcanza: devuelve precio pero ningun metadato, y /optimize
    puede contestar 400 por minimo de compra, asi que ninguno de los dos sirve de
    lookup.

    **Un unified_id AUSENTE de la respuesta significa exactamente una cosa: la
    fila ya no existe en unified_products, o sea que el pruning la borro (etapa 2
    de CLAUDE.md).** Ese contrato es el motivo entero de que este endpoint
    exista, y de el se desprenden las dos reglas que NO hay que "simplificar":

    - **No filtra por in_stock.** Si descartara los productos sin stock, un id
      ausente pasaria a significar o "lo dieron de baja para siempre" o "hoy no
      hay", y la UI no tendria como distinguirlos: le diria al usuario que un
      producto no se vende mas cuando en realidad vuelve manana. Ese es
      justamente el problema que ya tiene /price-preview, y que useUnavailable-
      CartItems.js documenta teniendo que NO marcar los ausentes por ambiguos.
      "Existe pero hoy no lo tiene nadie" es un estado real y distinto —
      prune_missing_store_products solo borra la fila unificada cuando no le
      queda ninguna oferta— y se reporta con store_count = 0.
    - **No acepta filtros dietarios.** Cualquier filtro capaz de descartar un id
      rompe el contrato de arriba. Un lookup por id no tiene facetas: el llamador
      ya sabe que productos quiere.

    `distance` va en 0.0 fija, igual que /category: no hay query, no hay
    relevancia que reportar.

    Tampoco falla hacia adelante devolviendo []: a diferencia de coto_logistics o
    analytics, una respuesta vacia en silencio es indistinguible de "todos tus
    habituales fueron dados de baja", que es la peor mentira posible para esta
    feature. El que falla abierto es el frontend (no renderiza la seccion); la
    API dice la verdad.
    """
    try:
        # dict.fromkeys deduplica conservando el orden: un id repetido no puede
        # producir dos filas, porque el frontend keyea la grilla por unified_id
        # y serian dos claves de React iguales.
        ordered_ids = list(dict.fromkeys(request.unified_ids))

        db = SmartCartDB()
        with psycopg.connect(db.conn_string, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT u.id, u.ean, u.name, u.brand, u.category, u.units_per_pack,
                           u.unit_type, u.total_volume_weight, u.is_gluten_free,
                           u.is_vegan, 0.0 AS distance,
                           count(DISTINCT sp.store_id) AS store_count
                    FROM unified_products u
                    LEFT JOIN store_products sp
                           ON sp.unified_product_id = u.id AND sp.in_stock
                    WHERE u.id = ANY(%s)
                    GROUP BY u.id, u.ean, u.name, u.brand, u.category, u.units_per_pack,
                             u.unit_type, u.total_volume_weight, u.is_gluten_free, u.is_vegan
                """, (ordered_ids,))
                rows_by_id = {row["id"]: row for row in cur.fetchall()}

                if not rows_by_id:
                    return []

                offers_by_product = _fetch_offers_by_product(cur, list(rows_by_id.keys()))

        # El orden se restituye en Python y no con un ORDER BY array_position():
        # el dict ya esta armado, asi que sale gratis, y evita mandar el array de
        # ids dos veces. El orden del request lleva informacion — es el ranking
        # del llamador —, devolver el de Postgres lo obligaria a reordenar.
        return [
            _build_product_response(rows_by_id[uid], offers_by_product.get(uid, []))
            for uid in ordered_ids
            if uid in rows_by_id
        ]

    except Exception as e:
        logger.error(f"Error en la busqueda por ids: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api:app", host="127.0.0.1", port=8000, reload=True)
