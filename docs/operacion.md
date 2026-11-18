# Operación de SmartCart

Dónde corre cada pieza, cómo se despliega y qué límites cuidar. El código se
explica en [`arquitectura.md`](arquitectura.md).

| pieza | dónde | cómo se actualiza |
|---|---|---|
| Barrido | GitHub Actions, programado 02:23 AR (`scrape.yml`) | solo, todos los días |
| Base | Neon, plan gratuito, proyecto en `aws-us-east-1` | la reescribe el barrido |
| API | Cloud Run, `smartcart-api` en `us-east1` | **a mano**, `gcloud run deploy` |
| Frontend | Vercel, `https://smart-cart-rouge.vercel.app` | solo, con cada push a `main` |
| Analítica | Cloud Run, `smartcart-analytics` en `us-east1` | a mano, desde su repo |

Todo entra en planes gratuitos. Si un cambio toca el contrato de la API,
desplegá el backend **antes** de pushear: Vercel publica el frontend apenas
llega a `main`.

## La base es derivada

Un barrido reconstruye catálogo y embeddings desde cero, así que no hay backups
ni dump de ejemplo, y mudar la base es cambiar `DATABASE_URL` y correr un
barrido. Hay dos excepciones:

- **El carrito y el historial** viven en el `localStorage` del navegador.
- **La analítica** (`smartcart_analytics`) está en el mismo proyecto de Neon y
  no se reconstruye: una mudanza tiene que copiarla.

El esquema se aplica solo (`src/schema.py`, DDL idempotente); no hay
migraciones.

## El barrido (GitHub Actions)

`scrape.yml` corre un job por tienda en paralelo y después uno de embeddings.
En paralelo porque Neon cobra el tiempo despierta, no el trabajo. Todos
comparten un `run_id`, así `scraper_execution_logs` muestra una sola corrida.
Una tienda caída no cancela a las otras (`fail-fast: false`), y dos corridas
nunca se pisan (`concurrency`).

- **Dura ~1 h 15 min:** Día y Vea ~45 min, Coto y Carrefour ~1 h 10 min.
- **GitHub lo demora.** Con el cron en `0 6` salía a horario hasta el
  20-oct-2026; desde el 21 la demora creció a ~9 h, sin cambios nuestros. El
  18-nov se pasó a `23 5`, porque la hora en punto es donde GitHub apila los
  schedules. Si sigue tarde, la solución puntual es dispararlo desde Cloud
  Scheduler con `workflow_dispatch`.
- **Secreto `DATABASE_URL`** en *Settings → Secrets and variables → Actions*,
  con `?sslmode=require`. Sin él el job falla al instante, en vez de buscar el
  Postgres local.
- **A mano:** Actions → *Run workflow*. `tiendas` elige cuáles y `args` pasa
  flags al orquestador (`--prune-dry-run`, …). Desde la terminal:
  `gh workflow run scrape.yml`.
- **`keepalive.yml`** existe porque GitHub apaga los workflows programados tras
  60 días sin commits, y las corridas del cron no cuentan.
- **torch se instala del índice CPU de PyTorch.** El de PyPI trae CUDA y llenó
  el disco del runner el 26 y 27-sep-2026.

Cómo leer una corrida:

```sql
SELECT run_id, supermercado, status, items_scraped, duration_seconds, start_time
  FROM scraper_execution_logs ORDER BY id DESC LIMIT 12;
```

| estado | significa |
|---|---|
| `SUCCESS` | todas las categorías OK y poda hecha |
| `PARTIAL` | alguna categoría falló o volvió vacía, o se abortó la poda: **mirarlo** |
| `FAILED` | ninguna categoría OK |
| `RUNNING` sin cerrar | el proceso murió (timeout, OOM) |

`ops/probe_endpoints.py` (lo corre `probe.yml`) verifica que los endpoints de
los súper respondan desde donde corre el barrido. Exige content-type JSON y la
forma esperada, porque Coto contesta 200 con su HTML a cualquier ruta.

## La API (Cloud Run)

**No se despliega sola.** Después de cada cambio en `src/` o el `Dockerfile`,
desde la raíz del repo, en una línea:

