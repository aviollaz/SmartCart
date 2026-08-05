"""
Carga de los descuentos bancarios que consume el optimizador.

Traduce el artefacto que genera `python -m src.scrapers.get_bank_promos` a la
forma exacta que espera `optimize_cart`: {store_id: [{card, discount_pct, cap,
description}]}.

Dos responsabilidades que no son obvias y que justifican que esto sea un módulo
y no una lectura de archivo en línea:

**Filtra por día.** El modelo CP-SAT no tiene noción de día de la semana: aplica
un porcentaje con tope y listo. Los descuentos reales, en cambio, son casi todos
de un día puntual ("todos los martes"). Si se cargaran todos, un usuario que
arma el carrito un martes vería el ahorro del jueves y elegiría una tienda por
una razón falsa. Filtrar acá deja el solver como está y hace que la pregunta
"¿qué descuentos hay?" se responda una sola vez por request.

Esto es, además, lo que destraba Carrefour. Estaba deliberadamente afuera de la
tabla hardcodeada porque sus descuentos son de fin de semana y el modelo no podía
expresarlo; con el filtro por día deja de ser un caso especial.

**Ordena por conveniencia.** `optimize_cart` elige con
`next(p for p in promos if p["card"] in user_cards)`: el PRIMERO que matchea, no
el mejor. Con dos entradas escritas a mano nunca se notó, pero los datos reales
traen tres promos de Naranja X en Coto (30%, 25% y 20%) y varias de Banco
Patagonia en Carrefour. Ordenar acá corrige la elección sin tocar el solver.
"""
import json
import logging
import os
from datetime import date

from src.promotions.banks import MEMBERSHIP_ENTITIES
from src.promotions.models import CANONICAL_DAYS

logger = logging.getLogger(__name__)

BANK_PROMOS_PATH = os.path.join(os.path.dirname(__file__), "scrapers", "bank_promos.json")

# Tope que se usa cuando la promo no tiene ninguno. No puede ser 0 (anularía el
# descuento) ni None (el modelo lo multiplica por 100 y lo compara). Es un número
# alto pero finito, del mismo orden que MAX_SUBTOTAL_CENTS en src/optimizer.py.
SIN_TOPE_CAP = 100_000_000

# La tabla que estuvo hardcodeada en optimize_cart hasta que existió el scraper.
# Sigue siendo el fallback: sin el artefacto —repo recién clonado, corrida que
# nunca se hizo, archivo corrupto— la app tiene que seguir funcionando igual que
# antes, no quedarse sin ningún descuento.
FALLBACK_BANK_PROMOS = {
    "coto_online": [
        {"card": "galicia", "discount_pct": 20, "cap": 5000,
         "description": "20% de ahorro con Galicia (Tope $5000)"},
    ],
    "dia_online": [
        {"card": "macro", "discount_pct": 15, "cap": 3000,
         "description": "15% de ahorro con Macro (Tope $3000)"},
    ],
}


def load_bank_promos(today: date | None = None, path: str = BANK_PROMOS_PATH) -> dict:
    """
    Devuelve {store_id: [promo]} con los descuentos vigentes hoy.

    `today` se inyecta en los tests; en producción es la fecha del sistema.

    Ante cualquier problema con el archivo devuelve FALLBACK_BANK_PROMOS. Es
    fail-open a propósito, como src/coto_logistics.py: que el artefacto falte no
    puede dejar al optimizador sin descuentos, porque el usuario no vería un
    error sino precios peores sin explicación.
    """
    documento = _read(path)
    if documento is None:
        return {k: list(v) for k, v in FALLBACK_BANK_PROMOS.items()}

    dia_de_hoy = CANONICAL_DAYS[(today or date.today()).weekday()]
    promos: dict[str, list[dict]] = {}
    vigentes = 0

    for store_id, registros in (documento.get("promos") or {}).items():
        del_dia = [r for r in registros if dia_de_hoy in (r.get("dias_validos") or ())]
        if not del_dia:
            continue

        # De mayor a menor descuento: optimize_cart se queda con el primero que
        # matchee la tarjeta del usuario, así que el orden ES la selección.
        #
        # El tope desempata, porque los empates son reales: Coto publica el mismo
        # 30% para ICBC (tope $20.000) y para Credicoop (tope $15.000). A igual
        # porcentaje, el de tope más alto nunca ahorra menos.
        del_dia.sort(
            key=lambda r: (r.get("porcentaje_descuento") or 0,
                           r.get("tope_reintegro") or SIN_TOPE_CAP),
            reverse=True,
        )
        promos[store_id] = [_to_optimizer_promo(r) for r in del_dia]
        vigentes += len(del_dia)

    if not promos:
        # Un archivo válido puede quedarse sin nada un día flojo. No es un error
        # —es la respuesta correcta— y devolver el fallback acá inventaría un
        # descuento de Galicia que hoy no está vigente.
        logger.info("bank_promos: no hay descuentos vigentes para %s", dia_de_hoy)
        return {}

    logger.debug("bank_promos: %d descuentos vigentes el %s", vigentes, dia_de_hoy)
    return promos


def _read(path: str) -> dict | None:
    try:
        with open(path, encoding="utf-8") as archivo:
            documento = json.load(archivo)
    except FileNotFoundError:
        logger.info("bank_promos: no existe %s; se usa la tabla por defecto", path)
        return None
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("bank_promos: no se pudo leer %s (%s); se usa la tabla por defecto",
                       path, exc)
        return None

    if not isinstance(documento, dict) or not isinstance(documento.get("promos"), dict):
        logger.warning("bank_promos: %s no tiene la forma esperada; se usa la tabla por defecto",
                       path)
        return None

    return documento


def _to_optimizer_promo(registro: dict) -> dict:
    """Traduce un BankDiscount serializado al dict que consume optimize_cart."""
    tope = registro.get("tope_reintegro")
    return {
        "card": registro["entidad"],
        # Entero obligatorio: optimize_cart lo usa como coeficiente de una
        # restricción CP-SAT (`subtotal * discount_pct`), y ortools no acepta
        # coeficientes float. Se redondea; hoy todos los porcentajes relevados
        # son enteros, así que no se pierde nada.
        "discount_pct": int(round(registro["porcentaje_descuento"])),
        "cap": SIN_TOPE_CAP if tope is None else tope,
        "description": registro.get("descripcion") or "",
        # El optimizador compara `card` contra user_cards. Las entidades que en
        # realidad son programas de fidelidad se declaran en el otro eje del
        # perfil (user_memberships), y sin esta marca no habría forma de saber
        # contra cuál comparar.
        "is_membership": registro["entidad"] in MEMBERSHIP_ENTITIES,
    }
