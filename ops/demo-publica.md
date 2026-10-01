# Publicar la demo

Cómo poner SmartCart en un link que se le pueda mandar a alguien que no tiene
nada instalado.

No reemplaza a `ops/README.md`, que describe dónde corre el **barrido
nocturno**. Esto es el otro eje: dónde corren la **API** y el **frontend** para
que alguien los use desde su celular. La base es la misma de siempre (Neon), y
el barrido sigue corriendo igual en GitHub Actions.

| pieza | dónde | por qué ahí |
|---|---|---|
| Base | Neon (ya está) | no cambia nada |
| API | **Google Cloud Run** | CPU real, 1 GiB holgado, escala a cero |
| Frontend | Vercel | build de Vite, deploy por push |

## Por qué Cloud Run

La API carga `all-MiniLM-L6-v2` para codificar las búsquedas. El pico medido es
**413 MB** de RSS bajo `/optimize`, que es el camino más pesado (CP-SAT, flatten,
swaps y sugerencias); en reposo son 402 MB.

Lo que se descartó, y por qué:

* **Hugging Face Spaces** — era el plan original y **dejó de servir**: la
  pantalla de creación ahora dice *"Gradio and Docker Spaces require a paid
  plan. Static Spaces stay free for everyone"*. Sólo el SDK Static sigue gratis,
  y eso no corre un backend.
* **Render free** — 0,1 CPU y 512 MB. Los 413 MB entran por 100 MB de aire, pero
  0,1 de CPU cargando torch en cada arranque en frío es lento de más.
* **Koyeb** — su plan gratuito ya no ofrece un web service claro.
* **La VM de Oracle** — sigue bloqueada por capacidad ajena (`ops/README.md`).

Cloud Run **pide una tarjeta** para activar la facturación, pero no cobra dentro
del free tier: **180.000 vCPU-segundos, 360.000 GiB-segundos y 2 millones de
requests por mes**, verificado en su página de precios. Con 1 vCPU / 1 GiB eso
son ~50 h de CPU facturable por mes, que para una demo sobra por dos órdenes de
magnitud.

### Self-hostear en una PC de casa: evaluado y descartado

La pregunta se hizo y se va a volver a hacer, así que queda contestada acá.

**Es técnicamente viable.** Una PC de escritorio no necesita IP pública ni abrir
puertos: **Tailscale Funnel** es gratis en todos los planes, da un hostname
HTTPS estable (`equipo.tailnet.ts.net`), y funciona sobre conexiones salientes,
o sea que atraviesa el CGNAT que usan casi todos los ISP argentinos. Sólo
escucha en 443, 8443 y 10000, y tiene límites de ancho de banda no publicados.
**ngrok free NO sirve para esto**: su plan gratuito inserta una página
intermedia en los endpoints HTTP/S, y eso rompe las llamadas XHR que el frontend
le hace a la API.

**Y la comparación honesta no es "Cloud Run vs la PC" sino "Cloud Run + Neon vs
la PC sola".** Lo que más se ganaría self-hosteando no es ahorrarse Cloud Run
—que ya sale $0— sino poder mover Postgres a esa misma máquina y sacarse de
encima el techo de **100 CU-hours** de Neon, que `ops/README.md` llama *"el techo
que importa, no el storage"*. Ésa es, de hecho, la arquitectura que el proyecto
tiene documentada como destino: la VM de Oracle es exactamente eso.

Se descarta igual, por tres motivos en orden de peso:

1. **La PC no queda prendida sola.** Habría que encenderla a propósito: son
   ~35-70 kWh al mes de electricidad real para servir un puñado de requests, y
   el techo de gasto del proyecto es $0.
2. **La falla es silenciosa, y ya pasó en esta misma máquina.** La etapa 10 de
   CLAUDE.md documenta que un cron bajo WSL2 nunca disparó porque Windows apaga
   la VM al quedar ociosa, y que ningún script lo arregla. En una ronda de
   feedback eso no se ve: la persona entra, no carga, no avisa, y el feedback se
   pierde sin dejar rastro de por qué.
3. **El techo de Neon todavía no aplica.** Los 60-120 CU-hours son *con usuarios
   reales*, no con cinco amigos durante una semana. Mudarse ahora es pagar la
   complejidad antes de que exista el problema.

