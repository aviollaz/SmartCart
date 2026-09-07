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

### 3. Comparar el split contra comprar en una sola tienda
**Hoy la respuesta de `/optimize` no puede contestar "¿valió la pena partir la
compra?".** Lo que existe es `price_savings` (`_compute_price_savings`,
`src/api.py:651`) dibujado por `SavingsPanel.jsx`: por cada línea del split, la
tienda **más cara** que tiene ese producto menos lo que se paga. Es una
comparación producto a producto, sin envío ni descuento bancario, y por eso no
es comparable contra `total_spent_net` — el panel lo aclara en pantalla.

O sea que el número que falta es otro: el costo total de poner todo el carrito
en Coto, todo en Día, todo en Carrefour. Es lo que decide si la complicación de
un split vale la pena, y puede perfectamente dar que **no**: partir la compra
duplica envíos, y en carritos chicos eso se come el ahorro por producto. No
asumir que la diferencia siempre es positiva.

**Referencia de diseño: el "Hacker Fare" de Kayak**, no las cadenas locales. Dos
pasajes de aerolíneas distintas porque sale más barato que uno solo es
literalmente el mismo producto que el split de carrito, **incluida la misma
objeción del usuario**: "¿vale la pena la complicación?". Cómo lo presentan
—ahorro adelante, contrapartidas explícitas, comparación contra la opción
simple— es una solución ya diseñada al problema.

Otras referencias más útiles que los súper locales: Instacart (mismo problema de
catálogo unificado multi-tienda, con blog de ingeniería público), Ocado, Picnic;
y los comparadores tipo Idealo / PriceSpy para el ranking de ofertas.

---

## Búsqueda y relevancia

Contexto: `GET /search` ya hace recuperar-y-reordenar en dos etapas con el bonus
por disponibilidad (`STORE_BONUS`, ver CLAUDE.md etapa 6). Lo que sigue es la
continuación natural.

### 4. Modelo multilingüe
`all-MiniLM-L6-v2` (fijado en `src/api.py` y en `src/embeddings.py:18`) está
entrenado principalmente en inglés. Esto **ya no es hipótesis**: hay una
medición, y cambia el diagnóstico lo suficiente como para que valga leerla antes
de migrar nada.

Se corrieron 10 queries de cabecera contra el catálogo real, contando cuántos de
los 10 primeros resultados caen en la góndola que corresponde
(`python -m src.scripts.medir_busqueda`):

| query | aciertos | primer resultado |
|---|---|---|
| `fideos`, `aceite`, `cerveza`, `yogur`, `queso`, `cafe`, `galletitas` | **10/10** | correcto |
| `yerba` | 9/10 | correcto |
| `leche` | **1/10** | *Dulce de leche Ser 400 g* |
| `arroz` | **0/10** | *Alfajor de arroz Chocoarroz* |

O sea que el modelo **no** está globalmente desalineado con el castellano, que es
lo que sugerían las tres distancias sueltas que este ítem citaba antes. Falla en
un patrón único y reconocible: **cuando la palabra buscada aparece como
modificador en el nombre de otra góndola**. "Leche" está adentro de "dulce de
leche" y de "chocolate con leche"; "arroz" adentro de "alfajor de arroz". Se
midió también `manteca` (contra "manteca de maní") y `sal`, con el mismo perfil.

**La consecuencia para este ítem es incómoda y conviene tenerla antes de
empezar: un modelo multilingüe no está garantizado que lo arregle.** El problema
no es que el modelo no sepa qué es la leche — es que "dulce de leche" contiene
literalmente la palabra y es, legítimamente, un vecino cercano. El ítem 5
(mitad léxica) tampoco lo resuelve solo, por el mismo motivo: BM25 sobre
"dulce de leche" matchea "leche" igual de bien.

Lo que sí se sabe es que el hueco es chico y que la información para cerrarlo ya
está en la base: el mejor producto de la góndola correcta está en los puestos
**10, 15, 9 y 2** respectivamente, a 0.056-0.113 de distancia del top-1 global.
O sea que **cualquier señal de góndola alcanza**; lo que falta es decidir cuál,
y eso es una decisión de diseño que conviene tomar con datos de uso reales.

Descartados, con su motivo, para que no se re-propongan:

