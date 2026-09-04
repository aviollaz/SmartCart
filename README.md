# SmartCart

Optimizador de canasta de compra para supermercados argentinos. Scrapea los
catálogos de **Coto, Día y Carrefour**, los unifica por EAN y calcula con un
solver de restricciones (Google OR-Tools) **cómo repartir el carrito entre las
tres cadenas gastando lo menos posible** — contemplando promociones, descuentos
bancarios, costos de envío y el mínimo de compra de cada tienda.

## Demo

<!-- ------------------------------------------------------------------------
     PENDIENTE: grabar la demo. Ver docs/TODO.md, sección Producto.

     Cómo publicarla SIN commitear el binario: arrastrar el archivo a un
     comentario de un issue de este repo (o a un Release). GitHub lo sube a su
     propia CDN y devuelve una URL; se pega acá y listo. Un .mp4 versionado lo
     paga cada clone para siempre.

     Reemplazar los dos bloques de abajo por:
       ![Demo](https://github.com/user-attachments/assets/UUID-DEL-GIF)
       https://github.com/user-attachments/assets/UUID-DEL-VIDEO
------------------------------------------------------------------------- -->

> **La demo en video todavía no está grabada.** Mientras tanto, el recorrido es:
> buscar productos → armar el carrito → *Optimizar* → ver el reparto por tienda,
> el ahorro y las sugerencias de reemplazo.

## Cómo funciona

1. **Scraping** — cada cadena expone una API interna (Coto un BFF REST, Día y
   Carrefour GraphQL de VTEX). Se barren **las mismas 49 góndolas en las tres**,
   que es lo que hace comparables los catálogos: comparar precios sólo sirve si
   las tres cadenas recorrieron el mismo estante.
2. **Unificación** — el EAN es la identidad del producto: `prod_<ean>`. Un
   producto que venden las tres cadenas es una fila con tres ofertas.
3. **Búsqueda semántica** — cada producto se vectoriza con
   `all-MiniLM-L6-v2` y se consulta con pgvector, así "gaseosa cola" encuentra
   Coca-Cola sin coincidencia literal.
4. **Optimización** — un modelo CP-SAT decide qué comprar en qué tienda,
   con el mínimo de compra como restricción dura y el gasto total (subtotal +
   envíos − descuento bancario) como función objetivo.

## Cómo correrlo localmente

### 1. Base de datos

```bash
docker-compose up -d
```

Levanta Postgres con `pgvector` en `localhost:5432` (usuario/clave/base:
`smartuser`/`smartpassword`/`smartcart`). El esquema se crea solo: `src/schema.py`
es DDL idempotente que se aplica al primer uso, no hay migraciones que correr.

### 2. Configuración

```bash
cp .env.example .env      # Copy-Item .env.example .env  en PowerShell
```

Para desarrollo local funciona tal cual viene. `.env.example` documenta cada
variable; la única imprescindible para apuntar el proyecto a otra base es
`DATABASE_URL`.

### 3. Poblar el catálogo

```bash
pip install -r requirements.txt
python -m src.scripts.run_scrapers
```

**Este paso es obligatorio y tarda unas 2-3 horas** con las tres tiendas: son 49
góndolas por cadena y el tiempo se lo llevan las pausas deliberadas entre pedidos
—para no parecer un bot—, no la red. En el barrido nocturno las tres tiendas
corren en paralelo, pero en local van una atrás de otra.

Para ver el proyecto andando sin esperar tanto, una sola tienda alcanza:

```bash
python -m src.scripts.run_scrapers --store dia     # ~25 min
```

> **Un producto sin embedding es invisible para `GET /search`.** El script
> genera los embeddings al final; si lo cortás antes de que termine, la base
> queda poblada y el buscador vacío. Es la forma más común de que un primer
> arranque parezca roto. Se regeneran solos volviendo a correr el script.

### 4. Backend

```bash
uvicorn src.api:app --reload
```

API en `http://localhost:8000`, documentación interactiva en `/docs`.
`GET /` reporta el estado (modelo cargado, pool de conexiones, analítica).

### 5. Frontend

```bash
cd frontend
npm install
npm run dev
```

App en `http://localhost:5173`. Le pega a la API vía `VITE_API_URL`
(`frontend/.env`), que **se lee en tiempo de build**: cambiarlo obliga a rehacer
el build.

## La base es derivada

No hay dump de ejemplo en el repo, y es a propósito: un barrido completo
reconstruye `unified_products`, `store_products` y los embeddings desde cero, y
corre todas las noches igual. Por eso tampoco hay backups ni migración de datos
al cambiar de servidor — mudarse es editar `DATABASE_URL` y correr un barrido.
Lo único que no es derivado es el carrito y el historial de compras, que viven en
el `localStorage` del navegador.

La base de producción es privada. Si querés probar el proyecto sin esperar el
barrido, pedí acceso de sólo lectura: la API está preparada para servir con un
rol sin permisos de escritura.

## Dónde corre

| | hoy |
|---|---|
| Barrido nocturno | GitHub Actions, 03:00 AR (`.github/workflows/scrape.yml`) |
| Base de datos | Neon (PostgreSQL administrado + pgvector) |
| API y frontend | local |

El detalle —por qué Actions y Neon, los límites del plan gratuito, y el
despliegue en Oracle Cloud que está diseñado pero bloqueado por capacidad— está
en [`ops/README.md`](ops/README.md), que es el archivo que dice cuál de los dos
está vigente.

## Tests

```bash
pytest                                   # suite completa
pytest tests/test_optimizer_correctness.py   # sin base ni modelo, corre siempre
```

No son tests unitarios aislados: `tests/test_api.py`, `test_search.py` y
`test_search_ranking.py` levantan la app real y consultan Postgres, así que
necesitan la base **arriba y poblada** (y descargan el modelo la primera vez).
La mayoría del resto es Python puro y corre sin nada levantado.

## Documentación

* [`docs/smartcart_spec.md`](docs/smartcart_spec.md) — especificación técnica y
  modelo de datos.
* [`docs/TODO.md`](docs/TODO.md) — pendientes y riesgos conocidos, con el
  razonamiento de cada uno.
* [`CLAUDE.md`](CLAUDE.md) — arquitectura etapa por etapa: qué decide cada
  módulo y por qué. Es el más detallado de los tres.
* [`ops/README.md`](ops/README.md) — dónde corre y cómo se opera.