**Se volvió a plantear en sep-2026, por el arranque en frío** ("se cae a los 5
minutos y tarda un minuto en levantar"). Ese síntoma no es de Neon: la base se
suspende a los 5 minutos pero despierta en 1-3 s; los ~30 s son de Cloud Run
cargando el modelo (ver *Lo que hay que saber antes de mandar el link*). Mudar la
base a la PC no lo arregla, y mudar la API para arreglarlo es exactamente lo
descartado arriba. Se resolvió con un ping, sin mudar nada.

**Qué daría vuelta la decisión**, para no rediscutirla desde cero: que la PC
pase a quedar prendida por otro motivo, o que SmartCart junte usuarios y Neon
empiece a apretar. En los dos casos la mudanza es barata **por diseño** —dos
variables de entorno y el mismo `Dockerfile`, ver `ops/README.md`— y el paso
correcto sería llevar también Postgres a esa máquina, no sólo la API.

## 1. La API en Cloud Run

1. Crear un proyecto en <https://console.cloud.google.com> y activar la
   facturación (pide tarjeta; no cobra dentro del free tier).
2. Instalar el CLI: <https://cloud.google.com/sdk/docs/install>. Después:

   ```bash
   gcloud auth login
   gcloud config set project TU-PROYECTO
   gcloud services enable run.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com
   ```

3. Guardar la cadena de conexión de Neon como secreto, en vez de pasarla por
   línea de comandos — ahí queda en el historial del shell y en la descripción
   del servicio:

   ```bash
   printf '%s' 'postgresql://...neon.tech/smartcart?sslmode=require' | gcloud secrets create smartcart-db-url --data-file=-
   ```

4. Desplegar. `--source .` construye con Cloud Build usando el `Dockerfile` de
   la raíz. **Este es el comando para correr cada vez que cambia algo en
   `src/` o en el `Dockerfile`** — no hay redeploy automático del backend
   (a diferencia del frontend en Vercel, que sí redeploya solo con cada push a
   `main`):

   ```powershell
   gcloud run deploy smartcart-api --source . --region us-east1 --memory 1Gi --cpu 1 --min-instances 0 --max-instances 3 --cpu-boost --allow-unauthenticated --env-vars-file ops/vars.YAML --set-secrets DATABASE_URL=neon-url:latest
   ```

   Escrito en una sola línea a propósito: en PowerShell (Windows), el `\` de
   continuación de línea de bash no significa nada (ahí se usa `` ` ``), así
   que un comando multilínea copiado tal cual de una guía en bash tira
   `Missing expression after unary operator '--'` — una sola línea evita el
   problema de raíz. `--env-vars-file ops/vars.YAML` reemplaza a
   `--set-env-vars` con valores separados por coma: en Windows, `gcloud` es un
   `.cmd` que vuelve a parsear los argumentos a través de `cmd.exe`, y ahí una
   coma sin comillas es un separador de argumentos igual que un espacio — dos
   variables separadas por coma terminaban pegadas en una sola con un espacio
   en el medio (`'0 ANALYTICS_ENV=demo'`), y como esa cadena ya no era un
   entero válido, `SmartCartDB` explotaba en el arranque. `neon-url` es el
   nombre real del secreto en este proyecto (`gcloud secrets list` lo
   confirma) — el nombre `smartcart-db-url` de una versión anterior de esta
   guía nunca existió acá.

   La primera vez tarda ~10 minutos (baja torch). Al terminar imprime la URL del
   servicio.

5. Verificar que `https://TU-SERVICIO.run.app/` conteste `model_loaded: true` y
   `db_pool.enabled: true`, y probar `/search?q=yerba` y `/demo-cart`.

### Las decisiones del deploy, y por qué

* **1 GiB y no 512 MiB.** El pico medido es 413 MB. Con 512 MiB quedan 100 MB de
  aire, y un OOM en Cloud Run se ve como un 503 sin explicación. El
  GiB-segundo de más sale de un presupuesto que sobra.
* **`us-east1`.** La base está en Neon `us-east`, y `/optimize` hace varias idas
  y vueltas a la base por request: la latencia API↔base pesa más que la de
  usuario↔API. El free tier está cotizado sobre `us-central1` y ambas son Tier 1.
