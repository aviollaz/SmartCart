# SmartCart en AWS — el barrido nocturno

Runbook para mudar el pipeline de las 03:00 desde el cron de WSL a AWS.

**Por qué**: bajo WSL el job depende de que la máquina esté prendida a las 3am, y
Windows cierra la VM sola tras un rato sin uso. Eso no lo arregla ningún script
(está documentado en `ops/crontab.example`): es cómo funciona WSL.

**Qué se muda**: el pipeline y la base. La API (`uvicorn`) y el frontend siguen
corriendo en tu máquina, apuntando a la base remota — es una línea del `.env`.

## La arquitectura, en una línea

```
EventBridge Scheduler ──prende──► EC2 t4g.small ──corre──► ops/run_pipeline.sh
   (03:00 America/                     │                          │
    Argentina/Buenos_Aires)            │                          ▼
                                       │                    RDS PostgreSQL
                                       │                     (pgvector)
                                       └──se apaga sola──►  ~US$0,35/mes de cómputo
```

La instancia está **apagada 23 horas por día**. Ese es el truco entero: arrancar
*es* la señal de trabajo, así que no hace falta cron ni un `systemd.timer`
esperando despierto, que es precisamente el costo que se quiere evitar.

## Costo real, post-créditos (us-east-1)

| Recurso | Cálculo | US$/mes |
|---|---|---|
| RDS `db.t4g.micro` Single-AZ | US$0,016/h × 730 h | 11,68 |
| RDS storage 20 GB gp3 | 20 × US$0,115 | 2,30 |
| RDS backups | gratis hasta el tamaño de la base | 0 |
| EC2 `t4g.small` prendida ~0,7 h/día | 21 h × US$0,0168 | 0,35 |
| EBS 20 GB gp3 | 20 × US$0,08 | 1,60 |
| EventBridge Scheduler · Parameter Store · CloudWatch · SNS | dentro de siempre-gratis | 0 |
| **Total** | | **~16** |

