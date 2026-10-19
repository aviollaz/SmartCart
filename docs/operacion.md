# Operación de SmartCart

Dónde corre cada pieza, cómo se actualiza y qué límites hay que cuidar. La
arquitectura del código está en [`arquitectura.md`](arquitectura.md).

| pieza | dónde | cómo se actualiza |
|---|---|---|
| Barrido nocturno | GitHub Actions, 03:00 AR (`.github/workflows/scrape.yml`) | solo, todas las noches |
| Base de datos | Neon (Postgres administrado + pgvector, plan gratuito) | la reescribe el barrido |
| API | Google Cloud Run, servicio `smartcart-api` en `us-east1` | **a mano**: `gcloud run deploy` (abajo) |
| Frontend | Vercel (`https://smart-cart-rouge.vercel.app`) | solo, con cada push a `main` |

Todo entra en los planes gratuitos. **Orden al publicar un cambio que toca el
contrato de la API:** primero el backend y después el push, porque Vercel
publica el frontend apenas llega a `main`.

## La base es derivada, y eso abarata todo

Un barrido completo reconstruye `unified_products`, `store_products` y los
embeddings desde cero. Por eso no hay backups, ni dump de ejemplo, ni migración
de datos al cambiar de servidor: mudarse es editar `DATABASE_URL` y correr un
barrido. Lo único que no es derivado es el carrito y el historial, que viven en
el `localStorage` del navegador. Esto se invierte el día que algo del usuario
viva en Postgres.

`src/schema.py` es DDL idempotente que se aplica solo (`SmartCartDB`,
`EmbeddingPipeline`, `ScraperTelemetry` y el `lifespan` de la API): no hay
migraciones que correr.

## El barrido nocturno (GitHub Actions)

`scrape.yml` abre **una matriz de un job por tienda** más uno de embeddings
(`needs:`). El `run_id` se genera una vez en un job previo y se pasa a todos con
`--run-id`, así `scraper_execution_logs` muestra **una** corrida. Corre en
paralelo por Neon, no por el reloj: Neon cobra el tiempo que la base está
despierta, así que lo que importa es el wall-clock del barrido. `fail-fast:
false` (una tienda caída no cancela a las otras) y `concurrency` a nivel
workflow (dos noches nunca se pisan).

* **Secreto `DATABASE_URL`** en *Settings → Secrets and variables → Actions*,
  con el `?sslmode=require` que trae Neon. Sin él el job falla al toque con un
  mensaje claro, en vez de intentar el Postgres del docker-compose.
* **Correr a mano:** Actions → *Run workflow*. El campo `tiendas` elige cuáles
  (`dia` abre un solo job más el de embeddings) y `args` pasa flags al
  orquestador (`--prune-dry-run`, …).
* **`keepalive.yml`** existe porque GitHub desactiva los workflows programados
  tras 60 días sin commits, y las corridas del cron no cuentan como actividad.
* **torch se instala desde el índice CPU de PyTorch.** El 26 y 27-sep-2026 todos
  los jobs murieron en `pip install` con *No space left on device*: torch desde
  PyPI arrastra el runtime de CUDA.

Cómo leer una corrida:

```sql
SELECT run_id, supermercado, status, items_scraped, duration_seconds, start_time
  FROM scraper_execution_logs ORDER BY id DESC LIMIT 12;
```

`SUCCESS` = todas las categorías OK y poda hecha. `PARTIAL` = alguna categoría
falló o volvió vacía, o la poda se abortó por sus frenos: hay que mirarlo.
`FAILED` = ninguna categoría OK. Una fila en `RUNNING` que nunca cerró es un
proceso que murió (timeout, OOM).

### El gate de endpoints

`ops/probe_endpoints.py` (lo corre `.github/workflows/probe.yml`) chequea las
superficies de los súper y exige **content-type JSON y la forma esperada**, no
sólo un 200: Coto sirve su `index.html` con 200 para cualquier ruta
desconocida. Hay que pasarlo desde cada lugar nuevo donde vaya a correr el
barrido. Hasta ahora ningún proveedor probado (local, Oracle/Santiago, Actions)
tuvo bloqueo por IP. Coto es bastante más lento desde fuera de Argentina; las
tiendas VTEX casi no cambian.

## La API (Cloud Run)

**El backend no se despliega solo.** Después de cada cambio en `src/` o en el
`Dockerfile`, desde la raíz del repo y en una sola línea:

```powershell
gcloud run deploy smartcart-api --source . --region us-east1 --memory 1Gi --cpu 1 --min-instances 0 --max-instances 3 --cpu-boost --allow-unauthenticated --env-vars-file ops/vars.YAML --set-secrets DATABASE_URL=neon-url:latest
```

Tarda unos 10 minutos. Para verificar: `GET /` tiene que contestar
`model_loaded: true` y `db_pool.enabled: true`.

* **`--env-vars-file ops/vars.YAML` reemplaza TODAS las variables del
  servicio.** Una variable cargada aparte con `--update-env-vars` se borra en el
  próximo deploy. Ya pasó con `CORS_ORIGINS`: la app dejó de cargar entera con
  todos los endpoints dando 200, porque el navegador bloqueaba por CORS. Toda
  variable va en `vars.YAML`. Para chequear CORS:

  ```powershell
  curl.exe -s -D - -o NUL -H "Origin: https://smart-cart-rouge.vercel.app" https://smartcart-api-996729163198.us-east1.run.app/categories
  ```

  Tiene que aparecer `access-control-allow-origin` con la URL de Vercel.