* **Un bonus por góndola en el `ORDER BY` de `/search`.** Funciona (0.12 cubre el
  hueco medido) pero toca el ranking, y el costo también está medido: `yerba`
  hoy trae en el puesto 2 un *Yerba Mate en saquitos* de "Té e infusiones", un
  resultado bueno que el bonus empuja para abajo.
* **Resolver la góndola en `SearchBar` y rutear a `/categoria/<slug>`.** Más
  barato todavía y sin tocar el ranking, pero pone en el cliente una regla que
  decide qué ve el usuario: el frontend no calcula ni decide, y una segunda
  definición de "qué significa esta query" viviendo en JS se desincroniza sola.

**Antes de migrar, medir.** Correr `python -m src.scripts.medir_busqueda --modelo
<candidato>` y comparar
la tabla de arriba, no las distancias: una distancia más baja con los mismos
errores no sirve de nada. Costo de la migración: regenerar los ~12.900
embeddings (hay que poner `name_embedding` en NULL primero — el pipeline sólo
llena los nulos) y, si cambia la dimensión (los `multilingual-e5-*` usan 768),
recrear la columna `vector(384)` y el índice HNSW
(`EmbeddingPipeline.ensure_vector_extension_and_index()`). Candidatos:
`paraphrase-multilingual-MiniLM-L12-v2` (mantiene 384, o sea que no toca el
esquema) o `multilingual-e5-base`.

Un detalle aparte que salió del mismo relevamiento y no depende del modelo: el
nombre del modelo está **hardcodeado dos veces** (`src/embeddings.py:18` como
default de un parámetro y `src/api.py:234` como literal suelto), sin ninguna
constante compartida. Nada obliga a que el modelo que indexa y el que consulta
sean el mismo, y si se separan las distancias que salen no significan nada. Es
una línea, y es justo el error que una migración de modelo puede cometer.

### 5. Búsqueda híbrida: sumar la mitad léxica **[hipótesis]**
Para queries cortas y precisas ("oreo 354g", "coca 2.25") BM25 le gana a los
embeddings casi siempre; el vector brilla en queries vagas ("algo para untar sin
azúcar"). Hoy sólo está la mitad densa: grep de `tsvector|ts_rank|pg_trgm` sobre
`src/` da cero, `src/schema.py` incluido.

Postgres ya trae `tsvector`/`ts_rank` y `pg_trgm`, así que **no hacen falta
dependencias nuevas**: se fusionan las dos listas (Reciprocal Rank Fusion es lo
estándar) dentro del mismo CTE `pool` que ya existe. Probablemente la mejora más
grande por línea de código en un catálogo de este tamaño.

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

### 10. Helados: falta Carrefour
La única góndola de alimentos relevada que **no** entró al segundo tramo. Coto
tiene 150 productos y Día 48, pero `congelados/helados-y-postres` de Carrefour
devuelve **0 productos en vivo** aunque el nodo exista en su árbol de categorías,
así que no cumple la regla de las tres tiendas de `src/shelves.py`.

Dos hipótesis, sin verificar: que sea estacional (el relevamiento es de
principios de septiembre, arrancando la primavera) o que Carrefour los cuelgue de
otra rama. **Revisar en verano**; si aparecen productos es una fila más en la
tabla, con las claves de Coto y Día ya relevadas:

* Coto `catv00003247` (Helados en Pote), `catv00003248` (en Palito),
  `catv00003147` (Postres Helados), `catv00003183` (Yogur Helado)
* Día `congelados/postres-congelados`

### 11. Medir el consumo de Neon después del segundo tramo **[hipótesis]**
El catálogo pasó de 20 a 49 góndolas, así que el barrido nocturno pasa de ~77
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

---

## Cerrados

Se sacan del backlog. El razonamiento no se pierde: vive en CLAUDE.md, que es
donde se lee cuando se toca el código.

* **1** — Historial "Comprar de nuevo" / mis habituales → CLAUDE.md, sección de
  frontend, *Purchase history*. Incluye la regla de ventana de sesión (30 min,
  reemplaza en vez de anexar) y las cuatro alternativas descartadas.
* **2** — Precio por unidad de medida → CLAUDE.md etapa 6 (`_build_unit_price`).
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
