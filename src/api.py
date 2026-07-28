import re
import logging
from contextlib import asynccontextmanager
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import psycopg
from psycopg.rows import dict_row
from sentence_transformers import SentenceTransformer
from src.database import SmartCartDB
from src.optimizer import optimize_cart
from src.flattener import flatten_cart_prices
from src.category_tree import build_category_tree
from src.category_tags import filter_tags


def _same_aisle_filter(product_row: dict, alias: str = "") -> tuple[str, Any]:
    """
    Cláusula SQL que restringe los candidatos a sustituto a la misma góndola
    que el producto original, más su parámetro.

    Prefiere los tags de taxonomía (estrictos: la mayonesa cuelga de
    "almacén -> aceites y aderezos" y la carne de "frescos -> carnes", así que
    no pueden matchear). Cae a `category` cuando el producto todavía no tiene
    tags, que es el caso de toda fila no re-scrapeada: sin ese fallback las
    sugerencias se romperían en silencio durante la transición.

    Se usa `&&` (solapamiento) y no `@>` (containment) porque las tiendas
    anidan a distinta profundidad; ver src/category_tags.filter_tags().
    """
    prefix = f"{alias}." if alias else ""
    tags = filter_tags(product_row.get("tags"))

    if tags:
        return f"AND {prefix}tags && %s::text[]", tags
    return f"AND {prefix}category = %s", product_row.get("category")


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
    # En el futuro la dirección determinará los costos, ahora los pasamos opcionales
    delivery_costs: Optional[Dict[str, float]] = None

class PricePreviewRequest(BaseModel):
    items: List[CartItem]
    user_memberships: Optional[List[str]] = []

