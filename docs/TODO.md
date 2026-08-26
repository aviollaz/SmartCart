# TODO / Roadmap

Ideas pendientes, ordenadas por relación impacto-costo dentro de cada sección.
Cada ítem dice **dónde** toca y **por qué** — la mitad del trabajo de un TODO es
que el que lo agarre no tenga que redescubrir el razonamiento.

Convención: los ítems marcados **[hipótesis]** no están verificados contra la
base; los demás salen de mediciones o de código leído.

---

## Producto

### 1. "Comprar de nuevo" / mis habituales — RESUELTO
El historial se guarda en `smartcart_history_v1` (`HistoryContext` +
`utils/purchaseHistory.js`) y se lee de dos formas: un ranking de productos por
frecuencia ("Comprar de nuevo", grilla de `ProductCard` reales) y la lista de los
últimos carritos con un botón Repetir. Vive en la home y en `/carrito` cuando
está vacío. Documentado en la sección de frontend de CLAUDE.md.

**La decisión no obvia es la ventana de sesión.** Una sola sesión de compra pega
varias veces contra `/optimize` —aceptar una sugerencia re-optimiza sola, un
cierre de tienda también, deshacer también, y "cambio una cantidad y vuelvo a
optimizar" es el flujo normal—, así que anexar una entrada por corrida no es
sólo ruidoso: sobrepondera justo los carritos que el usuario más manoseó, y una
tarde de indecisión le gana para siempre a tres meses de compras. Una corrida
dentro de los 30 minutos **reemplaza** a la anterior. Como SmartCart no tiene
checkout, no existe ninguna acción que signifique "ya compré": el tiempo es la
única señal. La ventana se queda corta a propósito — partir una sesión en dos es
molesto y visible, unir dos compras distintas destruye la primera en silencio.

Alternativas descartadas, por si alguna vuelve a tentar: **hash del contenido**
del carrito (falla justo donde importa, porque un swap cambia el contenido y los
swaps son la principal fuente de corridas repetidas); **contar cada uid una vez
por entrada** (no ayuda: lo duplicado es la entrada); **un botón "ya compré"**
(la señal más limpia de todas, pero pide una acción en el momento exacto en que
el usuario no tiene motivo para darla, así que la feature se quedaría sin datos);
**grabar al hacer click en el link de checkout** (sólo Día y Carrefour tienen
magic link, así que sub-registraría sistemáticamente los carritos con mucho Coto
— un sesgo en la dimensión tienda, peor que el que arregla).

Hizo falta un endpoint nuevo, `POST /products/by-ids`: `/price-preview` devuelve
precio pero ningún metadato, y su filtro por `in_stock` vuelve ambigua la
ausencia de un id. En el endpoint nuevo **un id ausente significa exactamente que
el pruning lo borró**, y "existe pero hoy nadie lo tiene" se reporta aparte con
`store_count == 0`. Ese contrato es lo que permite avisar "esto ya no está" sin
mentirle al que sólo se quedó sin stock.

Sobre el versionado, corrigiendo la premisa que tenía este ítem: la clave del
perfil lleva `_v1` pero **no se versiona** — la migración es un efecto con spread
(CLAUDE.md, etapa 9). Para el historial bumpear no es sólo poco convencional, es
destructivo: no hay copia en el servidor ni tabla por usuario, así que ninguna
acción del usuario reconstruye lo perdido. El tope de 20 carritos sí quedó, y no
sólo por tamaño: la escritura de `useLocalStorage` se traga los errores, así que
un historial sin techo que reviente la cuota del origen haría que el **carrito**
deje de persistir en silencio.

Límite conocido, no bug: el ranking es local al navegador por construcción.

### 2. Precio por unidad de medida — RESUELTO (con una excepción anotada)
El número lo calcula ahora el backend: `unit_price` (`{value, base}`) sale de
`_build_unit_price()` en `src/api.py` y viaja en `ProductResponse`.
`formatUnitPrice()` en el frontend ya no calcula nada, sólo formatea.

**Se movió al backend porque ahí está el dato**, y eso arregló dos bugs con una
sola causa. El cliente dividía `min_price`, que es el mínimo de los precios de
LISTA, así que la card anunciaba el precio con promo al lado de un precio por
kilo derivado de otro número; y `GET /search` ni siquiera mandaba `min_price`,
o sea que en resultados de búsqueda —por donde el usuario entra al catálogo— el
precio por unidad directamente no aparecía. Lo segundo se arregló haciendo que
`/search` pase por `_build_product_response()` como los otros dos endpoints, que
de paso le dio `min_price` e `image_url`.

**Pendiente 1 (base única) — hecho.** Se sacó el corte en 1000: siempre por kilo
para `'g'` y por litro para `'ml'`. Se aceptaron los costos medidos: cambia la
etiqueta del **89%** de los productos y **275 (4,5%)** pasan de $100.000/kg, con
un azafrán de 0,375 g mostrando $9.710.526/kg. El argumento a favor del corte
—un número enorme en un envase chico se lee como error de tipeo— es cierto, pero
dos bases conviviendo en la misma grilla rompen justamente la comparabilidad que
es el motivo entero del ítem. La mediana quedó en **$14.929/kg**.

