# Especificación Técnica y Roadmap Simplificado: SmartCart Argentina

SmartCart es un Motor de Recomendación y Optimización de Canastas de Compra diseñado para mitigar el impacto de la dispersión de precios en supermercados mediante programación por restricciones y procesamiento de lenguaje natural (NLP). El sistema resuelve el problema de optimización combinatoria de minimizar el costo total de una lista de compras, considerando precios base, promociones complejas, membresías vigentes del usuario y umbrales de compra mínima por cadena.

---

## 1. Arquitectura y Componentes Core

### A. Pipeline de Ingesta y Unificación Nativa Relacional
El sistema recopila datos crudos mediante el scraping directo de las APIs internas (XHR/Fetch) de las plataformas web de los supermercados. La unificación y estructuración sigue un enfoque puramente relacional y determinista:

*   **Ingesta por Consumo de APIs Internas:** Se utilizan módulos de extracción en Python con `httpx` que interactúan de forma nativa con los endpoints de catálogo. Para *Coto Online*, el script itera categorías y maneja la paginación. Para *Día Online*, se integra con la infraestructura REST de VTEX para la extracción automatizada del árbol de taxonomías y el consumo de sus endpoints de búsqueda mediante firmas de paginación por índices.
*   **Unificación Nativa por Identificador Global (EAN):** Dado que la cobertura de códigos EAN en las APIs de Coto y Día es del 100%, la persistencia delega la unificación primaria directamente al motor de la base de datos (PostgreSQL). Utilizando el código EAN de 13 dígitos (`VARCHAR` para preservar ceros a la izquierda), el sistema genera llaves maestras únicas. Las colisiones en la ingesta se resuelven mediante cláusulas `ON CONFLICT` en SQL: si el EAN ya existe, el registro maestro permanece intacto y el nuevo precio/stock se inserta en la tabla de instancias vinculada al mismo identificador común. Esto elimina la necesidad de algoritmos de macheo semántico difuso para la unificación del catálogo.

### B. Indexación Semántica para la Búsqueda (pgvector)
Para resolver la carga de la lista de compras de manera ágil y sin dependencias pesadas de infraestructura externa, el sistema aprovecha las capacidades de la base de datos relacional mediante un esquema enfocado exclusivamente en la interfaz de usuario:

1.  **Fase de Recuperación (Retrieve):** Las descripciones de los productos unificados se convierten en vectores de 384 dimensiones mediante el modelo local de NLP `all-MiniLM-L6-v2`. Estos vectores se almacenan en una columna de tipo `vector` en PostgreSQL usando la extensión `pgvector`. Cuando el usuario escribe texto libre en la barra de búsqueda (ej. *"Puré de papas"*), consultas SQL nativas de distancia de coseno extraen en milisegundos los 20 o 30 vecinos semánticos más cercanos.
2.  **Fase de Clasificación (Rank):** Sobre este subconjunto acotado de candidatos, se aplica en memoria (usando Python/Pandas) una métrica híbrida de negocio que balancea la distancia semántica con la conveniencia de precio actual, traduciendo la intención de búsqueda del usuario a un EAN específico del catálogo de forma transparente.

### C. Motor de Restricciones y Pre-procesamiento (Google OR-Tools)
Para mantener la experiencia fluida y evitar sobrecargar la matriz del solver con restricciones no lineales complejas, el motor delega la lógica de promociones y fidelización a una etapa previa de aplanamiento de datos en Python:

*   **Aplanamiento de Membresías y Promociones Complejas:** Antes de invocar al optimizador, el sistema "plancha" el catálogo según el contexto del usuario (billeteras virtuales, Club Día, Comunidad Coto) y la cantidad demandada de cada producto. Las promociones de compra múltiple (2x1, 3x2, 50% en la 2da unidad) se calculan en memoria evaluando el costo total empaquetado para la cantidad exacta solicitada. Al solver de OR-Tools ingresa una estructura lineal simplificada con el costo neto por supermercado para ese volumen específico.
*   **Modelado del Mínimo de Compra:** El optimizador (CP-SAT o MIP) evalúa las variables binarias de compra por tienda incorporando una penalización o restricción dura basada en los umbrales de compra mínima obligatorios de las cadenas. Si la suma de los productos asignados a una tienda $j$ es mayor que cero pero menor al mínimo requerido, el solver es forzado a descartar la división del carrito para esa cadena o reubicar los productos en otra tienda para garantizar la viabilidad del checkout.

---

## 2. Roadmap de Implementación (Hitos Funcionales)

