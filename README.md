# SmartCart

Optimizador de canasta de compra para supermercados argentinos. Scrapea los
catálogos de **Coto, Día y Carrefour**, los unifica por EAN y calcula con un
solver de restricciones (Google OR-Tools) **cómo repartir el carrito entre las
tres cadenas gastando lo menos posible** — contemplando promociones, descuentos
bancarios, costos de envío y el mínimo de compra de cada tienda.

## Cómo funciona

1. **Scraping** — cada cadena expone una API interna (Coto un BFF REST, Día y
   Carrefour GraphQL de VTEX). Se barren **las mismas 75 góndolas en las tres**,
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

**Este paso es obligatorio y tarda horas** (~1,5 h por tienda) con las tres tiendas: son 75
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
(`frontend/.env`, default `http://localhost:8000`), que **se lee en tiempo de
build**: cambiarlo obliga a rehacer el build. `npm run build` genera
`frontend/dist` y `npm run lint` corre oxlint.

## La base es derivada

No hay dump de ejemplo en el repo, y es a propósito: un barrido completo
reconstruye el catálogo y los embeddings desde cero, y corre todas las noches
igual. La base de producción es privada; si querés probar el proyecto sin
esperar el barrido, pedí acceso de sólo lectura (la API sirve con un rol sin
permisos de escritura).

## Dónde corre

El barrido nocturno corre en GitHub Actions, la base en Neon, la API en Google
Cloud Run y el frontend en Vercel. Cómo se despliega y qué límites cuidar está
en [`docs/operacion.md`](docs/operacion.md).

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

* [`docs/arquitectura.md`](docs/arquitectura.md) — cómo está hecho: cada etapa
  del pipeline, la API, el frontend y por qué se decidió cada cosa.
* [`docs/operacion.md`](docs/operacion.md) — dónde corre, cómo se despliega y
  qué límites hay que cuidar.
* [Issues](https://github.com/aviollaz/SmartCart/issues) — pendientes y riesgos
  conocidos, con el razonamiento de cada uno.
