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

@app.post("/optimize")
def optimize_shopping_cart(request: OptimizationRequest):
    """
    Recibe un carrito y devuelve la asignación óptima de supermercados 
    considerando mínimos de compra, envíos y descuentos bancarios.
    """
    logger.info(f"Recibida solicitud de optimización para {len(request.cart)} productos.")
    
    try:
        # Convertimos los objetos Pydantic a lista de dicts para el optimizer
        cart_data = [item.model_dump() for item in request.cart]
        
        result = optimize_cart(
            cart_items=cart_data,
            user_memberships=request.user_memberships,
            user_cards=request.user_cards,
            delivery_costs=request.delivery_costs
        )
    except Exception as e:
        # Solo capturamos errores reales de código matemático o de servidor
        logger.error(f"Error en el motor de optimización: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    # FUERA del try/except: Manejo de reglas de negocio (mínimos no alcanzados)
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