```powershell
gcloud run deploy smartcart-api --source . --region us-east1 --memory 1Gi --cpu 1 --min-instances 0 --max-instances 3 --cpu-boost --allow-unauthenticated --env-vars-file ops/vars.YAML --set-secrets "DATABASE_URL=neon-url:latest,ANALYTICS_API_KEY=analytics-api-key:latest"
```

Tarda ~10 minutos. Verificá que `GET /` conteste `model_loaded: true` y
`db_pool.enabled: true`.

- **`--env-vars-file` reemplaza todas las variables del servicio.** Una cargada
  aparte con `--update-env-vars` se borra en el próximo deploy: pasó con
  `CORS_ORIGINS` y la app dejó de cargar. Toda variable va en `ops/vars.YAML`.
  Para chequear CORS:

  ```powershell
  curl.exe -s -D - -o NUL -H "Origin: https://smart-cart-rouge.vercel.app" https://smartcart-api-996729163198.us-east1.run.app/categories
  ```

  Tiene que aparecer `access-control-allow-origin`.
- **Secretos** (Secret Manager): `neon-url` y `analytics-api-key`. Sin la key no
  se emite analítica y no se rompe nada; `GET /` lo muestra en
  `analytics.enabled`.
- **1 GiB de memoria:** el pico medido es 413 MB, y un OOM se ve como un 503 sin
  explicación.
- **Misma región que Neon.** `/optimize` hace ~10 consultas en fila. Con Neon en
  São Paulo (hasta nov-2026) eran ~100 ms cada una. Se mudó la base y no la API
  porque Cloud Run en São Paulo es Tier 2 y el free tier rinde menos.
- **No hay tope duro de gasto.** Lo acotan `--max-instances 3` y una alerta de
  presupuesto, que avisa pero no corta.
- **El `Dockerfile`** respeta `$PORT` (forma shell a propósito), instala torch
  CPU (2,78 GB de imagen contra 10,3) y baja el modelo en el build.

### Arranque en frío

Con `--min-instances 0` la instancia se apaga sin tráfico: medido, 29,7 s en
frío contra 0,25 s en caliente, casi todo por cargar torch y el modelo. El job
de Cloud Scheduler `smartcart-warm` le pega a `GET /` cada 10 minutos de 8 a 24
(hora AR):

```powershell
gcloud scheduler jobs create http smartcart-warm --location=us-east1 --schedule="*/10 8-23 * * *" --time-zone="America/Argentina/Buenos_Aires" --uri="https://smartcart-api-996729163198.us-east1.run.app/" --http-method=GET --attempt-deadline=120s
```

**Nunca apuntarlo a un endpoint que consulte la base** (`/search`,
`/category/…`): `GET /` no la toca, así que Neon sigue
durmiendo. Despertarla cada 10 minutos gasta el mes de Neon en una semana. El
cron de Actions no sirve para esto porque llega con 15-35 minutos de demora.

Si el ping deja de alcanzar, la palanca es sacar torch del runtime (sólo
codifica la query de `/search`); ver issue #20.

## El frontend (Vercel)

Root Directory `frontend`, preset Vite. `VITE_API_URL` es la URL de Cloud Run
sin barra final, y Vite la incrusta en el build: cambiarla obliga a
redesplegar. Si cambia la URL de Vercel, sumala a `CORS_ORIGINS` en
`ops/vars.YAML` y redesplegá la API. `frontend/vercel.json` evita el 404 al
abrir directo una ruta de React Router.

## Neon: los límites suspenden, no cobran

| límite | plan gratuito | uso |
|---|---|---|
| Storage | 0,5 GB | ~110 MB estimados |
| Cómputo | 100 CU-hours/mes por proyecto | **el que importa** |
| Egress | 5 GB/mes | muy por debajo |

Neon duerme tras 5 minutos sin actividad, y una conexión abierta cuenta como
actividad. Por eso:

- **`SMARTCART_POOL_MIN_SIZE=0`** (en `ops/vars.YAML`). Con el default, 1, el
  pool mantiene una conexión, la base nunca duerme y el mes se gasta en ~4
  días.