| Fase / Duración | Objetivos de Ingeniería y Refinamientos | Entregable MVP |
| :--- | :--- | :--- |
| **Fase 1: Datos y Base Local** <br> *Semanas 1-3* | • Configuración de PostgreSQL en Docker-Compose.<br>• Desarrollo de scrapers con `httpx` para APIs internas de Coto y Día.<br>• Implementación del pipeline de unificación nativa relacional en BD mediante restricciones `ON CONFLICT` basadas estrictamente en el código EAN. | Base de datos relacional poblada y consistente con instancias comerciales unificadas automáticamente por EAN (vistas de comparación directa integradas en SQL). |
| **Fase 2: Motor de Similitud y Búsqueda** <br> *Semanas 4-5* | • Integración de `sentence-transformers` local para generar embeddings de las descripciones del catálogo.<br>• Indexación de vectores con `pgvector` en Postgres.<br>• Desarrollo de endpoints en FastAPI enfocados únicamente en la fase de *Retrieve* rápido para resolver texto libre del usuario contra el catálogo unificado. | Endpoint en FastAPI que recibe un string de búsqueda y extrae los vecinos semánticos directos desde SQL en milisegundos para poblar la UI. |
| **Fase 3: Optimización y Reglas de Negocio** <br> *Semanas 6-8* | • Desarrollo del componente intermedio de aplanamiento de promociones (2x1, 3x2, descuentos de membresía) en Pandas según cantidad pedida.<br>• Implementación del modelo matemático combinatorio en Google OR-Tools incluyendo la lógica de umbral de compra mínima por tienda. | Script core optimizado en Python que procesa una lista de compras real y resuelve la combinación óptima de tiendas para minimizar el gasto total respetando mínimos. |
| **Fase 4: Frontend de Simulación** <br> *Semanas 9-11* | • Desarrollo de la interfaz interactiva en Streamlit usando `st.session_state` para la gestión de canastas en tiempo real.<br>• Interfaz de checkout con visualización transparente del desglose de ahorros, alertas de mínimos no alcanzados y links de redirección directa. | MVP completo y funcional de la Web App corriendo de extremo a extremo en entorno local. |

---

## 2.1. Árbol de Categorías Real (Mega-Menú)

Además de `GET /categories` (lista plana de las 4 categorías normalizadas que existen en `unified_products.category`: Lácteos, Golosinas, Almacén, Otros), la API expone `GET /categories/tree`, que devuelve la taxonomía real de 2-3 niveles combinando las categorías ya scrapeadas de Coto y Día (`src/scrapers/coto_categories.json` y `dia_categories.json`), pensada para alimentar un mega-menú de navegación tipo e-commerce.

El árbol se construye una sola vez al arrancar la API (`src/category_tree.py`, cacheado en memoria) mergeando las categorías de ambas tiendas en capas: texto normalizado, contención de tokens significativos, similaridad semántica (reutilizando el modelo `all-MiniLM-L6-v2` ya cargado para `/search`) y una tabla chica de alias manuales para los casos puntuales que ninguna de las anteriores resuelve.

```json
{
  "Almacén": {
    "label": "Almacén",
    "has_direct_category_match": true,
    "subcategories": {
      "Golosinas": { "label": "Golosinas", "leaves": ["Alfajores", "Chocolates", "..."] }
    }
  },
  "Bebidas": {
    "label": "Bebidas",
    "has_direct_category_match": false,
    "subcategories": { "...": "..." }
  }
}
```

**Regla de ruteo para el frontend:** `has_direct_category_match` indica si ese top-level existe literalmente como valor de `unified_products.category` (hoy solo Lácteos, Golosinas y Almacén). Un click en esos top-levels debe resolverse vía `GET /category/{label}`. Cualquier otro click (subcategoría, leaf, o un top-level sin match directo — la mayoría, dado que el catálogo cargado hoy es acotado) debe resolverse vía `GET /search?q=<label>`, reutilizando la búsqueda semántica existente en lugar de requerir un match exacto de categoría.

---

## 3. Modelo de Datos Unificado (JSON Maestro de Producción)

Este formato consolidado representa la estructura limpia y corregida que se consume en la etapa de pre-procesamiento del optimizador:

```json
{
  "unified_id": "prod_7790742348005",
  "ean": "7790742348005",
  "name": "Leche Multidefensas 1% LA SERENISIMA Sachet 1l",
  "brand": "LA SERENISIMA",
  "category": "Lácteos",
  "image_url": "https://static.cotodigital3.com.ar/sitios/fotos/large/00539100/00539126.jpg",
  "min_price": 1975.0,
  "unit_info": {
    "units_per_pack": 1,
    "unit_type": "Ltr",
    "total_volume_weight": 1.0
  },
  "distance": 0.0,
  "available_at_stores": [
    {
      "store_id": "coto_online",
      "product_url": "https://www.cotodigital3.com.ar/...",
      "base_price": 1975.0,
      "in_stock": true,
      "last_updated": "2026-07-20T18:30:00Z",
      "image_url": "https://static.cotodigital3.com.ar/...",
      "promotions": [
        {
          "promo_id": "coto_promo_123",
          "type": "discount",
          "description": "15% de descuento con Comunidad Coto",
          "required_quantity": null,
          "free_quantity": null,
          "discount_percentage_on_next": 15.0,
          "requires_membership": "comunidad_coto",
          "valid_until": null
        }
      ]
    },
    {
      "store_id": "dia_online",
      "product_url": "https://diaonline.supermercadosdia.com.ar/...",
      "base_price": 1975.0,
      "in_stock": true,
      "last_updated": "2026-07-20T18:31:00Z",
      "image_url": "https://diaio.vtexassets.com/...",
      "promotions": []
    }
  ]
}
```

