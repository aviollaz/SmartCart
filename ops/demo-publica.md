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
   | `CORS_ORIGINS` | la URL de Vercel, sin barra final — todavía no la tenés, se carga al final |
   | `ANALYTICS_ENV` | `demo` |

   El orden es medio circular: el Space necesita la URL de Vercel y Vercel
   necesita la del Space. Se resuelve arrancando por el Space —su URL sale
   del nombre, `https://TU-USUARIO-smartcart.hf.space`— y volviendo a cargar
   `CORS_ORIGINS` después del paso 2. Mientras tanto la API anda: CORS lo
   aplica el navegador, así que `curl` y `/docs` funcionan igual.

   **`ANALYTICS_API_KEY` no se carga.** El analyzer corre en tu localhost y no es
   alcanzable desde el Space; sin la clave no se emite nada y no rompe nada (ver
   etapa 9 de CLAUDE.md). `GET /` lo confirma: `analytics.enabled: false` con el
   motivo escrito.

3. Clonar el Space **una sola vez**, en un directorio hermano de éste:

   ```bash
   git clone https://huggingface.co/spaces/TU-USUARIO/smartcart ../smartcart-space
   ```

   HF va a pedir usuario y contraseña: la contraseña es un **access token** con
   permiso de escritura, que se saca en <https://huggingface.co/settings/tokens>.

4. Publicar la API:

   ```bash
   python ops/publicar_space.py ../smartcart-space
   ```

   El build tarda ~10 minutos la primera vez (baja torch); se sigue desde la
   pestaña **Logs** del Space. Después es cuestión de capas cacheadas.

   **El Space es un repo aparte y eso es a propósito, no una vuelta de más.**
   Spaces lee su configuración del **frontmatter YAML del `README.md`** en la
   raíz, así que empujar este repo tal cual le pisaría ese README con el de
   SmartCart —que no lo tiene, ni debería: GitHub dibuja el frontmatter como una
   tabla arriba de todo, en el archivo que es la carta de presentación del
   proyecto— y el Space se quedaría sin saber que es Docker. El script escribe
   el README del Space y copia sólo lo que la imagen necesita (`Dockerfile`,
   `requirements.txt`, `src/`), que es lo mismo que ya dice `.dockerignore`.
   Corre con `--dry-run` si querés ver qué haría.

5. Verificar: `https://TU-USUARIO-smartcart.hf.space/` tiene que contestar
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

Antes que nada, mergear a `main`: Vercel despliega la rama de producción del
repo, que por defecto es esa.

```bash
git checkout main && git merge demo-ready && git push
```

1. <https://vercel.com/new> → importar `aviollaz/SmartCart` (login con GitHub, no
   pide tarjeta).
2. **Root Directory**: `frontend`. El preset Vite lo detecta solo.
3. **Environment Variables**: `VITE_API_URL` = la URL del Space, sin barra final.
4. Deploy. Copiar la URL que queda (`https://smartcart-algo.vercel.app`).
5. **Volver al Space** y poner esa URL en `CORS_ORIGINS`. El Space se reinicia
   solo. Sin este paso el frontend carga pero no le entra ni un dato, y el error
   sólo se ve en la consola del navegador.

De ahí en más, cada push a `main` redespliega el frontend solo. La API no: se
actualiza con `python ops/publicar_space.py ../smartcart-space`.

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
