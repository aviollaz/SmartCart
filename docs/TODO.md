# TODO / Roadmap

Ideas pendientes, ordenadas por relación impacto-costo dentro de cada sección.
Cada ítem dice **dónde** toca y **por qué** — la mitad del trabajo de un TODO es
que el que lo agarre no tenga que redescubrir el razonamiento.

Convención: los ítems marcados **[hipótesis]** no están verificados contra la
base; los demás salen de mediciones o de código leído.

---

## Producto

### 1. "Comprar de nuevo" / mis habituales
Entre el 60% y el 80% de un carrito de supermercado es recompra, así que el
historial personal es la señal más fuerte que existe en el rubro — más que
cualquier mejora del embedding. No necesita ML.

`CartContext` ya persiste el carrito en `localStorage`, así que el salto es
guardar **historial** de carritos optimizados, no solo el estado actual.
Cuidado con una cosa: `smartcart_profile_v1` está versionado y el historial
puede crecer sin techo, así que conviene un límite de N carritos.

### 2. Precio por unidad de medida (por 100 g / por litro)
Para una app cuyo propósito **es** comparar precios, esta es la primitiva de
comparación y hoy no está expuesta en ningún lado. En UK es obligatorio por ley
mostrarlo.

Sale de una división: `total_volume_weight` y `unit_type` ya están normalizados
(y el invariante `'g'|'ml'|'un'` de la etapa 2 de CLAUDE.md es justamente lo que
lo hace calculable). Ojo con `unit_type = 'un'`, donde no aplica, y con los
multipacks — ver la discusión de `extract_pack_count()` en la etapa 7: el número
al lado del `xN` a veces es el total del pack y a veces el tamaño unitario, así
que un precio por gramo derivado de un multipack puede mentir.

### 3. Progreso hacia el mínimo de compra, en vivo
Hoy el usuario descubre que el carrito es inviable **recién al optimizar**, que
es la peor fricción del flujo y además es la KPI que mide el analyzer
(`% carritos inviables`).

`DEFAULT_MIN_SPEND_LIMITS` vive en `src/optimizer.py` y el frontend ya llama a
`POST /price-preview` para la advertencia de cobertura. Falta convertir la
restricción dura en un indicador durante el armado.

### 4. Sustituciones pre-aprobadas
`src/strategic_swaps.py` ya calcula candidatos comparables; lo que falta no es
el algoritmo sino el **consentimiento previo** del usuario sobre qué reemplazo
acepta.

### 5. Presentación del split: mirar Kayak, no a los supermercados
El "Hacker Fare" de Kayak (dos pasajes de aerolíneas distintas porque sale más
barato que uno solo) es literalmente el mismo producto que el split de carrito,
**incluida la misma objeción del usuario**: "¿vale la pena la complicación?".
Cómo lo presentan —ahorro adelante, contrapartidas explícitas, comparación
contra la opción simple— es una solución ya diseñada al problema que
`BaselineComparison` está atacando.

Referencias más útiles que las cadenas locales: Instacart (mismo problema de
catálogo unificado multi-tienda, con blog de ingeniería público), Ocado, Picnic;
y los comparadores tipo Idealo / PriceSpy para el ranking de ofertas.

---

## Búsqueda y relevancia

Contexto: `GET /search` ya hace recuperar-y-reordenar en dos etapas con el bonus
por disponibilidad (`STORE_BONUS`, ver CLAUDE.md etapa 6). Lo que sigue es la
continuación natural.

### 6. Modelo multilingüe **[hipótesis]**
`all-MiniLM-L6-v2` está entrenado principalmente en inglés, y los números lo
sugieren: en el catálogo actual el resultado #1 de `yerba` está a distancia
**0.417**, `arroz` a **0.471** y `azucar` a **0.394**. Para queries que
coinciden casi literalmente con el nombre del producto, eso es altísimo — un
modelo alineado con el idioma debería dar bastante menos.

Probablemente rinda más que cualquier ajuste de `STORE_BONUS`. Costo: regenerar
los 6.336 embeddings y, si cambia la dimensión (los `multilingual-e5-*` usan
768), recrear la columna `vector(384)` y el índice HNSW —
`EmbeddingPipeline.ensure_vector_extension_and_index()`. Candidatos:
`paraphrase-multilingual-MiniLM-L12-v2` (mantiene 384) o `multilingual-e5-base`.

**Medir antes de migrar**: correr el mismo set de 15 queries con los dos modelos
y comparar distancias del top-1. Es barato y decide solo.