### 3.1. Tags estrictos de góndola

Además de `category` (los 4 buckets gruesos de `SmartCartDB.CATEGORY_MAP`), `unified_products` guarda `tags TEXT[]`: la ruta jerárquica completa de la categoría, slugificada.

```
"Almacén -> Golosinas -> Alfajores"  ->  ["almacen", "golosinas", "alfajores"]
```

La ruta sale del dump de taxonomía de cada tienda (`src/scrapers/*_categories.json`), que está indexado por la misma clave que los scrapers ya iteran: el `category_id` de Coto y el slug de Día. No hay requests extra ni heurísticas sobre el nombre del producto.

El motivo es que `category` no sirve como guarda de "misma góndola": mapea etiquetas hoja a través de un dict de 9 claves, así que sobre el catálogo completo el 98 % de las categorías reales cae en `Otros`, mezclando mayonesa con condimentos para carne. Los tags, en cambio, vienen de ramas distintas de la taxonomía y no pueden colisionar.

La comparación de góndolas está centralizada en `category_tags.same_aisle_filter()`, que arma la cláusula SQL y la consumen tanto las sugerencias de `api.py` como la heurística de cierre de tienda (`strategic_swaps.py`). Usa el operador de **solapamiento** de Postgres (`&&`, índice GIN) sobre los segmentos **no top-level** (`category_tags.filter_tags()`), no containment ni prefijo de rama. La razón es que las tiendas anidan a distinta profundidad:

| | `tags` | segmentos de comparación |
|---|---|---|
| Leche Coto | `[frescos, lacteos, leches]` | `[lacteos, leches]` |
| Leche Día | `[frescos, leches]` | `[leches]` |

Solapan en `leches` y son sustituibles; un filtro por prefijo de rama fallaría acá. Descartar el top-level es lo que evita que `almacen` matchee contra medio catálogo. Cuando un producto todavía no tiene tags, la comparación cae al filtro por `category` anterior.

### 3.2. Atributos dietarios

`unified_products` expone dos booleanos, poblados por los scrapers vía `src/dietary_parser.py`:

- `is_gluten_free` — `sin tacc`, `sin t.a.c.c`, `libre de gluten`, `sin gluten`, `gluten free`.
- `is_vegan` — `vegano`/`vegana`, `plant based`, `100% vegetal`.

**`FALSE` significa "sin evidencia explícita", no "contiene gluten" ni "no es vegano".** Un flag solo se pone en `TRUE` cuando aparece una frase completa en el texto disponible; nunca se infiere a partir de la categoría, porque un falso positivo acá tiene consecuencias reales para alguien celíaco. Los tokens sueltos `gluten` y `vegetal` están excluidos a propósito (darían positivo en "contiene gluten" y en "Sémola Vegetales Vitina Luchetti").

La evidencia se busca **solo en texto que describe a ese producto**: nombre, marca, ruta de categoría y los campos estructurados que la tienda le asigna (del lado de Día, `properties` —la property `Otros` suele traer `"Sin Tacc"`— y `clusterHighlights`, leídos de forma defensiva porque la query es persisted y pueden no venir).

**Las descripciones de marketing (`description`, `metaTagDescription`) están excluidas a propósito.** Enumeran productos hermanos de la misma línea: la del *Ketchup Hellmann's Regular* incluye `"...mayonesa hellmann's light, clásica, suave, vegana, oliva..."` y hacía que el ketchup se marcara como vegano. Ninguna regla de frases evita ese caso —el reclamo es legítimo, pero es sobre otro producto—, así que la única defensa es no mirar ese texto. Medido sobre 196 productos de Día, el texto libre aportaba +5 detecciones de gluten y 1 sola de vegano, que era precisamente ese falso positivo; los campos estructurados aportan el 92 % de la señal.

Los flags se **pisan** en cada scrapeo (`EXCLUDED`), no se acumulan con `OR`. Acumular preservaría la evidencia de ambas tiendas, pero volvería los flags monotónicos: un falso positivo no se podría corregir nunca, ni siquiera arreglando el parser. La asimetría de riesgo decide: un `FALSE` de más solo significa "sin evidencia", mientras que un `TRUE` de más es el error que hace daño.
