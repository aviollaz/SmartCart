"""
Configuración compartida del suite.

Existe por una sola razón, y es la misma que motivó `src/db_pool.py`: la base
dejó de estar en `localhost`. Los tests que tocan Postgres resuelven su cadena
con `resolve_conn_string()` (src/schema.py), cuyo orden es
`explícita > DATABASE_URL > docker-compose`. Pero **nadie llamaba a
`load_dotenv()` en el suite**: el único módulo que lo hace es `src/analytics.py`,
al importarse, así que un test lo heredaba de casualidad si su cadena de imports
pasaba por ahí, y no lo tenía si no.

`tests/test_schema.py` es el que lo destapó. Sin `DATABASE_URL` en el entorno
caía al default de docker-compose, no encontraba nada escuchando y su fixture
—que saltea en vez de fallar, a propósito, para que el suite corra sin Docker—
salteaba **las nueve aserciones de esquema**. `pytest` reportaba verde. Es
exactamente el modo de falla que esos tests existen para detectar (algo que se ve
sano y no está verificando nada), sólo que en los tests mismos.

`load_dotenv()` no pisa lo que ya esté exportado, así que un `DATABASE_URL`
puesto a mano en la shell —o el secreto en CI— le sigue ganando al `.env`.
"""
from dotenv import load_dotenv

load_dotenv()