### 7. Búsqueda híbrida: sumar la mitad léxica **[hipótesis]**
Para queries cortas y precisas ("oreo 354g", "coca 2.25") BM25 le gana a los
embeddings casi siempre; el vector brilla en queries vagas ("algo para untar sin
azúcar"). Hoy solo está la mitad densa.

Postgres ya trae `tsvector`/`ts_rank` y `pg_trgm`, así que **no hacen falta
dependencias nuevas**: se fusionan las dos listas (Reciprocal Rank Fusion es lo
estándar) dentro del mismo CTE `pool` que ya existe. Probablemente la mejora más
grande por línea de código en un catálogo de este tamaño.

### 8. Atributos de la query como filtro duro
"leche descremada 1L" o "fideos sin tacc": el embedding **difumina** el `1L` y
el `sin tacc`, que son justo las partes no negociables. Ya existen
`is_gluten_free`, `is_vegan`, `total_volume_weight` y `src/size_parser.py` — la
pieza que falta es parsear esos atributos **de la query** y aplicarlos como
filtro, no como similitud. Es exactamente donde el vector es aproximado.

Relacionado y ya medido: con `STORE_BONUS = 0.02` la query `yogur bebible`
expulsaba yogures *bebibles* en favor de *griegos* de 3 tiendas, porque el
embedding no trata "bebible" como restricción dura. Este ítem es la solución de
fondo a esa clase de problema; el tope del bonus es solo la contención.

### 9. `exclude_stores` en `/search` y `/category`
El backend no conoce la cobertura — `unavailableStores` vive en
`ProfileContext` —, así que `store_count` cuenta tiendas que quizá no lleguen a
la dirección del usuario.

Con `STORE_BONUS = 0.01` y el tope en 2 el error se diluye casi siempre (un
producto de 3 tiendas menos una sigue teniendo 2 y conserva el bonus completo),
por eso se difirió. Se vuelve necesario si el bonus sube o si se agregan
tiendas.

---

## Deuda técnica y riesgos conocidos

### 10 y 11 — RESUELTOS
La truncación silenciosa y el pruning que se apagaba con una sola categoría
caída se corrigieron juntos, porque el primero agrava al segundo: al declarar
las categorías caídas como tales, el gate `complete` dejaba sin podar a la
tienda entera. Quedó documentado en las etapas 1 y 2 de CLAUDE.md.

Los tres scrapers siguen ahora una regla única —`break` sólo ante página válida
y vacía, todo lo demás levanta `CategoryScrapeError`—, y el pruning se acota a
las categorías cuyo barrido cerró bien vía `store_products.source_category`.

**Por qué NO se aflojó `complete` por porcentaje**, que era la hipótesis de este
ítem: una tolerancia del estilo "podar si el 90% de las categorías anduvo" borra
catálogo vivo en proporción a lo que falló — el mismo daño de la truncación, más
chico. `MAX_PRUNE_RATIO` no lo ataja porque protege el caso contrario. Acotar el
DELETE en vez de aflojar el gate hace correcto al pruning en lugar de
heurístico, y no cede nada a cambio.

### 12. `unified_products.tags` es por EAN, no por tienda
Un producto presente en las tres tiendas se queda con los tags de la última que
lo escriba (orden coto → dia → carrefour). El tag canónico de góndola
(`src/shelves.py`) hace que el segmento que importa para el `&&` sea el mismo en
las tres, así que hoy no duele — pero si se scrapean categorías **fuera** de la
tabla de góndolas, vuelve a doler.

### 13. `CATEGORY_MAP` quedó chico para el catálogo actual
Sus 4 buckets (`Lácteos`/`Golosinas`/`Almacén`/`Otros`) mapean *hojas* con un
dict de 9 claves, así que con 6.336 productos la enorme mayoría cae en `Otros` y
`GET /category/{name}` los deja afuera. El mega-menú ya rutea casi todo a
`GET /search` vía `has_direct_category_match`, y la sustitución usa `tags`, así
que está contenido — pero el endpoint hoy cubre una fracción chica del catálogo.

---

## Catálogo

### 14. Segundo tramo de góndolas
`src/shelves.py` tiene 20 góndolas alineadas entre las tres tiendas. Las
candidatas obvias para el próximo tramo, ya relevadas contra las tres
taxonomías: **cereales, té, papas congeladas, hamburguesas congeladas, cervezas,
jugos, fiambres, huevos, manteca y margarina**.

Costo de referencia: las 20 actuales son ~30 min de barrido completo más
embeddings. Agregar una góndola es una fila en la tabla.

### 15. Alias de góndola para categorías fuera de la tabla
`shelf_tags()` resuelve el problema de vocabulario **solo** para las claves que
están en `SHELVES`. Una categoría scrapeada por fuera vuelve a depender de que
las cadenas nombren igual el mismo estante, que es la brecha que documenta la
etapa 7 de CLAUDE.md (Carrefour archiva el vinagre en `aceites-y-vinagres` y Día
en `aceites-y-aderezos`; no solapan).

**No aflojar el `&&` a un umbral de similaridad** — ver la discusión del 0.90 en
la etapa 4: pares genuinamente duplicados y pares meramente hermanos ocupan la
misma banda de similaridad, así que ningún umbral los separa.
