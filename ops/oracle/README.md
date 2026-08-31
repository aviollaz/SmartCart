# SmartCart en Oracle Cloud Always Free

Runbook para poner el backend entero —base, barrido nocturno y API— en una VM
gratuita de Oracle.

**Por qué**: el cron de las 03:00 corría bajo WSL2 y dependía de que la máquina
estuviera prendida; Windows cierra la VM sola tras un rato sin uso y el job
simplemente no disparaba, sin error y sin aviso. Y para que SmartCart lo use
alguien más, la API tiene que estar arriba sin tu notebook.

## La arquitectura

```
   internet ──HTTPS──► nginx ──► uvicorn (127.0.0.1:8000) ─┐
                        │                                  │
                        └── frontend/dist (estático)        ├──► Postgres
                                                            │    (localhost)
   systemd timer 03:00 ──► orchestrator ────────────────────┘
```

Todo en una máquina. Eso no es simplismo: es lo que hace que cada consulta de
`/optimize` cueste **menos de 1 ms** en vez de los ~200 ms que costaría contra una
base administrada remota — y `/optimize` abre varias por request.

## Costo

**US$0/mes, sin fecha de vencimiento y sin tarjeta.** Always Free de Oracle:
2 OCPU ARM + 12 GB de RAM + 200 GB de disco, sin tope de horas de cómputo. Ese
último punto es el que descartó a Neon, cuyo plan gratuito da 100 CU-hours por mes
—suficiente para uso propio, no para usuarios reales.

> **Ojo con los números viejos.** Oracle recortó el Always Free A1 a la mitad el
> 15-jun-2026 sin anunciarlo: era 4 OCPU / 24 GB, hoy son **2 OCPU / 12 GB**.
> Cualquier guía anterior a esa fecha te va a prometer el doble.

---

## 1. Cuenta y región — el paso irreversible

**Es el riesgo más alto de todo el plan y va primero.** Dos hechos que se combinan
mal:

* Los recursos Always Free **sólo existen en la región de origen**, que se elige
  al registrarse y **no se puede cambiar nunca**.
* Crear una instancia A1 devuelve *out of capacity* en muchas regiones, de forma
  persistente.

O sea: elegís a ciegas algo que no podés deshacer.

**Región recomendada: Santiago (`sa-santiago-1`)**, la más cercana a Buenos Aires
(~35 ms). São Paulo o Vinhedo son la alternativa.

Después de crear la cuenta, **lo primero es intentar crear la instancia** (paso 2).
Si no hay capacidad, no tiene sentido configurar nada más. Salidas conocidas:

1. **Reintentar.** La capacidad se libera; hay quien lo consigue al tercer intento
   y quien tarda días.
2. **Pasar a Pay-As-You-Go.** Destraba A1 de inmediato y **los recursos Always
   Free siguen siendo gratis**. Pide tarjeta, así que va con un presupuesto y
   alerta en US$1 configurados *antes*. Es la salida, no el punto de partida.

## 2. La instancia

`VM.Standard.A1.Flex`, **2 OCPU y 12 GB**, Ubuntu 24.04 LTS, boot volume 50 GB.
Guardar la clave SSH que ofrece el asistente: no hay segunda oportunidad.

**Security list** (Networking → VCN → Subnet → Security List), entrada:

| puerto | desde | para qué |
|---|---|---|
| 22 | tu IP | SSH |
| 80 | 0.0.0.0/0 | certbot y la redirección a HTTPS |
| 443 | 0.0.0.0/0 | la app |

**El 5432 nunca se abre.** Postgres escucha sólo en `localhost` y todo lo que lo
consulta vive en la misma máquina.

> **La trampa número uno de Ubuntu en OCI**: la imagen trae sus propias reglas de
> `iptables` además de la security list. Abrir el puerto en la consola de Oracle y
> que igual no ande es *el* síntoma. Hay que abrirlo en los dos lados:
>
> ```bash
> sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
> sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
> sudo netfilter-persistent save
> ```

