# Imagen de la API, desplegada en Google Cloud Run (ops/demo-publica.md).
#
# Por qué Cloud Run y no un PaaS gratuito: la API carga `all-MiniLM-L6-v2` para
# codificar las búsquedas y el pico medido es **413 MB** de RSS (bajo /optimize,
# el camino más pesado). Render free da 0,1 CPU y 512 MB —entra por 100 MB, pero
# 0,1 de CPU con torch es lento—, Koyeb ya no ofrece un web service gratis, y
# Hugging Face Spaces movió el SDK Docker a un plan pagado. Cloud Run da CPU
# real, 1 GiB holgado y escala a cero, dentro de un free tier de 180.000
# vCPU-segundos por mes.
#
# La base sigue siendo Neon y el frontend sigue en Vercel. Acá va SÓLO la API.
FROM python:3.12-slim

# git lo necesita huggingface_hub para bajar el modelo. No está build-essential
# a propósito: psycopg[binary] y las ruedas de torch/ortools vienen compiladas,
# así que agregarlo sólo engorda la imagen.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git curl \
    && rm -rf /var/lib/apt/lists/*

# El contenedor NO corre como root y el HOME por defecto no es escribible:
# sin esto, sentence-transformers no puede escribir su caché y el
# arranque falla con un PermissionError que no menciona la caché.
RUN useradd -m -u 1000 app
ENV HOME=/home/app \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/home/app/.cache/huggingface

WORKDIR /app

# torch CPU-only, ANTES que el resto y desde el índice propio de PyTorch.
#
# No es una optimización opcional: `pip install sentence-transformers` resuelve
# torch desde PyPI, y esa rueda arrastra el runtime de CUDA entero (cuDNN,
# cuBLAS, NCCL y compañía). Medido: la imagen daba **10,3 GB** con un modelo que
# corre en CPU y una máquina que no tiene GPU. Fijando el índice CPU baja a
# ~1 GB. Importa por el tiempo de build del Space y por su cuota de disco.
#
# Va en su propia capa, y las dependencias antes que el código, porque cambian
# mucho menos seguido y bajar torch es lo que domina el build.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY --chown=app:app requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=app:app src ./src

USER app

# El modelo se baja EN EL BUILD y no en el primer arranque. Con scale-to-zero el
# arranque en frío es el caso NORMAL y no uno raro —Cloud Run apaga la instancia
# cuando nadie la usa, que es justamente lo que la mantiene gratis—, así que sin
# esto la primera persona que abre el link paga la descarga del modelo además de
# su carga.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Cloud Run INYECTA `PORT` y espera que el contenedor escuche ahí. El puerto no
# se puede fijar: si el proceso escucha en otro, el deploy falla el health check
# y el error no menciona el puerto. El default 8080 es el de Cloud Run, y deja
# que la imagen se pueda correr a mano sin pasar nada.
ENV PORT=8080
EXPOSE 8080

# Forma SHELL a propósito (sin corchetes): la forma exec no expande variables, y
# `--port $PORT` llegaría a uvicorn como el string literal "$PORT".
#
# El `exec` NO es decorativo y es lo que arregla la contrapartida de esa
# decisión: sin él uvicorn queda como hijo de /bin/sh, que es el PID 1, y el
# SIGTERM que Cloud Run manda al bajar la instancia se lo come el shell. El
# lifespan de FastAPI nunca corre su shutdown, o sea que `close_pool()` no cierra
# el pool y las conexiones a Neon quedan colgadas hasta que expiran solas — justo
# lo que SMARTCART_POOL_MIN_SIZE=0 existe para evitar. Con `exec`, uvicorn
# reemplaza al shell y recibe la señal él.
#
# Un solo worker: cada uno carga su propia copia del modelo, así que dos son
# ~800 MB para una demo sin concurrencia. El pool de conexiones ya asume un
# worker (src/db_pool.py), y Cloud Run escala con instancias, no con workers.
CMD exec uvicorn src.api:app --host 0.0.0.0 --port $PORT --workers 1
