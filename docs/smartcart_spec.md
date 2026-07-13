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

## 3. Modelo de Datos Unificado (JSON Maestro de Producción)

Este formato consolidado representa la estructura limpia y corregida que se consume en la etapa de pre-procesamiento del optimizador:

```json
{
  "unified_id": "prod_7790000000123",
  "ean": "7790000000123",
  "name": "Hamburguesa Paty Clásica 4x80g",
  "brand": "Paty",
  "category": "congelados_hamburguesas",
  "unit_info": {
    "units_per_pack": 4,
    "unit_type": "gr",
    "total_volume_weight": 320.0
  },
  "embedding": [0.012, -0.045, 0.821, 0.114],
  "available_at_stores": [
    {
      "store_id": "coto_online",
      "product_url": "https://www.cotodigital3.com.ar/sitios/cdigi/producto?id=123",
      "base_price": 2500.0,
      "in_stock": true,
      "last_updated": "2026-07-02T14:30:00Z",
      "promotions": [
        {
          "promo_id": "coto_paty_3x2",
          "type": "multi_buy",
          "description": "Llevando 3 pagás 2",
          "required_quantity": 3,
          "free_quantity": 1,
          "discount_percentage_on_next": 0.0,
          "requires_membership": null,
          "valid_until": "2026-07-05T23:59:59Z"
        }
      ]
    },
    {
      "store_id": "dia_online",
      "product_url": "https://diaonline.supermercadosdia.com.ar/producto/456",
      "base_price": 2700.0,
      "in_stock": true,
      "last_updated": "2026-07-02T15:10:00Z",
      "promotions": [
        {
          "promo_id": "dia_paty_2da_50",
          "type": "conditional_discount",
          "description": "50% de descuento en la 2da unidad con Club Día",
          "required_quantity": 2,
          "free_quantity": 0,
          "discount_percentage_on_next": 50.0,
          "requires_membership": "club_dia",
          "valid_until": "2026-07-07T23:59:59Z"
        }
      ]
    }
  ]
}
```