# Estado global para mantener el modelo cargado en memoria
ml_models = {}

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
        "model_loaded": "model" in ml_models
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

        # 2. Consultar vecinos más cercanos en PostgreSQL usando la distancia de coseno (<=>)
        # Traemos también los detalles del producto unificado
        with psycopg.connect(db.conn_string, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT id, ean, name, brand, category, units_per_pack, unit_type, total_volume_weight,
                           is_gluten_free, is_vegan,
                           name_embedding <=> %s AS distance
                    FROM unified_products
                    WHERE name_embedding IS NOT NULL
                    {dietary_clause}
                    ORDER BY distance ASC
                    LIMIT %s
                """, (vector_str, limit))
                
                nearest_products = cur.fetchall()
                
                if not nearest_products:
                    logger.info("No se encontraron productos indexados con embeddings.")
                    return []
                
                # 3. Obtener ofertas asociadas de store_products para los productos unificados encontrados
                product_ids = [p["id"] for p in nearest_products]
                
                cur.execute("""
                    SELECT unified_product_id, store_id, product_url, base_price, in_stock, promotions_json, image_url, last_updated
                    FROM store_products
                    WHERE unified_product_id = ANY(%s)
                """, (product_ids,))

                store_products = cur.fetchall()

        # 4. Agrupar ofertas por unified_product_id
        offers_by_product: Dict[str, List[Dict[str, Any]]] = {}
        for sp in store_products:
            prod_id = sp["unified_product_id"]
            if prod_id not in offers_by_product:
                offers_by_product[prod_id] = []
                
            # Parsear promociones JSON
            promotions = []
            if sp["promotions_json"]:
                # psycopg puede devolver el json como dict/list directamente o como string.
                # Aseguramos parseo tolerante a fallos.
                raw_promos = sp["promotions_json"]
                if isinstance(raw_promos, str):
                    import json
                    try:
                        raw_promos = json.loads(raw_promos)
                    except Exception:
                        raw_promos = []
                
                if isinstance(raw_promos, list):
                    for rp in raw_promos:
                        # Mapear campos de la promo cruda al formato estandarizado de la spec
                        promotions.append({
                            "promo_id": rp.get("promo_id") or rp.get("id"),
                            "type": rp.get("type") or rp.get("promo_type"),
                            "description": rp.get("description") or rp.get("name"),
                            "required_quantity": rp.get("required_quantity"),
                            "free_quantity": rp.get("free_quantity"),
                            "discount_percentage_on_next": rp.get("discount_percentage_on_next") or rp.get("discount"),
                            "requires_membership": rp.get("requires_membership"),
                            "valid_until": rp.get("valid_until")
                        })
            
            offers_by_product[prod_id].append({
                "store_id": sp["store_id"],
                "product_url": sp["product_url"],
                "base_price": float(sp["base_price"]) if sp["base_price"] is not None else 0.0,
                "in_stock": bool(sp["in_stock"]),
                "last_updated": sp["last_updated"].isoformat() if sp["last_updated"] else None,
                "image_url": sp.get("image_url"),
                "promotions": promotions
            })

        # 5. Estructurar la respuesta final de búsqueda
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
                "distance": float(p["distance"]),
                "available_at_stores": offers_by_product.get(prod_id, [])
            })
            
        return results

    except Exception as e:
        logger.error(f"Error interno durante la búsqueda semántica: {e}")
        raise HTTPException(status_code=500, detail=f"Error interno en el servidor: {e}")

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

@app.post("/optimize")
def optimize_shopping_cart(request: OptimizationRequest):
    """
    Recibe un carrito y devuelve la asignación óptima de supermercados 
    considerando mínimos de compra, envíos y descuentos bancarios.
    """
    logger.info(f"Recibida solicitud de optimización para {len(request.cart)} productos.")
    
    try:
        cart_data = [item.model_dump() for item in request.cart]
        
        result = optimize_cart(
            cart_items=cart_data,
            user_memberships=request.user_memberships,
            user_cards=request.user_cards,
            delivery_costs=request.delivery_costs
        )

        if result.get("status") == "success":
            try:
                db = SmartCartDB()
                flat_prices = flatten_cart_prices(cart_data, request.user_memberships)
                stores = list(request.delivery_costs.keys()) if request.delivery_costs else ["coto_online", "dia_online"]
                
                bank_promos = {
                    "coto_online": [{"card": "galicia", "discount_pct": 20, "cap": 5000}],
                    "dia_online": [{"card": "macro", "discount_pct": 15, "cap": 3000}]
                }

                single_store_baselines = {}
                replaced_items_info = {s: [] for s in stores}
                suggestions = []
                # Se inicializa acá y no dentro del `if neighbor_candidates:` de más
                # abajo: se lee incondicionalmente al armar la respuesta, así que un
                # carrito sin vecinos en la misma góndola tiraba NameError, que el
                # except ancho se comía llevándose puesto single_store_baselines.
                # El orden de inserción del dict es el de ahorro descendente.
                grouped_suggestions = {}
                neighbor_candidates = []
                uid_to_name = {}
                
                # UNIFICAMOS TODO BAJO UNA ÚNICA CONEXIÓN A LA BD
                with psycopg.connect(db.conn_string, row_factory=dict_row) as conn:
                    with conn.cursor() as cur:
                        
                        # --- 1. CÁLCULO DE BASELINE CON REEMPLAZOS ---
                        for store in stores:
                            store_subtotal = 0
                            for item in request.cart:
                                uid = item.unified_id
                                qty = item.quantity
                                
                                if uid in flat_prices and store in flat_prices[uid]:
                                    store_subtotal += flat_prices[uid][store]["total_cost"]
                                else:
                                    # Extraemos también los tags/categoría para no sugerir locuras
                                    cur.execute("SELECT name_embedding, name, category, tags FROM unified_products WHERE id = %s", (uid,))
                                    p = cur.fetchone()

                                    if p and p["name_embedding"]:
                                        # Forzamos misma góndola vía tags de taxonomía
                                        aisle_clause, aisle_param = _same_aisle_filter(p, alias="u")
                                        cur.execute(f"""
                                            SELECT u.id, u.name
                                            FROM unified_products u
                                            JOIN store_products sp ON u.id = sp.unified_product_id
                                            WHERE sp.store_id = %s AND sp.in_stock = TRUE AND u.name_embedding IS NOT NULL
                                            {aisle_clause}
                                            ORDER BY u.name_embedding <=> %s ASC
                                            LIMIT 1
                                        """, (store, aisle_param, p["name_embedding"]))
                                        fallback = cur.fetchone()
                                        
                                        if fallback:
                                            fallback_uid = fallback["id"]
                                            fallback_flat = flatten_cart_prices([{"unified_id": fallback_uid, "quantity": qty}], request.user_memberships)
                                            
                                            if fallback_uid in fallback_flat and store in fallback_flat[fallback_uid]:
                                                store_subtotal += fallback_flat[fallback_uid][store]["total_cost"]
                                                replaced_items_info[store].append({
                                                    "original": p["name"],
                                                    "replacement": fallback["name"]
                                                })
                            
                            delivery = request.delivery_costs.get(store, 3000) if request.delivery_costs else 3000
                            baseline_discount = 0
                            best_promo = next((p for p in bank_promos.get(store, []) if p["card"] in request.user_cards), None)
                            if best_promo:
                                raw_disc = store_subtotal * (best_promo["discount_pct"] / 100.0)
                                baseline_discount = min(raw_disc, best_promo["cap"])
                            
                            total_baseline = store_subtotal + delivery - baseline_discount
                            single_store_baselines[store] = round(total_baseline, 2)
                
                        result["single_store_baselines"] = single_store_baselines
                        result["baseline_replacements"] = replaced_items_info
                        
                        # --- 2. FEATURE: SUGERENCIAS SEMÁNTICAS DE AHORRO PROPORCIONAL ---
                        for item in request.cart:
                            # 1. Agregamos las columnas de peso y unidad al SELECT original
                            cur.execute("SELECT name, name_embedding, category, tags, total_volume_weight, unit_type FROM unified_products WHERE id = %s", (item.unified_id,))
                            p = cur.fetchone()
                            
                            if p and p["name_embedding"]:
                                # 2. Usamos los datos directos de la BD con un fallback de seguridad
                                uid_to_name[item.unified_id] = {
                                    "name": p["name"],
                                    "weight": float(p["total_volume_weight"]) if p["total_volume_weight"] else 1.0,
                                    "unit": p["unit_type"] or "un",
                                    "category": p["category"]
                                }
                                
                                # 3. Agregamos las columnas de peso y unidad al SELECT de los vecinos
                                aisle_clause, aisle_param = _same_aisle_filter(p)
                                cur.execute(f"""
                                    SELECT id, name, total_volume_weight, unit_type
                                    FROM unified_products
                                    WHERE id != %s AND name_embedding IS NOT NULL
                                    {aisle_clause}
                                    ORDER BY name_embedding <=> %s ASC
                                    LIMIT 3
                                """, (item.unified_id, aisle_param, p["name_embedding"]))
                                
                                for n in cur.fetchall():
                                    # 4. Asignamos directo desde el resultado SQL del vecino
                                    neighbor_candidates.append({
                                        "original_uid": item.unified_id,
                                        "suggested_uid": n["id"],
                                        "suggested_name": n["name"],
                                        "quantity": item.quantity,
                                        "suggested_weight": float(n["total_volume_weight"]) if n["total_volume_weight"] else 1.0,
                                        "suggested_unit": n["unit_type"] or "un"
                                    })
                        
                        # --- 3. FEATURE: LINK DE PRODUCTO POR ÍTEM, PARA TODAS LAS TIENDAS ---
                        # Día tiene además un magic link de carrito completo (más abajo); para
                        # el resto (ej. Coto, que no expone un endpoint de carrito por URL) esto
                        # permite al usuario abrir cada producto individualmente.
                        for store_id, store_result in result.get("split", {}).items():
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

                                # Promo efectivamente aplicada a esta línea, para que el
                                # desglose del frontend pueda explicar de dónde sale el
                                # total_cost en vez de mostrar un número sin justificar.
                                # `flat_prices` es el flatten del carrito calculado arriba
                                # (todavía no fue rebindeado con los candidatos a sugerencia).
                                line_flat = flat_prices.get(p["unified_id"], {}).get(store_id)
                                if line_flat:
                                    p["applied_promo_id"] = line_flat["applied_promo_id"]
                                    p["promo_description"] = line_flat["promo_description"]
                                    p["effective_unit_price"] = line_flat["effective_unit_price"]

                        # --- 4. FEATURE: MAGIC LINK PARA DÍA ONLINE ---
                        if "dia_online" in result.get("split", {}):
                            dia_products = result["split"]["dia_online"]["products"]
                            uids_dia = [p["unified_id"] for p in dia_products]
                            
                            if uids_dia:
                                cur.execute("""
                                    SELECT unified_product_id, store_sku 
                                    FROM store_products 
                                    WHERE store_id = 'dia_online' AND unified_product_id = ANY(%s)
                                """, (uids_dia,))
                                
                                sku_map = {row["unified_product_id"]: row["store_sku"] for row in cur.fetchall()}
                                
                                link_payload = []
                                for p in dia_products:
                                    if p["unified_id"] in sku_map:
                                        link_payload.append({
                                            "store_sku": sku_map[p["unified_id"]],
                                            "quantity": p["quantity"]
                                        })
                                
                                if link_payload:
                                    magic_link = generate_vtex_magic_link(
                                        store_domain="diaonline.supermercadosdia.com.ar",
                                        products=link_payload
                                    )
                                    result["split"]["dia_online"]["checkout_url"] = magic_link
                                    
                # --- PROCESAMIENTO FINAL DE SUGERENCIAS SEMÁNTICAS (Fuera del cursor) ---
                if neighbor_candidates:
                    items_to_flatten = [{"unified_id": c["suggested_uid"], "quantity": c["quantity"]} for c in neighbor_candidates]
                    items_to_flatten.extend(cart_data)
                    flat_prices = flatten_cart_prices(items_to_flatten, request.user_memberships)
                    
                    for cand in neighbor_candidates:
                        orig_uid = cand["original_uid"]
                        sugg_uid = cand["suggested_uid"]
                        
                        if orig_uid not in flat_prices or sugg_uid not in flat_prices: continue
                        
                        orig_min_cost = min([flat_prices[orig_uid][s]["total_cost"] for s in flat_prices[orig_uid]])
                        sugg_min_cost = min([flat_prices[sugg_uid][s]["total_cost"] for s in flat_prices[sugg_uid]])
                        
                        orig_info = uid_to_name[orig_uid]
                        orig_weight = orig_info["weight"]
                        orig_unit = orig_info["unit"]
                        sugg_weight = cand["suggested_weight"]
                        sugg_unit = cand["suggested_unit"]

                        # Solo calculamos si las unidades son lógicamente comparables
                        if orig_unit == sugg_unit or (orig_unit in ['g', 'ml'] and sugg_unit in ['g', 'ml']):
                            
                            sugg_cost_per_unit = sugg_min_cost / sugg_weight
                            sugg_proportional_cost = sugg_cost_per_unit * orig_weight
                            
                            savings_proportional = orig_min_cost - sugg_proportional_cost
                            
                            # Formateo de UI para volver a Litros o Kilos si es grande
                            display_weight = orig_weight
                            display_unit = orig_unit
                            if display_unit == 'g' and display_weight >= 1000:
                                display_weight /= 1000
                                display_unit = 'Kg'
                            elif display_unit == 'ml' and display_weight >= 1000:
                                display_weight /= 1000
                                display_unit = 'L'
                            
                            # Subimos el umbral a 20% para limpiar ruido
                            if savings_proportional > (orig_min_cost * 0.2):
                                sugg_min_unit_price = min(
                                    flat_prices[sugg_uid][s]["effective_unit_price"]
                                    for s in flat_prices[sugg_uid]
                                )
                                suggestions.append({
                                    "original_uid": orig_uid,
                                    "original_product": orig_info["name"],
                                    "suggested_product": cand["suggested_name"],
                                    "savings": round(savings_proportional, 2),
                                    "suggested_uid": sugg_uid,
                                    "effective_unit_price": sugg_min_unit_price,
                                    "metric_info": f"a igual cantidad de {display_weight} {display_unit.upper()}"
                                })

                    # Agrupamos por producto original en vez de devolver una lista plana.
                    # El dedupe global por suggested_uid con tope de 5 que había antes
                    # recortaba alternativas de forma impredecible: un producto podía
                    # quedarse sin ninguna porque otro se había llevado el cupo.
                    suggestions = sorted(suggestions, key=lambda x: x["savings"], reverse=True)
                    for s in suggestions:
                        group = grouped_suggestions.get(s["original_uid"])
                        if group is None:
                            group = {
                                "original_uid": s["original_uid"],
                                "original_product": s["original_product"],
                                "alternatives": []
                            }
                            grouped_suggestions[s["original_uid"]] = group

                        if len(group["alternatives"]) >= 3:
                            continue
                        if any(a["suggested_uid"] == s["suggested_uid"] for a in group["alternatives"]):
                            continue

                        group["alternatives"].append({
                            "suggested_uid": s["suggested_uid"],
                            "suggested_product": s["suggested_product"],
                            "savings": s["savings"],
                            "effective_unit_price": s["effective_unit_price"],
                            "metric_info": s["metric_info"]
                        })

                result["suggestions"] = list(grouped_suggestions.values())

            except Exception as e:
                logger.error(f"Error generando analíticas post-optimización: {e}")
                result["suggestions"] = []
                if "single_store_baselines" not in result:
                    result["single_store_baselines"] = {}

    except Exception as e:
        logger.error(f"Error en el motor de optimización: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    if result.get("status") == "infeasible":
        msg = result.get("message", "El carrito no alcanza los montos mínimos requeridos por las tiendas ($15.000 Coto / $12.000 Día). Agregá más productos.")
        raise HTTPException(status_code=400, detail=msg)
        
    return result

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
        dietary_clause = _dietary_filter_clause(gluten_free, vegan)
        with psycopg.connect(db.conn_string, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT id, ean, name, brand, category, units_per_pack, unit_type, total_volume_weight,
                           is_gluten_free, is_vegan,
                           0.0 AS distance
                    FROM unified_products
                    WHERE category = %s
                    {dietary_clause}
                    LIMIT %s
                """, (category_name, limit))
                nearest_products = cur.fetchall()

                if not nearest_products:
                    return []

                product_ids = [p["id"] for p in nearest_products]
                
                # LA CLAVE ESTÁ ACÁ: Nos aseguramos de que 'image_url' esté en el SELECT
                cur.execute("""
                    SELECT unified_product_id, store_id, product_url, base_price, in_stock, promotions_json, image_url, last_updated
                    FROM store_products
                    WHERE unified_product_id = ANY(%s)
                """, (product_ids,))
                store_products = cur.fetchall()

        offers_by_product = {}
        for sp in store_products:
            prod_id = sp["unified_product_id"]
            if prod_id not in offers_by_product:
                offers_by_product[prod_id] = []
            
            promotions = []
            if sp["promotions_json"]:
                raw_promos = sp["promotions_json"]
                if isinstance(raw_promos, str):
                    import json
                    try: raw_promos = json.loads(raw_promos)
                    except: raw_promos = []
                
                if isinstance(raw_promos, list):
                    for rp in raw_promos:
                        promotions.append({
                            "promo_id": rp.get("promo_id") or rp.get("id"),
                            "type": rp.get("type") or rp.get("promo_type"),
                            "description": rp.get("description") or rp.get("name"),
                            "required_quantity": rp.get("required_quantity"),
                            "free_quantity": rp.get("free_quantity"),
                            "discount_percentage_on_next": rp.get("discount_percentage_on_next") or rp.get("discount"),
                            "requires_membership": rp.get("requires_membership"),
                            "valid_until": rp.get("valid_until")
                        })
            
            offers_by_product[prod_id].append({
                "store_id": sp["store_id"],
                "product_url": sp["product_url"],
                "base_price": float(sp["base_price"]) if sp["base_price"] is not None else 0.0,
                "in_stock": bool(sp["in_stock"]),
                "last_updated": sp["last_updated"].isoformat() if sp["last_updated"] else None,
                "image_url": sp.get("image_url"), # Extracción segura de la base de datos
                "promotions": promotions
            })

        results = []
        for p in nearest_products:
            prod_id = p["id"]
            offers = offers_by_product.get(prod_id, [])
            
            # --- CALCULAR PRECIO MÍNIMO ---
            min_price = min([o["base_price"] for o in offers if o["base_price"] > 0], default=0.0)
            
            # --- PRIORIZAR IMAGEN DE COTO ---
            best_image = None
            coto_offer = next((o for o in offers if o["store_id"] == "coto_online" and o.get("image_url")), None)
            dia_offer = next((o for o in offers if o["store_id"] == "dia_online" and o.get("image_url")), None)
            
            if coto_offer:
                best_image = coto_offer["image_url"]
            elif dia_offer:
                best_image = dia_offer["image_url"]

            results.append({
                "unified_id": prod_id,
                "ean": p["ean"],
                "name": p["name"],
                "brand": p["brand"],
                "category": p["category"],
                "min_price": min_price,
                "image_url": best_image,
                "is_gluten_free": bool(p["is_gluten_free"]),
                "is_vegan": bool(p["is_vegan"]),
                "unit_info": {
                    "units_per_pack": p["units_per_pack"],
                    "unit_type": p["unit_type"],
                    "total_volume_weight": float(p["total_volume_weight"]) if p["total_volume_weight"] is not None else None
                },
                "distance": 0.0,
                "available_at_stores": offers
            })
        return results
    except Exception as e:
        logger.error(f"Error en búsqueda por categoría: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api:app", host="127.0.0.1", port=8000, reload=True)
