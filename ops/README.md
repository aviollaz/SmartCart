# Dónde corre SmartCart

Este directorio tiene **dos** despliegues descritos, lo cual normalmente es un
olor a documentación podrida. Acá es deliberado y temporal, así que empieza por
la condición de salida.

## Estado, a 2026-08-31

| | hoy | destino |
|---|---|---|
| **Barrido nocturno** | GitHub Actions (`.github/workflows/scrape.yml`) | systemd en la VM (`ops/oracle/`) |
| **Base de datos** | Neon (plan gratuito) | Postgres en la misma VM |
| **API** | tu máquina (`uvicorn`) | la VM, detrás de nginx |

**Por qué no está todo en la VM ya:** Oracle no entrega capacidad. El Always Free
da 2 OCPU / 12 GB, pero crear la instancia devuelve *out of capacity* de forma
persistente en Santiago; lo único que entró fue **1 OCPU y 1 GB de RAM**, y con
1 GB no corre `all-MiniLM-L6-v2` — el modelo necesita ~1,5 GB y lo usan tanto la
API para codificar búsquedas como el barrido para generar los vectores. El resize
a 6 GB también falla. **No es un problema de diseño: es capacidad ajena.**

## La condición de salida

Se toma una de las dos ramas y **se borra la otra**. Sin fecha se convierte en la
deuda que este archivo intenta evitar:

* **Si Oracle entrega ≥6 GB** → se sigue `ops/oracle/README.md`, se borra
  `.github/workflows/{scrape,keepalive}.yml` y esta tabla.
* **Si a fin de octubre de 2026 no entregó** → se borra `ops/oracle/` entero y
  Actions + Neon pasa a ser la arquitectura, sin asterisco.

**Mudarse no cuesta migración de datos.** La base es derivada: un barrido completo
reconstruye `unified_products`, `store_products` y los embeddings en ~30 minutos,
y corre todas las noches igual. Es la misma razón por la que no hay backups
(`ops/oracle/README.md` §9). Cambiar de destino es cambiar `DATABASE_URL` y
correr un barrido.

## El gate que los dos comparten

`ops/probe_endpoints.py` — vive acá arriba y no adentro de `oracle/` porque lo
corren los dos caminos. Chequea **cuatro** superficies: el BFF de catálogo de
Coto, el actor ATG `getCobertura`, y los `productSearchV3` de Día y de Carrefour.
Para cada una exige **content-type JSON y la forma esperada**, no sólo un HTTP
200: el sitio de Coto sirve su `index.html` con 200 para cualquier ruta
desconocida, así que mirar sólo el status es parsear una página web creyendo que
son datos.

**Hay que pasarlo desde cada lugar nuevo donde vaya a correr el barrido.** Un
bloqueo por rango de datacenter o por geografía puede afectar a un proveedor y no
a otro:

| desde | fecha | Coto | cobertura | Día | Carrefour |
|---|---|---|---|---|---|
| local (Argentina) | 2026-08-28 | 300 ms | 50 ms | 232 ms | 229 ms |
| Oracle (Santiago) | 2026-08-31 | 516 ms | 168 ms | 769 ms | 624 ms |
| GitHub Actions | 2026-08-31 | 1454 ms | 611 ms | 372 ms | 352 ms |

**Las tres dieron las cuatro OK.** No hay bloqueo por IP de datacenter en ningún
proveedor probado.

El perfil de latencia cambia según dónde corras, y no de forma uniforme: **Coto es
mucho más lento desde afuera de Argentina** (sirve su API desde infraestructura
propia) mientras que **Día y Carrefour casi no se mueven** —corren sobre VTEX, que
es una plataforma con CDN global— y desde los runners de GitHub llegan a ser más
rápidos que desde Oracle. O sea que "más lejos" no predice el resultado: hay que
medirlo.