**La base es el 90% de la factura.** Con US$200 de crédito eso da ~12 meses, que
es justo cuando el crédito vence. Después cuesta plata real: ver
[Salida](#salida-cómo-se-desarma) antes de que eso pase, no después.

---

## 0. Guardarraíles, antes de crear nada

> Desde el 15-jul-2025 las cuentas nuevas **no tienen** los 12 meses de free
> tier. Tienen US$100 de crédito (US$200 completando 5 tareas de onboarding) y un
> "Free Plan" que **vence a los 6 meses cerrando la cuenta**, con 90 días para
> recuperar los datos antes del borrado definitivo.
>
> **Para este proyecto eso es aceptable y por eso se elige el Free Plan.** La
> base es *derivada*: `unified_products`, `store_products` y los embeddings los
> reconstruye entero un barrido completo (~30 min), que además corre todas las
> noches. Perder la instancia cuesta media hora de cómputo, no información. Lo
> único no reconstruible es el historial de `scraper_execution_logs` — telemetría
> de operación, no datos de producto — y eso no justifica pagar por retenerlo.
> (El historial de compras del usuario tampoco corre riesgo: vive en el
> `localStorage` del navegador, no en Postgres.)

1. Crear la cuenta. MFA en el usuario root y **no volver a usarlo**; crear un
   administrador aparte en IAM Identity Center.
2. Completar las 5 tareas de onboarding para llevar el crédito a **US$200**. Dos
   de ellas (lanzar una EC2, configurar una RDS) son pasos de este runbook igual.
3. **AWS Budgets**: presupuesto mensual con alerta por mail a **US$1** y otra a
   **US$20**. La de US$1 es la que avisa que algo quedó prendido.
4. **Quedarse en el Free Plan.** Por la nota de arriba, el cierre a los 6 meses
   es un horizonte aceptado, no un riesgo a mitigar: cuando llegue, se decide
   entre [Salida](#salida-cómo-se-desarma) 2 o 3. La ventaja de no pasar a Paid
   Plan es que **el gasto no puede desbordar** — agotados los créditos la cuenta
   se cierra en vez de seguir facturando, que es la garantía más fuerte de $0
   que da AWS. Pasar a Paid Plan sólo si en algún momento hace falta que la
   cuenta sobreviva.

Región: **us-east-1**. sa-east-1 (São Paulo) está más cerca pero cuesta ~40% más
y para un job nocturno la latencia no decide nada.

---

## 1. El gate: ¿los súper le contestan a una IP de AWS?

**Este paso puede cancelar el plan entero y cuesta ~US$0,02.** Coto (ATG) y VTEX
(Día, Carrefour) podrían bloquear rangos de datacenter o geo-bloquear fuera de
Argentina. Hay que saberlo **antes** de crear una RDS.

```bash
# En tu máquina (línea de base):
python ops/aws/probe_endpoints.py --json > baseline_local.json

# En una EC2 t4g.micro recién lanzada, entrando por EC2 Instance Connect:
sudo dnf install -y python3-pip && python3 -m pip install httpx
curl -sO https://raw.githubusercontent.com/aviollaz/SmartCart/main/ops/aws/probe_endpoints.py
python3 probe_endpoints.py --json > baseline_aws.json
```

El probe no importa nada de `src/`, así que corre en una instancia pelada sin
clonar el repo. Chequea las cuatro superficies reales —el BFF de catálogo de
Coto, el actor `getCobertura`, y los `productSearchV3` de Día y Carrefour— y
para cada una exige **content-type JSON y la forma esperada**, no sólo un HTTP
200: el sitio de Coto es un SPA que sirve su `index.html` con 200 para cualquier
ruta desconocida, así que mirar sólo el status es parsear una página web
creyendo que son datos.

**Línea de base medida desde Argentina (2026-08-28), las cuatro OK:**

| sonda | latencia |
|---|---|
| `coto-catalogo` | ~300 ms |
| `coto-cobertura` | ~50 ms |
| `dia-graphql` | ~230-515 ms |
| `carrefour-graphql` | ~230-570 ms |

**Si desde AWS vuelve 403, captcha o HTML: parar acá.** El plan cambia (proxy
residencial = costo recurrente, o el pipeline se queda local). Mirar también los
milisegundos: el barrido son miles de requests secuenciales, así que +200 ms por
request se nota en la ventana de `PIPELINE_TIMEOUT`.

Terminar la instancia cuando termines.

---

## 2. Red y RDS

**No crear un NAT Gateway.** Son ~US$32/mes, más que todo el resto junto, y es la
trampa de costo clásica de esta arquitectura. Se usa la **VPC default**, que ya
trae subredes públicas e internet gateway, y la EC2 va en subred pública con IP
pública auto-asignada.

Dos security groups, y el de la base referencia al otro **por id de SG, no por
CIDR** (una IP de casa cambia; una referencia de SG no):

| SG | inbound |
|---|---|
| `sg-smartcart-scraper` | ninguno — se entra por SSM Session Manager, no por el 22 |
| `sg-smartcart-db` | 5432 sólo desde `sg-smartcart-scraper` |

**RDS**: PostgreSQL 16 o 17 · `db.t4g.micro` · Single-AZ · 20 GB gp3 · backups
7 días · **Public access = No** · encryption on.

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

> **La contraseña tiene que ser alfanumérica.** No es manía: `ops/run_pipeline.sh`
> hace `source` del `.env`, así que un `$`, un backtick, un `&` o un `!` los
> interpreta el shell y psycopg recibe una cadena distinta de la que dice el
> archivo. Los generadores de claves de AWS ponen esos símbolos por default.
> Está documentado en `.env.example`.

**No hay migración que correr.** `src/schema.py` es idempotente y declarativo, y
lo aplican `SmartCartDB`, `EmbeddingPipeline`, `ScraperTelemetry` y el `lifespan`
de la API. La base arranca vacía y se llena con el primer barrido.

---

## 3. Llegar a la base desde tu máquina

La base es privada, así que la API local entra por un túnel de SSM en vez de
abrir RDS a internet:

```bash
aws ssm start-session --target i-xxxxxxxx \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters '{"host":["<endpoint>.rds.amazonaws.com"],"portNumber":["5432"],"localPortNumber":["5432"]}'
```

Con el túnel arriba, el único cambio en el proyecto es una línea del `.env`:

```
DATABASE_URL=postgresql://usuario:clave@localhost:5432/smartcart?sslmode=require
```

`?sslmode=require` es explícito a propósito: el default (`prefer`) acepta texto
plano si el servidor lo ofrece — pide, no exige.

El túnel necesita la EC2 prendida, y en esta arquitectura está apagada casi
siempre. Para trabajar: `aws ec2 start-instances --instance-ids i-xxxx`, y
**antes poner el freno de mano** (paso 4) o el arranque te dispara un barrido y
después te apaga la sesión en la cara.

---

## 4. La instancia

**`t4g.small`, no `t4g.micro`**: 1 GB de RAM no aguanta torch + `all-MiniLM-L6-v2`.
Con 2 GB más un swapfile de 2 GB entra cómodo. Amazon Linux 2023 arm64, 20 GB gp3.

**Instance profile** (rol IAM de la instancia):
- `AmazonSSMManagedInstanceCore` — Session Manager y el túnel.
- lectura de `/smartcart/prod/*` en Parameter Store.
- escritura a CloudWatch Logs.

**Provisionar** (una vez):

```bash
sudo dnf install -y git python3.11 python3.11-pip postgresql16
sudo git clone <repo> /opt/smartcart && cd /opt/smartcart
sudo python3.11 -m venv .venv-linux
sudo .venv-linux/bin/pip install -r requirements.txt
sudo cp .env.example .env && sudo chmod 600 .env   # completar y ajustar
sudo dd if=/dev/zero of=/swapfile bs=1M count=2048 && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

Playwright **no** hace falta: sólo lo usan los scrapers de promos bancarias
(`src/scrapers/get_bank_promos.py`), que son un runner aparte y no están en el
pipeline nocturno.

En el `.env`: `SMARTCART_AUTOSTART_DB=0` (ya no hay contenedor local que
levantar) y `SMARTCART_VENV=/opt/smartcart/.venv-linux`.

**El secreto** va a SSM Parameter Store como `SecureString` (Standard es gratis;
Secrets Manager cuesta US$0,40/mes por secreto y acá no compra nada):

```bash
aws ssm put-parameter --name /smartcart/prod/database_url --type SecureString \
  --value 'postgresql://usuario:clave@<endpoint>:5432/smartcart?sslmode=require'
```

**La unidad de systemd**:

```bash
sudo cp ops/aws/smartcart-pipeline.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable smartcart-pipeline.service    # enable, NO start
```

`enable` sin `start`: lo que se quiere es que corra en el **próximo** arranque.
Un `start` acá lo dispara ahora y al terminar apaga la instancia que estás usando
para instalarlo.

### El freno de mano

La instancia también se prende a mano (túnel, provisionar, depurar). Sin freno,
prenderla para eso dispara un barrido completo y después te apaga la sesión:

```bash
sudo mkdir -p /etc/smartcart && sudo touch /etc/smartcart/hold   # modo manual
sudo rm /etc/smartcart/hold                                      # modo automático
```

Va en `/etc` y no en `/run` a propósito: `/run` se vacía en cada arranque, o sea
que no podría frenar el arranque que querés frenar.

---

## 5. El schedule

**EventBridge Scheduler** (no una regla vieja de EventBridge: Scheduler soporta
zona horaria, las reglas son sólo UTC — y con horario de verano eso se corre una
hora sin avisar).

- Expresión: `cron(0 3 * * ? *)`
- `ScheduleExpressionTimezone`: `America/Argentina/Buenos_Aires`
- Target universal: `ec2:StartInstances`, con un rol que sólo pueda arrancar
  **esa** instancia.

El `flock` de `ops/crontab.example` deja de hacer falta: la instancia apagada es
el lock. Si el barrido de ayer sigue vivo, la máquina está prendida y el
`StartInstances` es un no-op.

---

## 6. Que alguien se entere cuando falla

Los códigos de salida ya son el contrato de monitoreo:

| rc | significa |
|---|---|
| 0 | todos los pasos SUCCESS |
| 1 | algún paso PARTIAL/FAILED |
| 2 | fallo de arranque, no corrió ningún scraper |
| 124 | el watchdog cortó por `PIPELINE_TIMEOUT` |
| 143 | SIGTERM |

- **CloudWatch Agent** subiendo `logs/orchestrator_*.log` y `logs/pipeline_*.log`,
  retención 7 días. `boot_and_scrape.sh` espera `SMARTCART_DRAIN_SECONDS` (45 por
  default) antes de apagar para que el agente llegue a subir: si no, la corrida
  que más importa mirar —la que falló— es justo la que puede no quedar registrada.
- **Metric filter** sobre `FATAL|DEGRADADO|TIMEOUT` → alarma → **SNS** a tu mail.
- **Y la que más sirve: una alarma por AUSENCIA de logs.** Si el schedule no
  dispara no hay error, hay silencio — indistinguible de "nunca corrió". Es el
  mismo argumento por el que `ScraperTelemetry` abre su fila *antes* del trabajo
  y no después.

---

## Verificación

En orden, cada paso antes del siguiente:

1. **El gate del paso 1.** Si falla, no se construye nada más.
2. `psql "$DATABASE_URL" -c "SELECT version();"` por el túnel.
3. Con el `.env` local apuntando al RDS: `pytest tests/test_schema.py` — sólo
   re-emite el DDL idempotente y lee el catálogo de Postgres, no toca datos.
4. Primer barrido **a mano en la EC2**, una sola tienda:
   `python -m src.scripts.orchestrator --store dia`. Mirar el `rc` y la fila en
   `scraper_execution_logs`.
5. Barrido completo a mano: `./ops/run_pipeline.sh`. Esperar `rc=0` y cuatro
   filas en `SUCCESS` (coto/dia/carrefour/embeddings).
6. `uvicorn src.api:app` **local** contra el RDS: `GET /` (reporta `db_pool` y
   analítica), `GET /search?q=yerba`, y un `POST /optimize` desde el frontend.
   Acá se ve si el pool aguanta la latencia nueva.
7. **El schedule, con un cron a 5 minutos vista, no esperando a las 3am.**
   Confirmar los tres eslabones: arrancó, corrió, se apagó sola.
8. Al día siguiente: el mail de la alarma (o su ausencia), los logs, y

   ```sql
   SELECT run_id, supermercado, status, items_scraped, duration_seconds, start_time
     FROM scraper_execution_logs ORDER BY id DESC LIMIT 12;
   ```

9. **Al tercer día, Cost Explorer.** Es la única forma de saber si algo quedó
   prendido.

---

## Salida: cómo se desarma

Escrito de antemano, porque el crédito vence a los 12 meses y ese es el momento
de decidir, no de averiguar.

1. **Bajar el costo sin mudarse** — poco margen: la base es el 90% de la factura
   y RDS sólo se puede *detener* 7 días seguidos, después arranca sola. No sirve
   para apagarla a diario.
2. **Migrar a US$0/mes** — `pg_dump` → Neon (free tier permanente, pgvector,
   0,5 GB alcanza de sobra para ~6.400 productos) y el job a GitHub Actions
   (`schedule:` en el workflow; gratis e ilimitado en repos públicos). Cambia una
   línea de `DATABASE_URL`.
3. **Desarmar del todo** — `pg_dump` local, borrar la RDS con snapshot final,
   terminar la EC2, borrar el schedule, volver `DATABASE_URL` a `localhost`. El
   repo queda exactamente como está hoy: nada de esto tocó `src/`.
