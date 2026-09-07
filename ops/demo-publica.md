# Publicar la demo

Cómo poner SmartCart en un link que se le pueda mandar a alguien que no tiene
nada instalado. Todo gratis y sin tarjeta de crédito.

No reemplaza a `ops/README.md`, que describe dónde corre el **barrido
nocturno**. Esto es el otro eje: dónde corren la **API** y el **frontend** para
que alguien los use desde su celular. La base es la misma de siempre (Neon), y
el barrido sigue corriendo igual en GitHub Actions.

| pieza | dónde | por qué ahí |
|---|---|---|
| Base | Neon (ya está) | no cambia nada |
| API | Hugging Face Spaces, SDK **docker** | es el único gratis con RAM suficiente |
| Frontend | Vercel | build de Vite, deploy por push |

## Por qué Spaces y no un PaaS normal

La API carga `all-MiniLM-L6-v2` con torch para codificar las búsquedas: **~1 GB
de RAM**. Los planes gratuitos de Render, Koyeb y Fly dan 512 MB y el proceso
muere al arrancar — es la misma pared que tiene bloqueada la VM de Oracle
(`ops/README.md`). El CPU basic de Spaces da 2 vCPU y 16 GB, sin pedir tarjeta.

## 1. La API en Spaces

1. Crear un Space en <https://huggingface.co/new-space>: **SDK Docker**,
   visibilidad **Public**, hardware **CPU basic (free)**.
2. En **Settings → Variables and secrets**, cargar como *Secrets*:

   | nombre | valor |
   |---|---|
   | `DATABASE_URL` | el mismo de tu `.env` (el de Neon, con `?sslmode=require`) |
   | `SMARTCART_POOL_MIN_SIZE` | `0` — **no es opcional**, ver abajo |
   | `CORS_ORIGINS` | la URL de Vercel del paso 2, sin barra final |
   | `ANALYTICS_ENV` | `demo` |

   **`ANALYTICS_API_KEY` no se carga.** El analyzer corre en tu localhost y no es
   alcanzable desde el Space; sin la clave no se emite nada y no rompe nada (ver
   etapa 9 de CLAUDE.md). `GET /` lo confirma: `analytics.enabled: false` con el
   motivo escrito.

3. Empujar este repo al Space:

   ```bash
   git remote add space https://huggingface.co/spaces/TU-USUARIO/smartcart
   git push space main
   ```

   El build tarda ~10 minutos la primera vez (baja torch). Después es cuestión
   de capas cacheadas.

4. Verificar: `https://TU-USUARIO-smartcart.hf.space/` tiene que contestar
   `model_loaded: true` y `db_pool.enabled: true`. Probar también
   `/search?q=yerba` y `/demo-cart`.

### `SMARTCART_POOL_MIN_SIZE=0` es lo que decide si la demo sobrevive la semana

Neon suspende la base tras **5 minutos sin actividad**, y una conexión abierta
cuenta como actividad. El default del pool es `min_size=1`, o sea que sostiene
una conexión para siempre: la base nunca se suspende, la API prendida consume
~1 CU-hour por hora y los **100 CU-hours mensuales del plan gratuito se agotan
en poco más de 4 días**. La base se apaga sola en medio de la ronda de feedback.

`SMARTCART_POOL_MAX_IDLE` ya viene en 60 segundos por la misma cuenta: con el
default de psycopg_pool (10 minutos), la última conexión de cada visita vive 10
minutos antes de que arranque el reloj de 5 de Neon, o sea 15 minutos
facturados por visita. Veinte visitas sueltas en un día son 5 horas.

Lo que se paga a cambio es un handshake TCP+TLS en la primera consulta de cada
visita: milisegundos, una vez por sesión.

## 2. El frontend en Vercel

1. <https://vercel.com/new> → importar el repo de GitHub (login con GitHub, no
   pide tarjeta).
2. **Root Directory**: `frontend`. El preset Vite lo detecta solo.
3. **Environment Variables**: `VITE_API_URL` = la URL del Space, sin barra final.
4. Deploy. Después, volver al Space y poner esa URL de Vercel en `CORS_ORIGINS`.

Va separado del Space a propósito. Durante una semana de feedback el frontend se
toca muchas veces, y en Vercel eso es un push (segundos) contra un rebuild de
imagen con torch (~10 minutos). Servirlo desde el mismo contenedor ahorraría
configurar CORS y pagaría ese rebuild en cada ajuste de texto.

## Lo que hay que saber antes de mandar el link

* **Un Space gratis se pausa tras ~48 h sin uso**, y volver a arrancar carga el
  modelo (~1 minuto). Abrilo vos un rato antes de mandar el link. Si molesta,
  `.github/workflows/keepalive.yml` ya es el patrón para pingearlo.
* **Neon suspende a los 5 minutos**, así que la primera consulta después de un
  rato tarda unos segundos. Es la contrapartida directa de `min_size=0`.
* **El barrido nocturno corre igual** y puede cambiar precios en medio de una
  sesión. Es correcto, y de hecho es parte de la demo.
* **Recorrer el flujo entero vos, desde el celular, con el link público, antes de
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