Nota: `substitutions.format_size()` **conserva** su corte en 1000. No es una
inconsistencia: escribe un *tamaño* ("1 Kg"), no una base de comparación.

**Pendiente 2 (multipacks) — sigue abierto, y probablemente se quede así.** El
peso no se multiplica. El número al lado del `xN` es indecidible desde el nombre
(a veces es el total del pack, a veces el tamaño de cada unidad; ver el docstring
de `extract_pack_count`), así que multiplicar inflaría justo las filas que ya
traían el total, y un peso inflado **abarata** el precio por kilo. Al no
multiplicar el error sólo puede ir hacia **caro**, que es la dirección que el
proyecto acepta en todos lados. Resolverlo de verdad pide evidencia que el
payload scrapeado no tiene.

Lo de `units_per_pack` que este ítem arrastraba se cerró en el 14: la columna ya
no existe.

### 3. Progreso hacia el mínimo de compra, en vivo
Hoy el usuario descubre que el carrito es inviable **recién al optimizar**, que
es la peor fricción del flujo y además es la KPI que mide el analyzer
(`% carritos inviables`).

`DEFAULT_MIN_SPEND_LIMITS` vive en `src/optimizer.py` y el frontend ya llama a
`POST /price-preview` para la advertencia de cobertura. Falta convertir la
restricción dura en un indicador durante el armado.