Y la zona horaria, de la que depende que el timer dispare cuando decís:

```bash
sudo timedatectl set-timezone America/Argentina/Buenos_Aires
```

## 3. El gate: ¿los súper le contestan a esta IP?

**Puede cancelar el plan, y no cuesta nada verificarlo.** Coto (ATG) y VTEX (Día,
Carrefour) podrían bloquear rangos de datacenter o geo-bloquear fuera de
Argentina.

```bash
sudo apt install -y python3-pip
pip install --break-system-packages "httpx[http2]"
curl -sO https://raw.githubusercontent.com/aviollaz/SmartCart/main/ops/oracle/probe_endpoints.py
python3 probe_endpoints.py
```

Chequea **cuatro** superficies —el BFF de catálogo de Coto, el actor ATG
`getCobertura`, y los `productSearchV3` de Día y de Carrefour— y para cada una
exige **content-type JSON y la forma esperada**, no sólo un HTTP 200: el sitio de
Coto sirve su `index.html` con 200 para cualquier ruta desconocida, así que mirar
sólo el status es parsear una página web creyendo que son datos.

**Línea de base local (Argentina, 2026-08-28), las cuatro OK:**

| sonda | latencia |
|---|---|
| `coto-catalogo` | ~300 ms |
| `coto-cobertura` | ~50 ms |
| `dia-graphql` | ~230-515 ms |
| `carrefour-graphql` | ~230-570 ms |

Desde Santiago se esperan ~30 ms más. **Si alguna vuelve 403, captcha o HTML,
parar acá**: no hay arquitectura que arregle un bloqueo por IP.

## 4. Postgres

```bash
sudo apt install -y postgresql postgresql-16-pgvector
sudo -u postgres createuser --pwprompt smartuser
sudo -u postgres createdb -O smartuser smartcart
sudo -u postgres psql -d smartcart -c "CREATE EXTENSION IF NOT EXISTS vector;"

sudo cp /opt/smartcart/ops/oracle/postgresql-smartcart.conf /etc/postgresql/16/conf.d/
sudo systemctl restart postgresql
```

**`postgresql-smartcart.conf` hace dos cosas y la segunda no se ve venir.** Es el
tuning que le corresponde a Postgres en una máquina dedicada — y es lo que impide
que Oracle se lleve la instancia. Ver §7.

**No hay migración que correr**: `src/schema.py` es idempotente y lo aplican
`SmartCartDB`, `EmbeddingPipeline`, `ScraperTelemetry` y el `lifespan` de la API.
La base arranca vacía y el primer barrido la llena.

## 5. La aplicación

```bash
sudo useradd --system --home /opt/smartcart --shell /usr/sbin/nologin smartcart
sudo git clone https://github.com/aviollaz/SmartCart.git /opt/smartcart
cd /opt/smartcart
sudo python3 -m venv .venv
sudo .venv/bin/pip install -r requirements.txt

sudo cp .env.example .env      # completar DATABASE_URL, CORS_ORIGINS, SMARTCART_NTFY_URL
sudo chmod 600 .env
sudo chown -R smartcart:smartcart /opt/smartcart
```

Playwright **no** hace falta: sólo lo usan los scrapers de promociones bancarias
(`src/scrapers/get_bank_promos.py`), que son un runner aparte y no están en el
barrido nocturno.

> `EnvironmentFile` de systemd **no es un shell**: parsea `CLAVE=VALOR` literal.
> No pongas comillas alrededor de los valores (quedarían dentro del valor), y a
> cambio la contraseña puede tener los símbolos que quiera.

El frontend se compila una vez y lo sirve nginx:

```bash
cd /opt/smartcart/frontend
echo "VITE_API_URL=https://TU_DOMINIO/api" > .env
npm ci && npm run build
```

## 6. systemd

Cuatro unidades declarativas, **sin una sola condición entre las cuatro**:

| unidad | qué hace |
|---|---|
| `smartcart-api.service` | uvicorn en `127.0.0.1:8000`, `Restart=always` |
| `smartcart-scrape.service` | `oneshot`, corre el orquestador |
| `smartcart-scrape.timer` | `OnCalendar=03:00`, `Persistent=true` |
| `smartcart-alert@.service` | `OnFailure` de las otras: un `curl` a ntfy.sh |

```bash
sudo cp ops/oracle/smartcart-*.service ops/oracle/smartcart-*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now smartcart-api.service
sudo systemctl enable --now smartcart-scrape.timer   # el TIMER, no el service
```

**No hay ningún script wrapper, y es a propósito.** `WorkingDirectory`,
`EnvironmentFile`, `User` y la captura de salida son exactamente lo que el viejo
`ops/run_pipeline.sh` existía para darle a cron — systemd las da declarativamente.
El camino nocturno quedó con **cero líneas de bash**.

Dos directivas que reemplazan categorías enteras de problema: `Persistent=true`
corre el barrido al arrancar si la VM estuvo caída a las 03:00, y `OnCalendar`
usa la hora local, sin aritmética UTC ni el caveat de horario de verano que
arrastraba el cron de GitHub Actions.

**El aviso de fallo es lo único que se pierde al dejar GitHub Actions**, y es
justo el problema que motivó la migración. `OnFailure=` cubre los exit codes 1 y 2
sin código propio; el notificador es un `curl` a un topic de ntfy.sh — gratis, sin
cuenta, llega al teléfono. **Hay que probarlo a propósito** (paso 7 de la
verificación): un aviso que nunca se disparó no existe.

## 7. Que Oracle no se lleve la máquina

**El Always Free recupera instancias ociosas.** Si durante 7 días corridos el CPU
(percentil 95), la red y la memoria están **todos** por debajo del 20%, Oracle
reclama la instancia.

El barrido nocturno no salva a nadie: 30 minutos por noche son 3,5 horas sobre
168, ni mueven el percentil 95.

Pero las tres condiciones tienen que cumplirse **a la vez**, así que alcanza con
romper una permanentemente. Eso es lo que hace `shared_buffers = 4GB` sobre 12 GB
de RAM: deja la memoria en 33% para siempre. Y no es un truco — es el tamaño que
le corresponde a Postgres en una máquina dedicada (la recomendación habitual es
25-40% de la RAM), así que además hace la base más rápida. El uvicorn con el
modelo cargado (~1,5 GB) suma por encima.

**Descartado explícitamente**: el `while true` o el cron que quema CPU para
simular actividad. Gasta recursos de verdad, es un proceso más que puede morirse
en silencio, y no compra nada más. Acá la mitigación es un efecto lateral de una
configuración que había que hacer igual.