- **`SMARTCART_POOL_MAX_IDLE`** = 60 s (default de `src/db_pool.py`). Con el de
  psycopg_pool, 10 minutos, cada visita facturaría ~15.

El costo es un handshake TCP+TLS por visita. Los CU-hours se ven en el panel de
Neon, no desde la base.

## Analítica (SmartCart Performance Analyzer)

Servicio aparte, `smartcart-analytics`, con su base `smartcart_analytics` en el
**mismo proyecto de Neon** que el catálogo: el evento sale de `/optimize`, que
ya despertó a Neon, así que no suma cómputo. Se armó una vez, a mano:

1. **Base.** En Neon, *Databases → New database* `smartcart_analytics`. Desde
   el repo del analyzer, con `ANALYTICS_DB_URL` apuntando a esa base:

   ```powershell
   Get-ChildItem db\init\*.sql | ForEach-Object { psql "$env:ANALYTICS_DB_URL" -v ON_ERROR_STOP=1 -f $_.FullName }
   ```

2. **Secretos.**

   ```powershell
   [IO.File]::WriteAllText("$PWD\key.tmp", (python -c "import secrets; print(secrets.token_urlsafe(32))"))
   [IO.File]::WriteAllText("$PWD\url.tmp", $env:ANALYTICS_DB_URL)
   gcloud secrets create analytics-api-key --data-file=key.tmp
   gcloud secrets create analytics-db-url --data-file=url.tmp
   Remove-Item key.tmp, url.tmp
   ```

   Para actualizar uno existente: `gcloud secrets versions add <nombre>
   --data-file=url.tmp`. La cuenta de servicio de Cloud Run necesita
   `roles/secretmanager.secretAccessor` sobre los dos.

3. **Deploy, desde la carpeta del analyzer.** Desde la de SmartCart,
   `--source .` publicaría la API bajo este nombre.

   ```powershell
   gcloud run deploy smartcart-analytics --source . --region us-east1 --memory 512Mi --cpu 1 --min-instances 0 --max-instances 2 --cpu-boost --allow-unauthenticated --set-env-vars "ENVIRONMENT=prod,POOL_MIN_SIZE=0" --set-secrets "DATABASE_URL=analytics-db-url:latest,ANALYTICS_API_KEY=analytics-api-key:latest"
   ```

   Con `ENVIRONMENT=prod` no arranca si la key es la de ejemplo.
   `--allow-unauthenticated` porque autentica la `X-API-Key`.

4. **Redeploy de `smartcart-api`**, para que tome la key.

**Verificar:** `GET /health` del analyzer → `{"status":"ok","db":"ok"}`; `GET /`
de la API → `analytics.enabled: true`; después de optimizar en la demo, una fila
en `fact_optimization` con `source_env = 'demo'`.

**Power BI** se conecta directo a Neon (base `smartcart_analytics`, modo
Import), filtrando `source_env = 'demo'`.

## Windows / PowerShell

- **Comandos en una línea:** el `\` de continuación de bash no existe.
- **Comillas en `--set-env-vars` y `--set-secrets`:** `gcloud` es un `.cmd` y una
  coma sin comillas parte el argumento (`Invalid secret spec`).
- **Secretos con `WriteAllText`, no con `|` ni `>`:** los dos agregan un salto
  de línea (y `>` escribe UTF-16), que rompe la cadena de conexión.

## Alternativas descartadas

- **AWS:** desde jul-2025 las cuentas nuevas reciben créditos, no free tier (~US$16/mes).
- **Hugging Face Spaces:** Docker pasó a pago.
- **Render free:** 0,1 CPU, demasiado lento para cargar torch.
- **Koyeb:** sin web service gratuito claro.
- **Oracle Always Free:** nunca entregó más de 1 OCPU / 1 GB en Santiago, y el
  modelo necesita ~1,5 GB (oct-2026).
- **Una PC de casa:** hay que dejarla prendida, y sus fallas son silenciosas (un
  cron bajo WSL2 nunca disparó porque Windows apaga la VM).

Si Neon empieza a quedar corto por usuarios reales, lo correcto es llevar
Postgres y la API a la misma máquina; la mudanza es `DATABASE_URL` y el mismo
`Dockerfile`.