Dos notas de cuando se hizo el #1, que comparte substrato con este ítem (los dos
baten `/price-preview` sobre una lista de ítems). Primero: los mínimos hay que
exponerlos desde el backend, no copiar los números al frontend — un id duplicado
es tolerable, un número que cambia no. Segundo, y más importante: **el mínimo
rige sólo para las tiendas ACTIVAS del split**, no para todas, así que una barra
de progreso por tienda miente — un carrito puede ser perfectamente viable con dos
de las tres barras a cero. El indicador honesto es global ("te faltan $X para que
alguna tienda te sirva"), no por tienda.

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

### 12, 13 y 14 — RESUELTOS juntos: una sola taxonomía
Los tres eran el mismo problema visto desde tres lados: la base guardaba **tres
representaciones paralelas** de "a qué góndola pertenece este producto", y las
tres eran peores que la que ya existía en `src/shelves.py`.

* **12** — `unified_products.tags` era por EAN: un producto de las tres cadenas
  se quedaba con los tags de la última que lo escribiera, o sea con el
  vocabulario de una sola tienda.
* **13** — `unified_products.category` mapeaba *hojas* con un dict de 12 claves a
  4 buckets, y medido sobre la base: **5.140 de 6.401 (80%)** caían en `Otros`,
  así que `GET /category/{name}` cubría una fracción chica del catálogo.
* **14** — `units_per_pack` no la escribía nadie y, por tener `DEFAULT 1`, no
  llegaba vacía sino **afirmando "no es un pack"** sobre 6.401 productos, 287 de
  los cuales sí lo son.

Las tres se reemplazaron por **`unified_products.shelf`**: el slug de góndola de
`src/shelves.py`, idéntico en las tres cadenas por construcción. Medición que
habilitó la migración: las 20 góndolas cubren **6.401 de 6.401** productos con
exactamente un slug cada uno, y ese slug **ya estaba adentro de `tags`**, así que
el backfill fue un `UPDATE` y no hizo falta rescrapear nada
(`src/scripts/migrate_shelves.py`, que además dropea las tres columnas y aborta
si quedó una sola fila sin góndola — dropear `tags` es lo que vuelve
irreversible el backfill).

Lo que se cayó con ellas, y por qué no se extraña:

* `SmartCartDB.CATEGORY_MAP` y toda la normalización de categoría en el ingest.
* `src/category_tree.py` (260 líneas) y `GET /categories/tree`: mergeaban por
  embeddings las taxonomías COMPLETAS de Coto y Día —Carrefour nunca entró— para
  un menú de ~15 top-levels y cientos de hojas sobre un catálogo de 20 góndolas.
  Casi todo lo que se clickeaba no tenía productos y caía a `GET /search?q=<label>`,
  una búsqueda semántica del nombre de una categoría que el catálogo no tenía.
  El mega-menú ahora dibuja las góndolas: dos niveles, y toda hoja tiene
  productos. Con eso murió también `has_direct_category_match`.
* `src/category_tags.py` quedó reducido a `src/taxonomy.py` (cargar los dumps).
  El filtro de "misma góndola" pasó de un solapamiento `&&` sobre arrays con
  fallback a `category`, a una igualdad `u.shelf = %s` sobre un btree.

**La discusión del 0.90 de la etapa 4 de CLAUDE.md se conserva** aunque el módulo
que la motivó ya no exista: sigue siendo el precedente que dice que un desajuste
de vocabulario se arregla con una tabla explícita y no bajando un umbral.

### 15 y 16 — RESUELTOS
El 15 no era un bug sino cronología: `source_category` estaba en NULL en las
3.252 filas de Coto y las 1.529 de Día porque la columna se agregó el 2026-08-24
y esas filas se habían escrito por última vez el 2026-08-21. Cualquier barrido
completo las llena, y eso es lo que corresponde correr después de la migración.

El 16 era el riesgo silencioso que el 15 destapó, y ese sí necesitaba código.
Ahora `save_store_products` exige `prod['source_category']` y `prod['shelf']` en
vez de leerlas con `.get()` defensivo, y `tests/test_scraper_ingest_keys.py`
asserta que los tres scrapers las emitan, reusando los fixtures de
`test_scraper_truncation.py`. Sin eso, un scraper que dejara de mandar
`source_category` escribía NULL en silencio y a partir de ahí **todo barrido
parcial podaba cero filas** reportando `deleted: 0` con `skipped: False`,
indistinguible de "no se dio de baja nada".

### Bonus del mismo barrido: el esquema existe en el repo
No estaba en el TODO porque nadie lo había mirado: **no había ningún
`CREATE TABLE` de `unified_products` ni de `store_products` en el proyecto**. El
esquema base se había hecho a mano contra el Postgres de desarrollo, así que un
clone nuevo no arrancaba y los defaults de columna eran indescubribles leyendo el
código — que es exactamente cómo `units_per_pack DEFAULT 1` pudo mentir durante
meses sin que nada lo delatara.

Ahora está todo en `src/schema.py`: idempotente y declarativo (`CREATE TABLE IF
NOT EXISTS` + `ADD COLUMN IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS`), una
sola definición, aplicada por `SmartCartDB`, `EmbeddingPipeline`,
`ScraperTelemetry` y el `lifespan` de la API. Sigue sin haber migraciones
versionadas y es a propósito; lo que hay es un esquema que converge. **El módulo
no borra nada**: los DROP viven en el script de migración, que se corre a mano.

De paso salieron otras dos cosas que se traían y se tiraban: `is_weighable`, que
los tres scrapers calculaban y ningún INSERT guardaba, y `image_url`/`in_stock`
en el SELECT de `get_market_prices_for_cart`, que el flattener no lee.

### 17. Pesos absurdos del parser de tamaños
3 productos (**0,05%**) con `total_volume_weight` imposible en una góndola: una
yerba de 1 kg guardada como **999.811 g**, un combo de gaseosas como **3.500.000 g**
y filtros de café como 29.999 g. Salen del fallback que estima el tamaño dividiendo
el precio por el precio por unidad.

Importa porque un peso inflado **abarata** el precio por kilo — esa yerba muestra
$2/kg —, que es la dirección de error que el proyecto evita en todo el resto del
pipeline. Se registra y **no se actúa**: son 3 filas, y un umbral inventado
("ocultar si pesa más de 20 kg") es exactamente el tipo de constante arbitraria que
CLAUDE.md desaconseja en la discusión del 0.90 de la etapa 4. Si el número crece,
el arreglo va en `src/size_parser.py`, no en la vista.

---

## Catálogo

### 18. Segundo tramo de góndolas
`src/shelves.py` tiene 20 góndolas alineadas entre las tres tiendas. Las
candidatas obvias para el próximo tramo, ya relevadas contra las tres
taxonomías: **cereales, té, papas congeladas, hamburguesas congeladas, cervezas,
jugos, fiambres, huevos, manteca y margarina**.

Costo de referencia: las 20 actuales son ~30 min de barrido completo más
embeddings. Agregar una góndola es una fila en la tabla.

### 19. Alias de góndola para categorías fuera de la tabla — CERRADO por construcción
Ya no hay "categorías fuera de la tabla" que puedan llegar a la base: los
scrapers iteran `keys_for_store()`, `save_store_products` exige la góndola, y
`tests/test_shelves.py` verifica que toda clave de `SHELVES` exista de verdad en
el dump de taxonomía de su tienda. Una clave inventada falla el test en vez de
escribir un producto sin góndola.

La brecha que este ítem describía era real mientras la comparación corría sobre
los `tags` de cada tienda (Carrefour archiva el vinagre en `aceites-y-vinagres`
y Día en `aceites-y-aderezos`; no solapan). Con `shelf` no hay vocabulario que
conciliar. Se deja escrito el criterio, que sigue valiendo para cualquier
atributo nuevo que dependa de cómo nombra las cosas cada cadena:

**No reemplazar una comparación exacta por un umbral de similaridad** — ver la
discusión del 0.90 en la etapa 4 de CLAUDE.md: pares genuinamente duplicados y
pares meramente hermanos ocupan la misma banda de similaridad, así que ningún
umbral los separa. La forma correcta es una tabla explícita.
