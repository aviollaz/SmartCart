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
   la raíz:

   ```bash
   gcloud run deploy smartcart-api \
     --source . \
     --region us-east1 \
     --memory 1Gi --cpu 1 \
     --min-instances 0 --max-instances 3 \
     --allow-unauthenticated \
     --set-env-vars SMARTCART_POOL_MIN_SIZE=0,ANALYTICS_ENV=demo \
     --set-secrets DATABASE_URL=smartcart-db-url:latest
   ```

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
  (ver abajo).
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
5. **Volver a Cloud Run** y cargar esa URL en `CORS_ORIGINS`:

   ```bash
   gcloud run services update smartcart-api --region us-east1 \
     --update-env-vars CORS_ORIGINS=https://smartcart-algo.vercel.app
   ```

   Sin este paso el frontend carga pero no le entra ni un dato, y el error sólo
   se ve en la consola del navegador.

De ahí en más, cada push a `main` redespliega el frontend solo. La API no: se
actualiza volviendo a correr el `gcloud run deploy` de arriba.

## Lo que hay que saber antes de mandar el link

* **El arranque en frío es el caso normal, no la excepción.** Con
  `--min-instances 0` la instancia se apaga sin tráfico, y la primera visita
  paga el pull de la imagen más la carga del modelo. **Medilo** y anotá el
  número:

  ```bash
  curl -s -o /dev/null -w "%{time_total}\n" https://TU-SERVICIO.run.app/
  ```

  Si da más de ~10 s conviene achicar la imagen sacando torch del runtime (la
  API sólo lo usa para codificar la query de `/search`). Mientras tanto, abrí vos
  el link un rato antes de mandarlo.
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