* **`--max-instances 3`.** Cloud Run **no tiene tope duro de gasto**, así que
  ésta es la cota real: acota el peor caso a tres instancias. Conviene además
  crear una **alerta de presupuesto en USD 1** — es una notificación, no un
  corte, y hay que saberlo.
* **`--min-instances 0`.** Es lo que lo mantiene gratis: sin tráfico no hay
  instancia y no se factura nada. Lo que se paga a cambio es el arranque en frío
  (ver abajo). `--min-instances 1` lo eliminaría, pero una instancia siempre
  prendida son ~2,6 M vCPU-segundos al mes contra 180.000 gratis: se paga.
* **`--cpu-boost`.** Duplica la CPU (1 → 2 vCPU) durante el arranque y 10 s
  después, que es cuando se importa torch y se carga el modelo. Se cobra el CPU
  extra sólo en ese lapso: ~40 vCPU-segundos por arranque en frío, nada frente
  al free tier. Cuánto acorta el arranque no lo publica Google — hay que medirlo.
* **Sin `ANALYTICS_API_KEY`.** El analyzer corre en tu localhost y no es
  alcanzable desde Cloud Run; sin la clave no se emite nada y no rompe nada (ver
  etapa 9 de CLAUDE.md). `GET /` lo confirma: `analytics.enabled: false` con el
  motivo escrito.

### `SMARTCART_POOL_MIN_SIZE=0` decide si la demo sobrevive la semana

Neon suspende la base tras **5 minutos sin actividad**, y una conexión abierta
cuenta como actividad. El default del pool es `min_size=1`, o sea que sostiene
una conexión para siempre: la base nunca se suspende, consume ~1 CU-hour por
hora y los **100 CU-hours mensuales del plan gratuito se agotan en poco más de 4
días**. La base se apaga sola en medio de la ronda de feedback.

`SMARTCART_POOL_MAX_IDLE` ya viene en 60 segundos por la misma cuenta: con el
default de psycopg_pool (10 minutos), la última conexión de cada visita vive 10
minutos antes de que arranque el reloj de 5 de Neon, o sea 15 minutos facturados
por visita.

Lo que se paga a cambio es un handshake TCP+TLS en la primera consulta de cada
visita: milisegundos, una vez por sesión.

## 2. El frontend en Vercel

Antes que nada, mergear a `main`: Vercel despliega la rama de producción del
repo, que por defecto es esa.

```bash
git checkout main && git merge demo-ready && git push
```

1. <https://vercel.com/new> → importar `aviollaz/SmartCart` (login con GitHub, no
   pide tarjeta).
2. **Root Directory**: `frontend`. El preset Vite lo detecta solo.
3. **Environment Variables**: `VITE_API_URL` = la URL de Cloud Run, sin barra
   final. Cargala **antes** del primer deploy: Vite la incrusta en el build, no
   la lee en runtime.
4. Deploy. Copiar la URL que queda (`https://smartcart-algo.vercel.app`).
5. **Cargar esa URL en `CORS_ORIGINS` dentro de `ops/vars.YAML`** y volver a
   correr el `gcloud run deploy` de arriba.

   Va en el archivo y **no** con un `gcloud run services update
   --update-env-vars` aparte: `--env-vars-file` reemplaza todas las variables
   del servicio, así que una variable cargada por fuera se borra en el próximo
   deploy. Pasó: tras un redeploy la demo dejó de cargar entera, sin ningún
   error del lado del servidor (todas las respuestas daban 200), porque el
   navegador bloqueaba cada respuesta por CORS. El síntoma se ve sólo en la
   consola del navegador, y se confirma con:

   ```powershell
   curl.exe -s -D - -o NUL -H "Origin: https://smart-cart-rouge.vercel.app" https://smartcart-api-996729163198.us-east1.run.app/categories
   ```

   Tiene que aparecer un `access-control-allow-origin` con la URL de Vercel.

De ahí en más, cada push a `main` redespliega el frontend solo. La API no: se
actualiza volviendo a correr el `gcloud run deploy` de arriba.

## Lo que hay que saber antes de mandar el link