## 8. nginx y HTTPS

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
sudo cp ops/oracle/nginx-smartcart.conf /etc/nginx/sites-available/smartcart
sudo sed -i 's/TU_DOMINIO/tu-dominio-real/' /etc/nginx/sites-available/smartcart
sudo ln -s /etc/nginx/sites-available/smartcart /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d tu-dominio-real
```

certbot reescribe el archivo agregando el bloque TLS y la redirección desde el 80,
y deja su propio timer de renovación. Por eso el `.conf` del repo sólo tiene el
bloque 80: escribir el de 443 a mano sería duplicar lo que certbot ya hace.

**`CORS_ORIGINS` en el `.env` tiene que ser el dominio real.** El default son los
puertos del dev server de Vite. Antes esto era `allow_origins=["*"]` junto con
`allow_credentials=True`, que es inválido según la especificación de CORS: los
navegadores rechazan esa combinación. Mientras todo fue localhost no molestaba;
con la API pública, no.

## 9. Sin backups, y por qué

**La base es derivada.** `unified_products`, `store_products` y los embeddings los
reconstruye entero un barrido completo (~30 min) que además corre todas las
noches. El carrito y el historial de compras del usuario viven en el
`localStorage` del navegador, no en Postgres. Lo único no reconstruible es el
historial de `scraper_execution_logs`, que es telemetría de operación.

Así que no se construyen: ni timer de `pg_dump`, ni lógica de retención, ni
credenciales de Object Storage, ni el monitoreo de que todo eso ande. Es la mayor
porción de complejidad que este deploy evita, y se evita por un hecho establecido,
no por comodidad.

**Cuándo se invierte**: el día que se guarden carritos o cuentas de usuario en
Postgres, esta sección deja de valer y hay que escribir el backup.

## 10. La analítica queda apagada, a propósito

`ANALYTICS_URL` apunta a `localhost:8001`, donde vive el *SmartCart Performance
Analyzer* — que no se muda en este deploy. Sin `ANALYTICS_API_KEY` no se emite
ningún evento, que es el diseño (la analítica no puede tumbar `/optimize`).

El problema es que **un servidor mal configurado se ve idéntico a uno sano**. Por
eso se deja la variable vacía deliberadamente y se anota acá: `GET /` reporta en
qué estado quedó. Si algún día el analyzer también se muda, es cambiar esas dos
variables.

---

## Verificación

Los dos primeros son gates: si fallan, no se construye lo que sigue.

1. **Capacidad A1** (§1-2). Si sale *out of capacity*, parar y decidir.
2. **El probe** (§3): `python3 probe_endpoints.py`, las cuatro OK.
3. Postgres: `sudo -u postgres psql -d smartcart -c "SELECT version();"` y que
   `CREATE EXTENSION vector` haya quedado.
4. `sudo -u smartcart .venv/bin/python -m pytest tests/test_schema.py` — sólo
   re-emite el DDL idempotente y lee el catálogo, no toca datos.
5. **Barrido de una tienda a mano**, que es el más barato de diagnosticar:
   ```bash
   sudo -u smartcart .venv/bin/python -m src.scripts.orchestrator --store dia
   echo "rc=$?"
   ```
6. Barrido completo por systemd: `sudo systemctl start smartcart-scrape.service`,
   después `journalctl -u smartcart-scrape -f` y cuatro filas en `SUCCESS`:
   ```sql
   SELECT run_id, supermercado, status, items_scraped, duration_seconds
     FROM scraper_execution_logs ORDER BY id DESC LIMIT 12;
   ```
7. **El aviso de fallo, roto a propósito.** `sudo systemctl stop postgresql`,
   correr el barrido, y esperar el push en el teléfono. Después volver a
   levantar Postgres. Un notificador que nunca se probó no existe.
8. **El timer, a 10 minutos vista**, no esperando a las 3am: editar `OnCalendar`,
   `daemon-reload`, `systemctl list-timers` para ver el próximo disparo, y
   después devolverlo a las 03:00.
9. La API: `GET /` (reporta `db_pool` y el estado de la analítica),
   `GET /search?q=yerba`, y un `POST /optimize` desde el frontend ya en el dominio.
10. **A los 8 días: que la instancia siga viva.** Es la única forma de confirmar
    que lo de §7 funcionó, porque la ventana de evaluación de Oracle son 7 días.

## Lo que ahora es tuyo

Dejar un servicio administrado tiene un costo que no lo paga ninguna
arquitectura: lo paga el que la opera.

* **Parches**: `unattended-upgrades` cubre los de seguridad de Ubuntu; los de
  Postgres y los reinicios, no.
* **El certificado**: certbot renueva solo, pero si el timer se rompe el sitio
  queda inaccesible en 90 días.
* **El disco**: 50 GB alcanzan de sobra, pero los logs crecen. El orquestador poda
  los suyos (`SMARTCART_LOG_RETENTION_DAYS`); journald se limita con
  `SystemMaxUse` en `/etc/systemd/journald.conf`.