Ojo al leer esos números: el probe abre un cliente nuevo por sonda, así que cada
una paga DNS + TCP + TLS en frío. El barrido real reusa la conexión con
`httpx.Client` y sólo la primera request de cada host lo paga, así que la tabla
sobreestima el costo.

Sobre las latencias, ya medido: el barrido son unas **560 requests** (490 páginas
más una vacía por categoría para detectar el final). Aun a +200 ms cada una eso
suma menos de 2 minutos sobre un barrido de ~30, porque las pausas deliberadas de
los scrapers —para no parecer un bot— le ganan a la red por diez a uno.

## Poner Neon a andar

1. Crear cuenta en [neon.com](https://neon.com) (se puede con el login de GitHub;
   no pide tarjeta) y un proyecto con PostgreSQL 16 o 17, región **us-east**. Lo
   que importa es el RTT runner↔base, no Argentina↔base.
2. `CREATE EXTENSION IF NOT EXISTS vector;` — Neon lo soporta en el plan gratuito.
3. Copiar la connection string y cargarla en GitHub como secreto de repositorio:
   **Settings → Secrets and variables → Actions → New repository secret**, nombre
   `DATABASE_URL`. Conservar el `?sslmode=require` que viene: el default de
   psycopg (`prefer`) acepta texto plano si el servidor lo ofrece — pide, no exige.
4. Para trabajar en local contra esa misma base, la misma línea en tu `.env`.

**No hay migración que correr.** `src/schema.py` es idempotente y lo aplican
`SmartCartDB`, `EmbeddingPipeline`, `ScraperTelemetry` y el `lifespan` de la API.

## Los límites de Neon, que no cobran: suspenden

| límite | plan gratuito | uso de SmartCart |
|---|---|---|
| Storage | 0,5 GB por proyecto | **51 MB medidos** (10%) |
| Cómputo | 100 CU-hours/mes | ~20-40 para uso propio |
| Egress | 5 GB/mes | muy por debajo |

Los 51 MB son medición: `unified_products` pesa 38 MB (13 de ellos el índice
HNSW) y `store_products` 5 MB, sobre 6.401 y 8.846 filas. El techo de storage
está en ~64.000 productos, unas 10 veces el catálogo actual — pero **baja a
~47.000 si se hace el ítem 4 del TODO** (modelo multilingüe de 768 dimensiones),
porque el 43% de la base son embeddings.

**El cómputo es el techo que importa, no el storage.** La base duerme sola tras 5
minutos sin actividad, así que la cuenta es cuántas horas por día está despierta:
para vos solo son ~20-40 CU-hours, pero con usuarios reales y la base despierta
8 h/día ya son 60-120. Ese número es el que decidió intentar Oracle, y el que
vuelve a decidirlo cuando SmartCart tenga usuarios.

## Verificación

1. **`gh workflow run probe.yml`** — bloqueante, ver arriba.
2. Neon arriba: `psql "$DATABASE_URL" -c "SELECT version();"` y la extensión.
3. `pytest tests/test_schema.py` con el `.env` local apuntando a Neon: sólo
   re-emite el DDL idempotente y lee el catálogo, no toca datos.
4. **Barrido de una tienda, manual**: Actions → Run workflow → `args: --store dia`.
   Mirar el resultado y la fila en `scraper_execution_logs`.
5. Barrido completo: Run workflow sin argumentos. Verde y cuatro filas `SUCCESS`
   (coto/dia/carrefour/embeddings).
6. `uvicorn src.api:app` local contra Neon: `GET /` (reporta `db_pool`),
   `GET /search?q=yerba` y un `POST /optimize` desde el frontend.
7. **El schedule, con un cron a 10 minutos vista**, no esperando a las 3am.
   Después devolverlo a `0 6 * * *`.
8. A la semana: el panel de Neon (CU-hours y storage) y el historial de Actions.

```sql
SELECT run_id, supermercado, status, items_scraped, duration_seconds, start_time
  FROM scraper_execution_logs ORDER BY id DESC LIMIT 12;
```