* **El secreto se llama `neon-url`** (Secret Manager), no `smartcart-db-url`.
* **1 GiB:** el pico medido es 413 MB bajo `/optimize`, y un OOM en Cloud Run se
  ve como un 503 sin explicación.
* **`us-east1`** porque Neon está en `us-east`: `/optimize` hace varias idas a la
  base por request.
* **No hay tope duro de gasto en Cloud Run.** La cota es `--max-instances 3`,
  más una alerta de presupuesto (avisa, no corta).
* **El `CMD` del Dockerfile respeta `$PORT`** (forma shell a propósito), instala
  torch CPU (la imagen pasó de 10,3 GB a 2,78 GB) y descarga el modelo en el
  build.
* **Sin `ANALYTICS_API_KEY`:** el analyzer no es alcanzable desde Cloud Run. Sin
  la clave no se emite nada y no se rompe nada.

### Arranque en frío

Con `--min-instances 0` la instancia se apaga sin tráfico. Medido: **29,7 s en
frío, 0,25 s en caliente**; casi todo es Cloud Run cargando torch y el modelo
(Neon despierta en 1-3 s). El job de Cloud Scheduler **`smartcart-warm`** le
pega a `GET /` cada 10 minutos entre las 8 y las 24 (hora argentina). Se creó
una vez, a mano:

```powershell
gcloud scheduler jobs create http smartcart-warm --location=us-east1 --schedule="*/10 8-23 * * *" --time-zone="America/Argentina/Buenos_Aires" --uri="https://smartcart-api-996729163198.us-east1.run.app/" --http-method=GET --attempt-deadline=120s
```

**Nunca apuntarlo a un endpoint que consulte la base** (`/search`,
`/category/{slug}`, `/demo-cart`): `GET /` no toca la base, así que Neon se sigue
suspendiendo. Despertarla cada 10 minutos gasta el mes de Neon en menos de una
semana. Reemplazó a un cron de GitHub Actions porque ese cron no es puntual:
pedido cada 10 minutos, entregaba huecos de 15-35 y la mitad de los pings caían
en frío.

La palanca de fondo es sacar torch del runtime (la API sólo lo usa para
codificar la query de `/search`); ver issue #20.

## El frontend (Vercel)

Root Directory `frontend`, preset Vite. `VITE_API_URL` = URL de Cloud Run sin
barra final. **Vite la incrusta en el build**: cambiarla obliga a redeployar. Si
cambia la URL de Vercel, hay que sumarla a `CORS_ORIGINS` en `ops/vars.YAML` y
redeployar la API. `frontend/vercel.json` tiene el rewrite que hace falta para
que las rutas de React Router no den 404 al abrirlas directo.

## Neon: los límites suspenden, no cobran

| límite | plan gratuito | uso |
|---|---|---|
| Storage | 0,5 GB | ~51 MB medidos con 20 góndolas; ~110 MB estimados hoy |
| Cómputo | 100 CU-hours/mes | **es el techo que importa** |
| Egress | 5 GB/mes | muy por debajo |

Neon suspende la base tras 5 minutos sin actividad, y una conexión abierta
cuenta como actividad. Por eso, en cualquier deploy contra Neon:

* **`SMARTCART_POOL_MIN_SIZE=0`** — con el default (1) el pool sostiene una
  conexión para siempre, la base nunca duerme y los 100 CU-hours se acaban en
  ~4 días.
* **`SMARTCART_POOL_MAX_IDLE`** ya viene en 60 s en `src/db_pool.py` — con el
  default de psycopg_pool (10 min) cada visita facturaría ~15 minutos.

La primera está en `ops/vars.YAML`. El precio es un handshake TCP+TLS por visita.
Los CU-hours se miran en el panel de Neon (issue #29); desde adentro de la base
no se ven.

## Windows / PowerShell

* Los comandos van **en una sola línea**: el `\` de continuación de bash no
  existe en PowerShell (`Missing expression after unary operator '--'`).
* `gcloud` en Windows es un `.cmd` que re-parsea los argumentos con `cmd.exe`, y
  una coma sin comillas separa argumentos. Por eso las variables van en
  `vars.YAML` y no en `--set-env-vars A=1,B=2`.
* Para un secreto, cuidado con colar caracteres: un `-n` de bash pegado en
  PowerShell ya rompió una vez la cadena de conexión ("couldn't get a connection
  after 10.00 sec").

## Alternativas evaluadas

Para no rediscutirlas desde cero:

* **AWS:** desde jul-2025 las cuentas nuevas reciben créditos en vez de free tier
  (~US$16/mes).
* **Hugging Face Spaces:** Docker pasó a pago.
* **Render free:** 0,1 CPU, demasiado lento para cargar torch.
* **Koyeb:** sin web service gratuito claro.
* **Oracle Always Free** (VM con systemd + Postgres local): sin tope de cómputo,
  pero nunca entregó más de 1 OCPU / 1 GB en Santiago, y el modelo necesita
  ~1,5 GB. Se descartó en oct-2026; el runbook quedó en el historial de git.
* **Una PC de casa con Tailscale Funnel:** viable, pero hay que dejarla prendida
  (electricidad real), y una falla de ese tipo es silenciosa (un cron bajo WSL2
  nunca disparó porque Windows apaga la VM).

Qué daría vuelta la decisión: que Neon empiece a apretar por usuarios reales.
Ahí la mudanza es barata por diseño (`DATABASE_URL` + el mismo `Dockerfile`), y
lo correcto es llevar Postgres y la API a la misma máquina.
