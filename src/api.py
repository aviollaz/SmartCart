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
    unit_info: UnitInfo
    distance: float = Field(..., description="Distancia de coseno con respecto a la búsqueda (menor es más similar)")
    available_at_stores: List[StoreOffer] = []

class CartItem(BaseModel):
    unified_id: str
    quantity: int

class OptimizationRequest(BaseModel):
    cart: List[CartItem]
    user_memberships: Optional[List[str]] = []
    user_cards: Optional[List[str]] = []
    # En el futuro la dirección determinará los costos, ahora los pasamos opcionales
    delivery_costs: Optional[Dict[str, float]] = None

# Estado global para mantener el modelo cargado en memoria
ml_models = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Carga del modelo sentence-transformer en startup
    logger.info("Cargando modelo SentenceTransformer 'all-MiniLM-L6-v2'...")
    ml_models["model"] = SentenceTransformer("all-MiniLM-L6-v2")
    logger.info("Modelo SentenceTransformer cargado exitosamente.")
    
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
    limit: int = Query(20, description="Cantidad máxima de resultados (entre 1 y 50)", ge=1, le=50)
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
        
        # 2. Consultar vecinos más cercanos en PostgreSQL usando la distancia de coseno (<=>)
        # Traemos también los detalles del producto unificado
        with psycopg.connect(db.conn_string, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, ean, name, brand, category, units_per_pack, unit_type, total_volume_weight,
                           name_embedding <=> %s AS distance
                    FROM unified_products
                    WHERE name_embedding IS NOT NULL
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
                    SELECT unified_product_id, store_id, product_url, base_price, in_stock, promotions_json, last_updated
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

def extract_real_volume(name: str) -> tuple[float, str]:
    """
    Parsea el nombre del producto para extraer el volumen real usando Regex.
    Normaliza todo a gramos (g) o mililitros (ml) para poder comparar magnitudes.
    """
    match = re.search(r'(\d+(?:[,.]\d+)?)\s*(kg|gr|grm|g|l|ltr|ml|cc)\b', name, re.IGNORECASE)
    if match:
        try:
            val = float(match.group(1).replace(',', '.'))
            u = match.group(2).lower()
            if u in ['kg']: return val * 1000.0, 'g'
            if u in ['l', 'ltr']: return val * 1000.0, 'ml'
            if u in ['gr', 'grm', 'g']: return val, 'g'
            if u in ['ml', 'cc']: return val, 'ml'
        except ValueError:
            pass
    return 1.0, 'un' # Fallback si no encuentra patrón

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
                                    # Extraemos también la categoría para no sugerir locuras
                                    cur.execute("SELECT name_embedding, name, category FROM unified_products WHERE id = %s", (uid,))
                                    p = cur.fetchone()
                                    
                                    if p and p["name_embedding"]:
                                        # Agregamos AND u.category = %s para forzar misma góndola
                                        cur.execute("""
                                            SELECT u.id, u.name
                                            FROM unified_products u
                                            JOIN store_products sp ON u.id = sp.unified_product_id
                                            WHERE sp.store_id = %s AND sp.in_stock = TRUE AND u.name_embedding IS NOT NULL
                                            AND u.category = %s
                                            ORDER BY u.name_embedding <=> %s ASC
                                            LIMIT 1
                                        """, (store, p["category"], p["name_embedding"]))
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
                            cur.execute("SELECT name, name_embedding, category FROM unified_products WHERE id = %s", (item.unified_id,))
                            p = cur.fetchone()
                            if p and p["name_embedding"]:
                                # Extraemos el peso usando nuestra Regex sobre el string del nombre
                                real_weight, real_unit = extract_real_volume(p["name"])
                                
                                uid_to_name[item.unified_id] = {
                                    "name": p["name"],
                                    "weight": real_weight,
                                    "unit": real_unit,
                                    "category": p["category"]
                                }
                                
                                cur.execute("""
                                    SELECT id, name
                                    FROM unified_products
                                    WHERE id != %s AND name_embedding IS NOT NULL
                                    AND category = %s
                                    ORDER BY name_embedding <=> %s ASC
                                    LIMIT 2
                                """, (item.unified_id, p["category"], p["name_embedding"]))
                                
                                for n in cur.fetchall():
                                    cand_weight, cand_unit = extract_real_volume(n["name"])
                                    neighbor_candidates.append({
                                        "original_uid": item.unified_id,
                                        "suggested_uid": n["id"],
                                        "suggested_name": n["name"],
                                        "quantity": item.quantity,
                                        "suggested_weight": cand_weight,
                                        "suggested_unit": cand_unit
                                    })
                
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
                            
                            # Filtro léxico anti-locuras: Si el original tiene "polvo", la sugerencia debe tener "polvo"
                            # Esto mata el caso extremo del Dulce de Leche si la matemática llegara a fallar.
                            if "polvo" in orig_info["name"].lower() and "polvo" not in cand["suggested_name"].lower():
                                continue
                            
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
                            
                            # Subimos el umbral a 15% para limpiar ruido
                            if savings_proportional > (orig_min_cost * 0.15): 
                                suggestions.append({
                                    "original_product": orig_info["name"],
                                    "suggested_product": cand["suggested_name"],
                                    "savings": round(savings_proportional, 2),
                                    "suggested_uid": sugg_uid,
                                    "metric_info": f"a igual cantidad de {display_weight} {display_unit.upper()}"
                                })
                    
                    suggestions = sorted(suggestions, key=lambda x: x["savings"], reverse=True)
                    unique_suggestions = []
                    seen_sugg = set()
                    for s in suggestions:
                        if s["suggested_uid"] not in seen_sugg:
                            unique_suggestions.append(s)
                            seen_sugg.add(s["suggested_uid"])
                            if len(unique_suggestions) >= 5: break
                            
                result["suggestions"] = unique_suggestions

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
def get_products_by_category(category_name: str, limit: int = 50):
    """Devuelve productos filtrados por una categoría exacta."""
    try:
        db = SmartCartDB()
        with psycopg.connect(db.conn_string, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, ean, name, brand, category, units_per_pack, unit_type, total_volume_weight,
                           0.0 AS distance
                    FROM unified_products
                    WHERE category = %s
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
