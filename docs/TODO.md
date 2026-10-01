# TODO / Roadmap

Ideas pendientes, ordenadas por relación impacto-costo dentro de cada sección.
Cada ítem dice **dónde** toca y **por qué** — la mitad del trabajo de un TODO es
que el que lo agarre no tenga que redescubrir el razonamiento.

Convención: los ítems marcados **[hipótesis]** no están verificados contra la
base; los demás salen de mediciones o de código leído.

Lo ya resuelto no vive acá: se saca del backlog y queda una línea en
[Cerrados](#cerrados) apuntando a dónde quedó documentado el razonamiento.

---

## Producto

### 0. Grabar la demo del README
El `README.md` tiene el hueco marcado y las instrucciones de publicación; falta
el archivo. **Es lo de mayor impacto por hora de trabajo de todo este backlog**:
el repo es público y nadie clona un proyecto para evaluarlo — con suerte mira el
README treinta segundos. Hoy esos treinta segundos no muestran el producto.

Dos piezas, en este orden:

* **Un GIF corto (~10 s)** arriba de todo. Es el que se ve sin hacer click, y
  por eso es el que más importa: carrito → *Optimizar* → reparto entre tiendas.
* **Un video (~60 s)** abajo, con el recorrido completo: buscar, ver el precio
  por unidad de medida, armar el carrito, optimizar, y —lo que de verdad
  distingue al proyecto— el ahorro y una sustitución estratégica aplicada.

**No commitear el binario.** Se arrastra el archivo a un comentario de un issue
o a un Release: GitHub lo sube a su CDN y devuelve una URL de
`user-attachments`. Un `.mp4` versionado lo paga cada clone para siempre, y el
criterio del repo es no guardar artefactos descartables.

Para que la demo se vea bien hace falta una base poblada, o sea correr el
barrido antes (`--store dia` alcanza para grabar, son ~16 min).

### 0b. Arranque en frío de la demo: medir el ping y, si no alcanza, sacar torch
La demo pública tardaba **29,7 s** en contestar la primera visita tras ~15 min
sin tráfico, contra 0,25 s en caliente. Es Cloud Run (`--min-instances 0`)
cargando imagen, torch y modelo; **no es Neon**, que despierta en 1-3 s — por eso
mudar la base a una PC de casa no lo arregla (ver la sección de self-hosting de
`ops/demo-publica.md`, que ya lo había descartado).

**Lo que ya está** (oct-2026): un job de Cloud Scheduler (`smartcart-warm`) le
pega a `GET /` cada 10 min de 8 a 24 hs (no toca la base, así que no gasta
CU-hours de Neon) y `--cpu-boost` en el deploy. Reemplazó a un workflow de
Actions cuyo cron impuntual dejaba pasar ~la mitad de los pings en frío (medido
en `ops/demo-publica.md`).

**Lo que falta:**
1. Redeployar con `--cpu-boost` y volver a medir en frío (el comando está en
   `ops/demo-publica.md`).
2. Después de unos días, contar en los logs de Cloud Run cuántas veces por día
   aparece `Cargando modelo SentenceTransformer` (cada una es un arranque en
   frío) y confirmar en el panel de Neon que el consumo no subió.
3. **Sólo si sigue molestando** (la primera visita de la mañana, un cron
   atrasado): reemplazar torch por ONNX Runtime para codificar la query de
   `/search`. Imagen de 2,78 GB → ~600 MB, RSS ~400 → ~250 MB; también es lo que
   destraba la VM de Oracle de 1 GB (`ops/README.md`). Toca el `Dockerfile`,
   `requirements.txt` y el lifespan de `src/api.py`; `src/embeddings.py` (el
   barrido) puede seguir con sentence-transformers siempre que los vectores
   coincidan — **verificarlo** comparando embeddings de las dos vías antes de
   mezclar.

### 1. Progreso hacia el mínimo de compra, en vivo
Hoy el usuario descubre que el carrito es inviable **recién al optimizar**, que
es la peor fricción del flujo y además es la KPI que mide el analyzer
(`% carritos inviables`). Lo único que hay es `InfeasibleNotice`, o sea el aviso
después del hecho.

`DEFAULT_MIN_SPEND_LIMITS` vive en `src/optimizer.py` y hoy no lo expone ningún
endpoint: `GET /` devuelve estado, no configuración. El frontend ya llama a
`POST /price-preview` para la advertencia de cobertura, así que el substrato
—batir una lista de ítems contra la base mientras se arma el carrito— ya existe.
Falta convertir la restricción dura en un indicador durante el armado.

Dos notas heredadas del historial de compras, que comparte ese substrato.
Primero: los mínimos hay que **exponerlos desde el backend**, no copiar los
números al frontend — un id duplicado es tolerable, un número que cambia no.
Segundo, y más importante: **el mínimo rige sólo para las tiendas ACTIVAS del
split**, no para todas, así que una barra de progreso por tienda miente — un
carrito puede ser perfectamente viable con dos de las tres barras a cero. El
indicador honesto es global ("te faltan $X para que alguna tienda te sirva"), no
por tienda.

### 2. Sustituciones pre-aprobadas
`src/strategic_swaps.py` ya calcula candidatos comparables; lo que falta no es
el algoritmo sino el **consentimiento previo** del usuario sobre qué reemplazo
acepta.

Hoy todas las superficies de sustitución son post-optimización y de a un click:
`SuggestionsList.jsx` (un `<select>` de alternativas sobre `result.suggestions`)
y `StrategicSwapCard.jsx` + `handleApplyStrategicSwap` en `CartPage.jsx`, que
aplica un lote y re-optimiza. `ProfileContext` guarda tarjetas, membresías y
dirección: no hay dónde vivan las preferencias de reemplazo.

---

## Búsqueda y relevancia

Contexto: `GET /search` ya hace recuperar-y-reordenar en dos etapas con el bonus
por disponibilidad (`STORE_BONUS`, ver CLAUDE.md etapa 6). Lo que sigue es la
continuación natural.

### 5. Búsqueda híbrida: implementada, falta medirla y enchufarla **[hipótesis]**
**Lo que ya está** (sep-2026): `src/search.py` tiene los dos modos y es el único
SQL de búsqueda — lo usan `GET /search` y `medir_busqueda.py`, que antes copiaba
la consulta a mano y sin el bonus por disponibilidad. El híbrido suma una mitad
léxica sobre `unified_products.name_tsv` (tsvector `spanish` sin acentos,
columna generada + GIN, en `src/schema.py`; se rellena sola al aplicar el
esquema, sin re-scrapear) y fusiona por Reciprocal Rank Fusion (k=60). La mitad
densa entra con su orden de siempre, así que `STORE_BONUS` no se recalibra.

**Lo que falta, en este orden:**

1. Con una base poblada: `python -m src.scripts.medir_busqueda --modo denso` y
   `--modo hibrido`. Además de las 10 queries de una palabra (79/100 hoy) el
   script mide 5 precisas de marca ("playadito", "coca cola 2.25"…), que es
   donde se espera la ganancia.
2. **Gate:** el híbrido no puede bajar el total de una palabra ni romper
   ninguna query que hoy da 10/10. Si pasa, `DEFAULT_SEARCH_MODE = "hibrido"`
   en `src/search.py` y actualizar `tests/test_search_ranking.py`, cuyo test de
   orden replica el score denso y dejaría de valer con RRF.
3. Si no pasa, se registra en Cerrados con la tabla, como el ítem 4.

### 6. Atributos de la query como filtro duro
"leche descremada 1L" o "fideos sin tacc": el embedding **difumina** el `1L` y
el `sin tacc`, que son justo las partes no negociables.

Ojo con el alcance, porque una parte ya está hecha: `gluten_free` y `vegan` son
**parámetros explícitos** de `/search` y de `/category` (`_dietary_filter_clause`
en `src/api.py`), con UI en `plp/DietaryFacet.jsx`. Lo que falta son las otras
dos mitades, y ninguna existe:

* **Parsear los atributos de la query**, para que escribir "sin tacc" en el
  buscador active el filtro en vez de competir por similitud.
  `src/dietary_parser.py` hoy sólo lo importan los tres scrapers.
* **Filtrar por tamaño/formato**, que no tiene ni parámetro. `total_volume_weight`
  y `src/size_parser.py` ya están, pero `size_parser` también lo importan sólo
  los scrapers: nada mira el lado de la query.

Relacionado y ya medido: con `STORE_BONUS = 0.02` la query `yogur bebible`
expulsaba yogures *bebibles* en favor de *griegos* de 3 tiendas, porque el
embedding no trata "bebible" como restricción dura. Este ítem es la solución de
fondo a esa clase de problema; el tope del bonus es sólo la contención.

### 7. `exclude_stores` en `/search` y `/category`
El backend no conoce la cobertura — `unavailableStores` vive en
`ProfileContext` —, así que `store_count` (un `count(DISTINCT sp.store_id)` sobre
todas las tiendas) cuenta tiendas que quizá no lleguen a la dirección del
usuario, y el bonus de disponibilidad se calcula sobre ese número.

Con `STORE_BONUS = 0.01` y el tope en 2 el error se diluye casi siempre (un
producto de 3 tiendas menos una sigue teniendo 2 y conserva el bonus completo),
por eso se difirió. Se vuelve necesario si el bonus sube o si se agregan
tiendas.

---

## Deuda técnica y riesgos conocidos

### 8. Pesos absurdos del parser de tamaños
3 productos (**0,05%**) con `total_volume_weight` imposible en una góndola: una
yerba de 1 kg guardada como **999.811 g**, un combo de gaseosas como **3.500.000 g**
y filtros de café como 29.999 g.

Importa porque un peso inflado **abarata** el precio por kilo — esa yerba muestra
$2/kg —, que es la dirección de error que el proyecto evita en todo el resto del
pipeline.

Dónde está realmente el fallback, que no es donde uno lo busca: **no está en
`src/size_parser.py`** (ese módulo no tiene ningún tope superior; su único
control de cordura es `1 <= count <= 100` sobre el conteo de packs). Está
**triplicado en los tres scrapers**, estimando el tamaño como
`base_price / precio_por_und`: `scraper_carrefour.py:175-196`,
`scraper_dia.py:140-163` y `scraper_coto.py:176-188`. Un detalle que conviene
mirar si el número crece: la rama de magnitud de Día y Carrefour es
`if "lt" in unidad_medida or "l" in unidad_medida`, que matchea **cualquier**
unidad que contenga la letra "l", y es el mismo camino que produce los valores
inflados.

Se registra y **no se actúa**: son 3 filas, y un umbral inventado ("ocultar si
pesa más de 20 kg") es exactamente el tipo de constante arbitraria que CLAUDE.md
desaconseja en la discusión del 0.90 de la etapa 4. Si el número crece, el
arreglo va en el fallback de los scrapers (o mejor: unificado en
`src/size_parser.py`), no en la vista.

### 9. El pool de conexiones fija `dict_row`, y no todos los caminos lo usan
Riesgo medido, no bug: hoy no rompe nada y no hay que tocarlo antes de mudar la
base. Se anota ahora porque **una base remota lo vuelve caro**: contra Postgres
local una conexión es un socket local, contra una base administrada es un
handshake TCP + TLS.

* `src/db_pool.py` fija `kwargs={"row_factory": dict_row}` al crear el pool, así
  que cualquier consulta del camino de request que necesite tuplas **no puede
  usar el pool**. Es lo que hoy deja afuera a los caminos de escritura.
* `src/database.py:58` y `:258` (`save_store_products` y
  `prune_missing_store_products`) conectan directo a propósito. Correcto hoy,
  pero es el código que **más conexiones abre por corrida del pipeline**.
* `src/scraper_telemetry.py:91, 119, 145`: tres `psycopg.connect` directos, uno
  por paso. El escritor es fail-open por doctrina y corre 4 veces por noche, así
  que el costo es chico — pero es el único escritor que podría vivir en proceso.

Lo que **no** hace falta tocar: `src/embeddings.py`, `src/schema.py` y
`src/scripts/*` conectan directo y está bien — son procesos de una sola pasada.

---

## Catálogo

### 11. Medir el consumo de Neon después del segundo tramo **[hipótesis]**
El catálogo pasó de 20 a 49 góndolas (y después a 56, con helados y la sección
Limpieza, a 60 con frutas, verduras y carnes, ~700 productos más, y a 75 con
Perfumería, ~+20% de claves por tienda), así que el barrido nocturno pasa de ~77
minutos a un estimado de ~1,5 h por tienda en paralelo. El plan gratuito de Neon
da **100 CU-hours por mes** y la base se suspende sola tras 5 minutos sin
actividad, o sea que lo que se paga es el tiempo que está despierta.

El barrido en paralelo (`.github/workflows/scrape.yml` corre las tres tiendas en
una matriz) mantiene ese número en el orden del más lento y no de la suma, que es
justamente por qué se paralelizó. Pero **el número real no se puede leer desde
adentro de la base**: hay que mirarlo en el panel de Neon después de la primera
semana. Si se acerca al tope, las salidas por orden de costo son bajar la
frecuencia del barrido (día por medio alcanza para precios de supermercado),
o mudarse a la VM de Oracle (`ops/README.md`).

### 21. Tamaños de Limpieza: papel en metros y paños
Toda la sección Limpieza de papel (papel higiénico, rollos, servilletas) queda con
`unit_type = 'un'`: el tamaño real está en metros ("4 rollos x 30 m"), metros
cuadrados o paños, y `src/size_parser.py` no lee ninguna de esas unidades. Es la
dirección segura —no inventa un peso ni un precio por kilo—, pero tiene un costo
concreto: `substitutions.is_comparable` trata a dos productos en `'un'` como
comparables sin mirar tamaño, así que la única barrera que queda entre un rollo
de 30 m y uno de 80 m es `same_pack_format` (la cantidad de rollos del pack).

Relacionado: Coto archiva film adherente y papel manteca en `catv00003020`
("Rollo de Cocina"), así que esos dos productos quedan en `rollos-y-servilletas`.
Son dos filas; no se agregó una exclusión por nombre para eso.

Si se arregla, el lugar es `size_parser` (una unidad `m`/`m2` con su propio
vocabulario), no un umbral en las sustituciones.

### 22. Frescos: kilos fraccionarios y mantenimiento de la tabla
Las frutas, verduras y carnes de `src/fresh_items.py` se comparan por kilo, pero
el carrito sólo acepta cantidades enteras (`CartItem.quantity: int`): 1 = 1 kg.
Alcanza para papas o bananas, no para 300 g de jamón o medio kilo de bife. El
cambio toca el modelo de la API, el flattener (las promos por cantidad asumen
unidades enteras), el optimizador (trabaja en centavos enteros) y el stepper del
frontend, así que no es un parche.

Aparte, la tabla se degrada sola: cuando una cadena re-publica un producto con un
SKU nuevo, el ítem pierde esa tienda sin que falle nada. Hay que correr
`python -m src.scripts.curar_frescos` cada tanto y mirar "Obsoletos"; si se
vuelve tedioso, el paso siguiente es que el barrido nocturno cuente los SKUs de
la tabla que no vio y lo reporte como PARTIAL, igual que una categoría vacía.

### 23. Sumar Vea y Jumbo
Pedido de AV (sep-2026), **después** de la demo: no mejora la primera impresión
y es la tarea más cara del backlog. Relevado, sin medir todavía contra el
endpoint:

* **Easy queda afuera**: es la cadena de construcción y hogar de Cencosud, no un
  supermercado. No comparte ninguna góndola de `src/shelves.py`, y un producto
  que no se puede comparar no le da nada al optimizador.
* **Vea y Jumbo son VTEX** (Cencosud), igual que Día y Carrefour, así que el
  scraper se parece a `scraper_carrefour.py` y reusa `src/scrapers/vtex.py`
  (`extract_search_payload`, `read_availability`, `storefront_url`,
  `is_transient_graphql_error`). **Verificar** si aceptan el mismo `sha256Hash`
  de `productSearchV3`; si no, hay que capturar el suyo.
* **Son la misma empresa**: pueden compartir buena parte del catálogo y hasta
  precios. Medir cuánto aporta la segunda (productos por EAN que no tiene la
  primera, diferencias de precio) antes de sumar las dos. Empezar por una.

Lo que cuesta, en el orden en que rompe si se olvida:
* Una columna nueva en **las 75 filas** de `SHELVES`, medida clave por clave
  contra el endpoint en vivo, con dump de taxonomía propio
  (`src/scrapers/<tienda>_categories.json`) para `tests/test_shelves.py`, y las
  dos reglas de la etapa 1b (ninguna clave ancestro de otra; clave en el dump ≠
  clave con productos). Una góndola sin clave rompe la regla de "todas las
  tiendas en todas las góndolas" que el test exige hoy.
* `STORE_IDS`, `STORE_RUNNERS`, la matriz de `.github/workflows/scrape.yml`.
* **Regla de dos archivos** (CLAUDE.md etapa 6): `DEFAULT_MIN_SPEND_LIMITS` en
  `src/optimizer.py` y la tabla de `frontend/src/utils/deliveryCosts.js` en el
  mismo commit; si no, `KeyError` en `/optimize` o la tienda queda en el banco
  sin aviso. Mínimo de compra y costo de envío hay que relevarlos.
* `STORES` en `frontend/src/utils/constants.js`, `VTEX_CHECKOUT_DOMAINS` para el
  link de carrito, y un `DiscountScraper` para sus promos bancarias.
* **Activa el ítem 7** (`exclude_stores` en `/search`): con más tiendas el
  `store_count` sin cobertura deja de diluirse.
* **Aprieta el ítem 11**: un barrido más en la matriz es más cómputo de Neon por
  noche, justo el recurso que el plan gratuito limita.

---

## Optimizador

### 12. Límite de cantidad de supermercados en el split
Idea de AV: dejar elegir "como máximo N supermercados" antes de optimizar, en
vez de que el split use los que el propio solver decida óptimos. Investigado
para la demo con amigos y **deliberadamente no implementado todavía** — no
vale el costo para una primera demo, pero queda anotado para no rehacer la
investigación.

**La parte fácil es trivial.** `src/optimizer.py::optimize_cart()` ya arma
una variable booleana `y[j]` por tienda ("¿está activa?") para el constraint
de mínimo de compra. Un límite de cantidad es una línea más, en cualquier
punto antes de `model.Minimize(...)`:

```python
if max_stores is not None:
    model.Add(sum(y[j] for j in stores) <= max_stores)
```

**Lo que realmente cuesta es no mentir sobre por qué falló.** Hoy, si el
solver no encuentra asignación, `optimize_cart` devuelve un mensaje genérico
("No se encontró una asignación que cumpla los mínimos requeridos") que
asume que la causa es el mínimo de compra — con el cap agregado, un carrito
que necesita productos de más de N tiendas también cae por ese mismo mensaje,
y sería la causa equivocada. Hace falta distinguirlo, con un chequeo previo
al modelo (mismo patrón que `unavailable_products`, líneas 71-95) o con un
mensaje propio cuando el solver falla con el cap puesto.

**Lo que falta para exponerlo, dos archivos, sin precedente que copiar:**
`OptimizationRequest` en `src/api.py` no tiene ningún campo de este tipo hoy
— a diferencia de lo que uno esperaría, `excluded_stores` **no** viaja desde
el frontend: lo calcula el propio backend a partir de `lat`/`lng`
(`_resolve_coto_stage`). Ya hay un precedente: `user_excluded_stores`
(las tiendas que el usuario deshabilitó en el carrito) es un campo elegido por el
usuario, validado en `OptimizationRequest`, y `optimize_cart` ya distingue su
mensaje de inviabilidad del de cobertura. `max_stores` seguiría ese mismo patrón:
`Optional[int] = None`, validado, y pasado a `optimize_cart(...)`.
`frontend/src/api/optimize.js` sigue el mismo patrón que `zone`/`anon_user_id`
para sumarlo al body.

**No hace falta ningún selector de "qué tienda", sólo de cantidad.**
`StoreAvailabilityToggle` (`frontend/src/components/plp/`) existe pero es un
filtro client-side de la grilla de búsqueda, no tiene ninguna conexión con
`/optimize` — no sirve como base para esto. Al ser un límite de cantidad y no
una selección, alcanza con un control numérico simple (1 / 2 / 3 / sin
límite) en el carrito, sin pedirle al usuario que elija tiendas de antemano.

**Tests:** `tests/test_optimizer_correctness.py` ya tiene un oráculo de
fuerza bruta (`_brute_force_optimum`) que sería mecánico extender con un
filtro `len(active) <= max_stores`, más un puñado de casos nuevos (cap=1
fuerza todo a una tienda aunque sea más caro; cap=1 más un producto exclusivo
de otra tienda es infeasible con el mensaje distinguido; cap ≥ cantidad de
tiendas es un no-op).

---

## Cerrados

Se sacan del backlog. El razonamiento no se pierde: vive en CLAUDE.md, que es
donde se lee cuando se toca el código.

* **1** — Historial "Comprar de nuevo" / mis habituales → CLAUDE.md, sección de
  frontend, *Purchase history*. Incluye la regla de ventana de sesión (30 min,
  reemplaza en vez de anexar) y las cuatro alternativas descartadas.
* **2** — Precio por unidad de medida → CLAUDE.md etapa 6 (`_build_unit_price`).
* **3** — Comparar el split contra comprar en una sola tienda → CLAUDE.md etapa
  6 (`fewer_stores_options` y `max_stores`). Se resolvió como "cuánto cuesta
  comprar en menos súper", no como tres totales por cadena: la mejor opción de
  una sola tienda es la que responde "¿valió la pena partir?", y el usuario
  puede elegirla con un click.
  Base única kg/L, con los costos medidos. **Los multipacks siguen sin
  multiplicar el peso a propósito** — el `xN` es indecidible desde el nombre y
  errar hacia caro es la dirección que el proyecto acepta (etapa 7).
* **10, 11** — Truncación silenciosa de los scrapers y pruning que se apagaba con
  una sola categoría caída → CLAUDE.md etapas 1 y 2. Se corrigieron juntos porque
  el primero agrava al segundo. **No aflojar `complete` por porcentaje**: borra
  catálogo vivo en proporción a lo que falló.
* **12, 13, 14** — `tags`, `category` y `units_per_pack` → reemplazados por
  `unified_products.shelf`. CLAUDE.md etapas 1b y 2. Se llevaron puestos
  `src/category_tree.py`, `GET /categories/tree` y `CATEGORY_MAP`.
* **15, 16** — `source_category` en NULL (era cronología, no bug) y el riesgo que
  destapó: `save_store_products` ahora **exige** `shelf` y `source_category` en
  vez de leerlas con `.get()`. CLAUDE.md etapa 2, y
  `tests/test_scraper_ingest_keys.py`.
* **Bonus** — El esquema no existía en el repo. Ahora es `src/schema.py`:
  idempotente, declarativo, una sola definición, y **no borra nada** (los DROP
  viven en `src/scripts/migrate_shelves.py`). CLAUDE.md etapa 2.
* **Segundo tramo de góndolas** — de 20 a **49**, cubriendo las secciones de
  comida de las tres cadenas (se sumó Congelados como sección). Cada clave nueva
  se midió contra el endpoint en vivo antes de escribirla. En el camino
  aparecieron tres agujeros silenciosos que ya estaban en producción: dos claves
  de Día muertas por un renombre de la tienda, una clave de Carrefour anidada
  adentro de otra, y `frescos/fiambreria` entero cargado en `quesos`. Ver
  CLAUDE.md etapa 1b (reglas de anidamiento y de claves muertas) y etapa 10
  (`categories_empty`, que es lo que hace ruidosa esa clase de falla).
* **19** — Alias de góndola para categorías fuera de la tabla → cerrado por
  construcción: los scrapers iteran `keys_for_store()` y `tests/test_shelves.py`
  verifica que toda clave exista en el dump de taxonomía de su tienda. El
  criterio que lo motivó sigue valiendo para cualquier atributo nuevo que dependa
  del vocabulario de cada cadena: **no reemplazar una comparación exacta por un
  umbral de similaridad** — ver la discusión del 0.90 en CLAUDE.md etapa 4. La
  forma correcta es una tabla explícita, y `src/shelves.py` es esa tabla.
* **Scrapeo nocturno "casi siempre" con alguna tienda en rojo** — no era un
  problema de las tiendas, era que ningún scraper reintentaba un request.
  `scraper_coto.py`, `scraper_dia.py` y `scraper_carrefour.py` hacían un solo
  intento por página con `timeout=15.0`; cualquier timeout o error transitorio
  levantaba `CategoryScrapeError` de inmediato, y **cualquier** categoría
  PARTIAL hace que `orchestrator.py` salga con código != 0 (ver CLAUDE.md etapa
  10), así que un solo blip de red entre ~150-200 requests por noche alcanzaba
  para pintar el job de GitHub Actions en rojo. Coincide con lo observado en
  `docs/references/*.png`: la tienda que falla cambia noche a noche, y a veces
  falla a los 5 minutos — muy poco para un barrido que tarda 40 min-1,5 h,
  consistente con un error temprano de una sola request. Arreglado con
  `src/scrapers/http_retry.py`: 2-3 intentos con backoff corto sobre
  excepciones de transporte y status 429/5xx, sin tocar la semántica de
  `CategoryScrapeError` (sigue levantando igual si los reintentos se agotan).
  Sin dependencia nueva. Tests en `tests/test_http_retry.py` y los casos nuevos
  de `tests/test_scraper_truncation.py`. **No elimina los fallos reales**
  (hash de persisted query rotado, sitio caído) — esos tienen que seguir
  pintando el job en rojo.
* **10 — Helados en Carrefour** → fila `helados` en `src/shelves.py`. No era
  otra rama: el catálogo público de Carrefour tiene ~27 helados en
  `congelados/helados-y-postres`, pero el listado filtra los sin stock
  (`hideUnavailableItems`) y a fin de invierno quedaba 1. Con >0 la fila cumple
  la regla de las tres tiendas; en invierno puede volver a 0 y pintar el barrido
  de PARTIAL por categoría vacía, que es la señal funcionando.
* **20 — Descripción del producto en la ficha** → `store_products.description`,
  que llenan Día y Carrefour desde el próximo barrido (Coto no expone
  descripción: su BFF de listado sólo repite el nombre y no hay endpoint público
  de detalle). Medido sobre 97 productos: ~41% trae texto, y
  `vtex.clean_description()` descarta la plantilla de marca propia de Carrefour,
  el HTML sin texto y el nombre repetido — quedan ~32%, todas del producto.
  Sólo para mostrar (atribuida a la tienda en la ficha); **nunca** evidencia
  dietaria. CLAUDE.md etapas 2 y 6.
* **Carrito de Coto** (pedido fuera del backlog) — investigado: Coto agrega al
  carrito con un POST a su API ATG (`cCarritoActor/addOrRemoveItemToOrderV2`) que
  depende de las cookies de coto.com.ar, así que SmartCart no puede llamarlo, y
  no hay carrito por URL. Lo único que funcionaría es un bookmarklet o una
  extensión corriendo dentro de coto.com.ar; **AV lo descartó** por ser sólo de
  escritorio. Se arregló el problema de fondo que sí tenía solución: el botón que
  abría N pestañas (y el navegador bloqueaba desde la segunda) es ahora una
  lista con un link por producto. Y se agregó la salida para quien no quiere
  pasar por eso: **deshabilitar supermercados** en el carrito
  (`user_excluded_stores`), que los saca del optimizador y de los precios de la
  grilla. Razonamiento del endpoint en el comentario de `VTEX_CHECKOUT_DOMAINS`
  (`src/api.py`).
* **Sección Limpieza** (pedido fuera del backlog) — seis góndolas: papel
  higiénico, rollos y servilletas, detergente, jabón para la ropa, suavizantes y
  lavandina. Dos nodos de Día quedaron afuera a propósito por mezclar otra
  góndola en la misma hoja (servilletas con pañuelos, jabón en barra con
  aprestos). Ver el ítem 21 para lo que no resuelve.
* **Día reorganizó su taxonomía y 20 claves estaban muertas** (encontrado al
  agregar Limpieza, sep-2026) — todo Desayuno (`desayuno/…` pasó a
  `desayuno-y-merienda/…`) y casi todo Congelados devolvían 0 productos, o sea
  que Día no aportaba nada a 15 góndolas. Se regeneró
  `src/scrapers/dia_categories.json` y se remapearon las claves. Es exactamente
  el caso que `categories_empty` (CLAUDE.md etapa 10) existe para hacer ruidoso:
  si el barrido nocturno lo venía marcando PARTIAL, nadie lo había leído.
* **4 — Modelo multilingüe → medido y descartado, no se migra.** Se corrió
  `medir_busqueda.py` con los dos candidatos contra una copia local del
  catálogo (12.961 productos, dump de sólo lectura de Neon — la base de
  producción no se tocó en ningún momento de la medición):

  | modelo | total | leche | arroz | queda igual (antes 10/10) |
  |---|---|---|---|---|
  | `all-MiniLM-L6-v2` (actual) | 79/100 | 1/10 | 0/10 | — |
  | `paraphrase-multilingual-MiniLM-L12-v2` | 50/100 | 3/10 | 0/10 | aceite 10→1, cerveza 10→0, queso 10→4 |
  | `multilingual-e5-base` | 70/100 | 5/10 | 3/10 | fideos 10→1, aceite 10→2 |

  Los dos candidatos mejoran `leche` y `arroz` un poco, pero **rompen queries
  que hoy andan perfectas** — la caída neta es peor que el hueco que venían a
  cerrar. `multilingual-e5-base` corrió sin el prefijo `"query: "`/`"passage:
  "` que la familia e5 espera (`medir_busqueda.py` y `embeddings.py` no lo
  aplican a ningún modelo): puede ser parte de por qué le fue mejor que al
  otro candidato pero seguir perdiendo contra el actual; si alguna vez se
  retoma este ítem, probar eso primero antes que un tercer modelo. Se deja
  `all-MiniLM-L6-v2`. Lo que sí se corrigió de una, independiente del
  resultado: el nombre del modelo estaba hardcodeado dos veces
  (`src/api.py` y `src/embeddings.py`) y ahora es una sola constante,
  `DEFAULT_EMBEDDING_MODEL` en `src/embeddings.py`, que `api.py` y
  `medir_busqueda.py` importan — era el error exacto que este ítem advertía
  que una migración de modelo podía cometer.
