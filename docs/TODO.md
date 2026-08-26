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

### 2. Precio por unidad de medida — expuesto, con dos cosas pendientes
Corrigiendo la premisa original de este ítem: **no era cierto que no estuviera
expuesto**. `formatUnitPrice()` ya existía y `ProductCard` ya lo mostraba — pero
mal: dividía por `total_volume_weight` y escribía `"$0,02 x g"`, sin normalizar a
ninguna base legible. Eso ya está arreglado, junto con devolver `null` para
`unit_type = 'un'` y para cualquier unidad fuera del vocabulario (`'un'` es lo que
devuelve `normalize_magnitude()` cuando se dio por vencido, y ahí
`total_volume_weight` es el placeholder `1.0`).

**Pendiente 1: pasar a base única por kilo / litro.** Hoy hay un corte en 1000
(por 100 g / 100 ml abajo, por kilo / litro de ahí en adelante). La decisión es
sacarlo y usar siempre kilo para `'g'` y litro para `'ml'`. Medido sobre el
catálogo real: cambia la etiqueta del **89%** de los productos, la mediana queda
en **$14.929/kg** (perfectamente legible) y **275 productos (4,5%)** pasan de
$100.000/kg — el extremo es un azafrán de 0,375 g que muestra $9.710.526/kg.

Se acepta ese costo a propósito. El argumento a favor del corte era que un número
enorme en un envase chico se lee como un error de tipeo, y es cierto; pero dos
bases distintas conviviendo en la misma grilla rompen justamente la comparabilidad
que es el motivo entero del ítem. Una sola base gana.

**Pendiente 2: los multipacks.** El frontend no puede resolverlo, y el arreglo de
fondo es del ingest — decidir pack-vs-unidad donde está la evidencia del payload
scrapeado, al lado de `src/size_parser.py`. Portar `extract_pack_count()` a JS no
alcanzaría: el número al lado del `xN` es indecidible desde el nombre (a veces es
el total del pack, a veces el tamaño de cada unidad). Como el peso no se
multiplica, el error sólo puede ir hacia **caro** (N× de más cuando el tamaño
guardado era el unitario), que es la dirección que el proyecto acepta en todos
lados.

Corrigiendo un error de hecho que quedó escrito acá la vez pasada: se decía que
`units_per_pack` "llega siempre `NULL`", y es **falso**. La columna tiene
`DEFAULT 1`, así que las 6.401 filas dicen **`1`**. Es peor que `NULL`: un `NULL`
se lee como "no se sabe", mientras que un `1` afirma "no es un pack" — y **287
productos (4,5%) sí lo son**. Ver el ítem 14.

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


### 14. `units_per_pack` no la escribe nadie — sacarla de la API
Rastreada de punta a punta: **no está en el `INSERT INTO unified_products` ni en su
`ON CONFLICT DO UPDATE SET`** (`src/database.py:161-186`), ningún scraper emite la
clave, y `src/scripts/backfill_units.py` sólo toca `unit_type` y
`total_volume_weight`. La leen 4 `SELECT` de `src/api.py` (`/search`, `/category`,
`/products/by-ids`), que la copian a `UnitInfo` — y ahí muere: **ningún consumidor
la usa para decidir nada**, ni el backend ni el frontend.

Como la columna tiene `DEFAULT 1`, no llega vacía sino afirmando "no es un pack"
para los 6.401 productos, 287 de los cuales sí son packs. Un dato falso con cara
de dato bueno es peor que un `NULL`, y ya hizo perder tiempo una vez.

La decisión es **sacarla de la API** en vez de poblarla: el `unit_price` calculado
que pide el ítem 2 va a nacer en el backend con la evidencia del ingest, no de
esta columna. Toca los 4 `SELECT`/`GROUP BY` de `src/api.py`, el campo de
`UnitInfo`, el fixture de `tests/test_products_by_ids.py` y el ejemplo de
`docs/smartcart_spec.md`.

Dos avisos para el que lo agarre:

- **No dropear la columna primero.** Los tres endpoints la SELECTean hoy; dropearla
  sin sacar los SELECT hace que `psycopg` tire `UndefinedColumn` y los tres
  contesten 500. Primero el código, después (si se quiere) la base.
- **El gate de multipacks no depende de esto.** `src/substitutions.py:122`
  recalcula `extract_pack_count(name)` al vuelo, así que sacar la columna no toca
  la sustitución.

### 15. `source_category` en NULL para Coto y Día — no es un bug, falta un barrido
Medido: NULL en **3.252/3.252** filas de Coto, **1.529/1.529** de Día y **138/4.065**
de Carrefour. La explicación es la cronología, no un scraper roto: la columna se
agregó el **2026-08-24** (commit `3598b73`) y las filas de Coto y Día se escribieron
por última vez el **2026-08-21**. Carrefour sí se barrió después, y tiene el dato
salvo las 138 filas que ese barrido no alcanzó — el mismo número que ya documenta
la etapa 2 de CLAUDE.md. Los tres scrapers emiten la clave (`scraper_coto.py:214`,
`scraper_dia.py:214`, `scraper_carrefour.py:238`) y está en el
`ON CONFLICT DO UPDATE SET`, así que **cualquier barrido las llena**.

Consecuencia mientras tanto, que conviene entender antes de "arreglar" nada:

- Si un barrido de Coto o Día vuelve **PARCIAL**, el pruning acotado no borra nada:
  la comparación es `source_category = ANY(%s)` y una fila `NULL` nunca la
  satisface. Seguro, pero inerte.
- Si vuelve **completo**, poda igual, porque ahí `prune_scope` es `None` y el DELETE
  no se acota.

Nota al margen para cortar una búsqueda inútil: **`source_category_id` no existe**
— ni en el esquema ni en el repo. La columna que sí está y aparece en NULL para
Coto es `store_item_id`, y ahí el NULL es **correcto**: es el `itemId` de VTEX que
arma el link de checkout de Día y Carrefour, y Coto no es VTEX.

### 16. Ningún test verifica que los scrapers emitan `source_category`
El riesgo silencioso que destapó el ítem 15. `save_store_products` lee la clave con
`prod.get('source_category')` (defensivo), y los dos scrapers VTEX tienen el
parámetro con default `None`. O sea que un scraper que dejara de mandarla **no
rompería nada**: escribiría `NULL` en silencio, y a partir de ahí todo barrido
parcial podaría **cero** filas reportando `deleted: 0` con `skipped: False` —
indistinguible de "no se dio de baja nada".

Los únicos `source_category` en `tests/` son el fixture propio de `test_pruning.py`
y un docstring de `test_orchestrator.py`; ninguno mira la salida real de un
scraper. Falta una aserción de que cada uno pone la clave. Es barato: los tests de
`test_scraper_truncation.py` ya montan respuestas falsas por tienda.

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

### 19. Alias de góndola para categorías fuera de la tabla
`shelf_tags()` resuelve el problema de vocabulario **solo** para las claves que
están en `SHELVES`. Una categoría scrapeada por fuera vuelve a depender de que
las cadenas nombren igual el mismo estante, que es la brecha que documenta la
etapa 7 de CLAUDE.md (Carrefour archiva el vinagre en `aceites-y-vinagres` y Día
en `aceites-y-aderezos`; no solapan).

**No aflojar el `&&` a un umbral de similaridad** — ver la discusión del 0.90 en
la etapa 4: pares genuinamente duplicados y pares meramente hermanos ocupan la
misma banda de similaridad, así que ningún umbral los separa.