* **El arranque en frío es el caso normal, no la excepción.** Con
  `--min-instances 0` la instancia se apaga tras ~15 minutos sin tráfico, y la
  primera visita paga el pull de la imagen más la carga del modelo. Medido
  (30-sep-2026, antes de `--cpu-boost`): **29,7 s en frío, 0,25 s en caliente**.

  ```powershell
  curl.exe -s -o NUL -w "%{time_total}`n" https://smartcart-api-996729163198.us-east1.run.app/
  ```

  **Un job de Cloud Scheduler lo tapa en horario de uso**: le pega a `GET /`
  cada 10 minutos entre las 8 y las 24 (hora de Argentina), así Cloud Run no
  llega a apagar la instancia. Se crea una vez, a mano (una línea cada uno):

  ```powershell
  gcloud services enable cloudscheduler.googleapis.com
  gcloud scheduler jobs create http smartcart-warm --location=us-east1 --schedule="*/10 8-23 * * *" --time-zone="America/Argentina/Buenos_Aires" --uri="https://smartcart-api-996729163198.us-east1.run.app/" --http-method=GET --attempt-deadline=120s
  gcloud scheduler jobs run smartcart-warm --location=us-east1
  ```

  Es gratis por dos lados: Cloud Scheduler regala 3 jobs por cuenta de
  facturación, y `GET /` **no toca la base**, así que Neon se sigue suspendiendo a
  los 5 minutos y no gasta CU-hours. **Nunca apuntarlo a `/search`,
  `/category/{slug}` ni `/demo-cart`**: despertaría la base cada 10 minutos, ~16 h
  de cómputo por día, el mes entero de Neon en menos de una semana.

  **Antes era un workflow de GitHub Actions (`warm-api.yml`) y no alcanzaba.** El
  cron de Actions no es puntual: el 1-oct-2026 pidió `*/10` y entregó huecos de
  15 a 35 minutos, y **16 de los 34 pings diurnos cayeron en un arranque en frío**
  (se ven como corridas de ~50 s contra ~8 s). Todos después de un hueco de 15
  minutos o más; ninguno con hueco de 14 o menos. O sea que el intervalo estaba
  bien y lo que fallaba era la puntualidad, que Cloud Scheduler sí garantiza.

  De noche se deja enfriar a propósito, así que antes de mandar el link a alguien
  a una hora rara, abrilo vos primero. `--min-instances 1` eliminaría todo
  arranque en frío, pero factura la instancia ociosa las 24 horas.

  Si el frío sigue molestando, la palanca de fondo es achicar la imagen sacando
  torch del runtime (la API sólo lo usa para codificar la query de `/search`):
  ver `docs/TODO.md`.
* **Neon suspende a los 5 minutos**, así que la primera consulta después de un
  rato tarda unos segundos más. Es la contrapartida directa de `min_size=0`.
* **El barrido nocturno corre igual** y puede cambiar precios en medio de una
  sesión. Es correcto, y de hecho es parte de la demo.
* **Recorré el flujo entero vos, desde el celular, con el link público, antes de
  mandarlo.** Es distinto de tu localhost en resolución, latencia y arranque en
  frío, que son las tres cosas que un tester nota primero.

## Cómo pedir el feedback

Una oración de qué es, el link, y **una tarea concreta**: *"armá el changuito de
una semana como si fueras a comprar de verdad, y apretá Optimizar"*. Sin tarea,
la mitad mira la home y contesta "está lindo".

**No expliques de antemano cómo funciona.** Cada cosa que tenés que aclarar por
WhatsApp es un lugar donde la interfaz no se explica sola, y es exactamente el
dato que fuiste a buscar. Anotá las aclaraciones que te piden: esa lista *es* el
resultado de la ronda.

Tres preguntas al final, que más no contesta nadie:

1. ¿En qué momento no entendiste qué estaba pasando?
2. ¿Le creerías al precio final como para ir a comprar?
3. ¿Qué te faltó para usarlo de verdad?

La 2 es la que importa: el producto entero es una promesa sobre plata, y todas
las decisiones asimétricas del proyecto —cotizar caro antes que barato, en los
flags dietarios, en los multipacks, en las membresías de Carrefour— existen para
sostenerla.

Si en algún momento lo mostrás en persona, el guion es el mismo pero mirás la
pantalla en vez de preguntar: anotá dónde dudan, no lo que dicen, y no toques el
mouse.
