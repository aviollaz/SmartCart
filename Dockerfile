# Imagen de la API, pensada para Hugging Face Spaces (SDK "docker").
#
# Por qué HF Spaces y no un PaaS común: la API carga `all-MiniLM-L6-v2` con
# torch para codificar las búsquedas, o sea ~1 GB de RSS. Los planes gratuitos
# de Render, Koyeb y compañía dan 512 MB y el proceso muere al arrancar; el CPU
# basic de Spaces da 2 vCPU y 16 GB, sin tarjeta de crédito. Es el mismo motivo
# por el que la VM de Oracle sigue bloqueada (ops/README.md): 1 GB no alcanza.
#
# La base sigue siendo Neon y el frontend sigue en Vercel. Acá va SÓLO la API.
FROM python:3.12-slim

# git lo necesita huggingface_hub para bajar el modelo; el resto son las
# dependencias de compilación que psycopg[binary] NO necesita — por eso no está
# build-essential y la imagen queda chica.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git curl \
    && rm -rf /var/lib/apt/lists/*

# Spaces corre el contenedor como uid 1000 y el HOME por defecto no es
# escribible: sin esto, sentence-transformers no puede escribir su caché y el
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

# El modelo se baja EN EL BUILD y no en el primer arranque. Un Space gratis se
# pausa tras ~48 h sin uso, así que el arranque en frío es un caso normal y no
# uno raro: sin esto, la primera persona que abre el link después de una pausa
# espera la descarga del modelo además de su carga.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# 7860 es el puerto que Spaces expone por convención.
EXPOSE 7860

# Un solo worker a propósito: cada uno carga su propia copia del modelo, así que
# dos workers son ~2 GB de RAM para una demo que no tiene concurrencia. El pool
# de conexiones ya asume un worker (src/db_pool.py).
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
