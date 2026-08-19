# src/substitutions.py
"""
Reemplazos comparables: la única definición de "este otro producto es lo mismo
en otra presentación".

El proyecto tiene dos features que necesitan esa noción y que antes la resolvían
cada una por su cuenta:

1. `src/strategic_swaps.py` — sustituye los productos exclusivos de una tienda
   para poder cerrarla entera.
2. Las `suggestions` de `POST /optimize` (`build_semantic_suggestions()`, acá
   abajo) — le ofrece al usuario una alternativa más barata a igual cantidad.

Tenerlo escrito dos veces no era un problema estético: las dos copias
divergieron, y la de api.py se quedó sin la banda de tamaño y sin la guarda de
formato de pack. Prorratear el precio por el peso sin esa guarda es exactamente
el modo de falla que documenta `size_parser.extract_pack_count()` — un
"Alfajor MILKA Simple Mousse 42g Display X 6 Un." guarda 42 g (el tamaño de CADA
unidad) mientras su precio es el de las seis, así que prorrateado parece un 83%
más barato que el alfajor suelto que es. Sobre el catálogo real eso emitía 36
sugerencias de ese tipo, todas invitando al usuario a llevarse menos producto
creyendo que ahorraba.

La regla general del proyecto (la misma de los flags dietarios y del pack count):
errar hacia caro sólo pierde un ahorro, errar hacia barato rompe la promesa sobre
la que está construida la app.

Este módulo no importa a ninguno de sus dos consumidores, así que no hay ciclo:
substitutions -> {category_tags, flattener, size_parser}, y tanto
strategic_swaps como api importan de acá. Es el mismo movimiento que ya se hizo
con `same_aisle_filter`, que vive en category_tags.py por esta razón exacta.
"""
import logging

from src.category_tags import same_aisle_filter
from src.flattener import flatten_cart_prices
from src.size_parser import extract_pack_count

logger = logging.getLogger(__name__)

# Banda de tamaño aceptable para un reemplazo, relativa al original. Sin esto la
# comparación "ahorra" achicando el producto: 500 ml siempre sale menos que 1 L y
# no es el mismo mandado. También es lo que acota el prorrateo por peso de
# `build_semantic_suggestions` a una extrapolación de a lo sumo 2x.
MIN_WEIGHT_RATIO = 0.5
MAX_WEIGHT_RATIO = 2.0

# Fallback de src/size_parser.py cuando no pudo parsear el tamaño del nombre.
# No significa "pesa 1", significa "no sé cuánto pesa".
UNKNOWN_UNIT = "un"
UNKNOWN_WEIGHT = 1.0

# Cuántos vecinos semánticos se traen por producto antes de filtrar. Los filtros
# de comparabilidad descartan bastante, así que pedir exactamente los que se van
# a mostrar deja huecos por candidatos que igual no íbamos a usar.
CANDIDATES_PER_ANCHOR = 5

# Umbral para ofrecerle una alternativa al usuario, relativo al precio del
# original. Por debajo de esto la diferencia se la come el ruido de tamaños y
# promos, y una lista larga de ahorros triviales le resta credibilidad a los que
# valen la pena.
MIN_PROPORTIONAL_SAVINGS_PCT = 0.20

# Tope de alternativas por producto del carrito.
MAX_ALTERNATIVES_PER_PRODUCT = 3


# ---------------------------------------------------------------------------
# Comparabilidad
# ---------------------------------------------------------------------------

def weight_of(row: dict) -> tuple[float, str]:
    """Peso y unidad de una fila de unified_products, con el fallback del parser."""
    raw_weight = row.get("total_volume_weight")
    weight = float(raw_weight) if raw_weight else UNKNOWN_WEIGHT
    return weight, (row.get("unit_type") or UNKNOWN_UNIT)


def is_comparable(orig: tuple[float, str], cand: tuple[float, str]) -> bool:
    """
    ¿Son dos presentaciones del mismo tipo de producto, en tamaños intercambiables?

    Gatea por comparabilidad, no por precio. Quien llame decide después qué hacer
    con el precio: `strategic_swaps` cotiza el real porque simula un carrito que
    el usuario va a pagar, y `build_semantic_suggestions` prorratea porque su
    número es explícitamente "a igual cantidad". La banda de acá es lo que hace
    que ese prorrateo signifique algo.
    """
    orig_weight, orig_unit = orig
    cand_weight, cand_unit = cand

    # g y ml son intercambiables: el parser normaliza kg->g y l->ml, y un yogur
    # puede venir declarado en cualquiera de las dos según la tienda.
    units_ok = orig_unit == cand_unit or (orig_unit in ("g", "ml") and cand_unit in ("g", "ml"))
    if not units_ok:
        return False

    # Si alguno de los dos no tiene tamaño parseado, su peso es un 1.0 sintético.
    # Compararlo contra un peso real da una proporción inventada, así que en ese
    # caso sólo se exige que ambos sean "por unidad" y se saltea el ratio: dos
    # productos vendidos por unidad ya son comparables sin saber cuánto pesan.
    if orig_unit == UNKNOWN_UNIT or cand_unit == UNKNOWN_UNIT:
        return orig_unit == UNKNOWN_UNIT and cand_unit == UNKNOWN_UNIT

    if orig_weight <= 0:
        return False

    return MIN_WEIGHT_RATIO <= (cand_weight / orig_weight) <= MAX_WEIGHT_RATIO


def same_pack_format(original_name: str, candidate_name: str) -> bool:
    """
    ¿Los dos productos vienen en la misma cantidad de unidades por pack?

    Un pack de 6 y una unidad suelta no son el mismo producto por más que el
    gramaje del nombre entre en la banda: el tamaño que guarda la base es el que
    figura en el nombre, y en los packs ese número tanto puede ser el total como
    el de cada unidad (ver `size_parser.extract_pack_count`, que explica por qué
    no se puede desambiguar). Exigir el mismo formato es lo que evita ofrecer un
    alfajor a cambio de una caja de seis.
    """
    return extract_pack_count(original_name) == extract_pack_count(candidate_name)


def format_size(weight: float, unit: str) -> str:
    """Tamaño legible para la UI: 1000 g -> '1 Kg', 1500 ml -> '1.5 L'."""
    if unit == UNKNOWN_UNIT:
        return "1 unidad"

    display_weight, display_unit = weight, unit
    if unit == "g" and weight >= 1000:
        display_weight, display_unit = weight / 1000, "Kg"
    elif unit == "ml" and weight >= 1000:
        display_weight, display_unit = weight / 1000, "L"

    rendered = f"{display_weight:g}"
    return f"{rendered} {display_unit}"


# ---------------------------------------------------------------------------
# Acceso a datos
# ---------------------------------------------------------------------------

def fetch_product_rows(cur, uids) -> dict:
    """Nombre, tamaño y datos de góndola de cada producto, en una sola query."""
    uids = list(uids)
    if not uids:
        return {}

    cur.execute(
        """
        SELECT id, name, category, tags, total_volume_weight, unit_type, name_embedding
        FROM unified_products
        WHERE id = ANY(%s)
        """,
        (uids,),
    )
    return {row["id"]: row for row in cur.fetchall()}


def fetch_candidates(cur, anchor_row, target_stores, limit: int = CANDIDATES_PER_ANCHOR):
    """
    Vecinos semánticos del producto que estén en stock en alguna de `target_stores`.

    Lee el `name_embedding` ya guardado y lo manda como parámetro: no toca el
    SentenceTransformer, así que esto no carga ni usa el modelo.

    El filtro por stock no es cosmético. `get_market_prices_for_cart` filtra
    `in_stock = TRUE`, así que un candidato sin stock se cae solo más adelante —
    pero recién después de haber ocupado un lugar del LIMIT, dejando al usuario
    con menos alternativas de las que había para darle.

    El DISTINCT ON evita que un producto vendido por dos tiendas ocupe dos
    lugares por el mismo motivo.
    """
    aisle_clause, aisle_param = same_aisle_filter(anchor_row, alias="u")

    cur.execute(
        f"""
        SELECT * FROM (
            SELECT DISTINCT ON (u.id)
                   u.id, u.name, u.total_volume_weight, u.unit_type,
                   u.name_embedding <=> %s AS distance
            FROM unified_products u
            JOIN store_products sp ON u.id = sp.unified_product_id
            WHERE sp.store_id = ANY(%s)
              AND sp.in_stock = TRUE
              AND u.name_embedding IS NOT NULL
              AND u.id != %s
              {aisle_clause}
            ORDER BY u.id, distance ASC
        ) AS vecinos
        ORDER BY distance ASC
        LIMIT %s
        """,
        (
            anchor_row["name_embedding"],
            list(target_stores),
            anchor_row["id"],
            aisle_param,
            limit,
        ),
    )
    return cur.fetchall()


def comparable_candidates(cur, anchor_row, target_stores, *, exclude_uids=(),
                          limit: int = CANDIDATES_PER_ANCHOR) -> list:
    """
    Los vecinos de `anchor_row` que además son sustituciones honestas: misma
    góndola (vía la query), mismo formato de pack, unidad compatible y tamaño
    dentro de la banda.

    Devuelve dicts `{uid, name, weight, unit}`.
    """
    anchor_size = weight_of(anchor_row)
    excluded = set(exclude_uids)
    viables = []

    for cand in fetch_candidates(cur, anchor_row, target_stores, limit=limit):
        if cand["id"] in excluded:
            continue
        if not same_pack_format(anchor_row["name"], cand["name"]):
            continue
        cand_size = weight_of(cand)
        if not is_comparable(anchor_size, cand_size):
            continue
        viables.append({
            "uid": cand["id"],
            "name": cand["name"],
            "weight": cand_size[0],
            "unit": cand_size[1],
        })

    return viables


# ---------------------------------------------------------------------------
# Sugerencias de ahorro proporcional (las que devuelve POST /optimize)
# ---------------------------------------------------------------------------

def build_semantic_suggestions(cur, cart_items, *, target_stores, user_memberships=None,
                               flatten=flatten_cart_prices) -> list:
    """
    Alternativas más baratas "a igual cantidad" para los productos del carrito.

    A diferencia de `strategic_swaps`, acá el precio SÍ se prorratea por peso: el
    número que se muestra es explícitamente una comparación por unidad de medida
    ("a igual cantidad de 900 ML"), no el costo de un carrito que el usuario vaya
    a pagar. Eso es honesto sólo porque el candidato ya pasó por
    `comparable_candidates()`: mismo formato de pack y tamaño dentro de la banda
    0,5x–2x, así que la extrapolación está acotada y el peso significa lo mismo
    en los dos lados. Sin esas dos guardas el prorrateo es el bug que este módulo
    existe para cerrar (ver el docstring de arriba).

    `flatten` se inyecta para poder testear sin base; `target_stores` acota los
    candidatos a las tiendas que efectivamente pueden entregar.

    :return: lista de grupos {original_uid, original_product, alternatives[]},
             ordenada por el mejor ahorro de cada grupo, descendente.
    """
    if not cart_items:
        return []

    quantities = {item["unified_id"]: item["quantity"] for item in cart_items}
    cart_uids = set(quantities)

    anchor_rows = fetch_product_rows(cur, cart_uids)

    # Un candidato ya presente en el carrito no es una alternativa: cambiarlo por
    # él fusiona dos líneas y el ahorro que se le muestra al usuario no
    # corresponde a ningún carrito real. Mismo motivo por el que lo descarta
    # strategic_swaps.
    candidates_by_uid = {}
    for uid, row in anchor_rows.items():
        if not row.get("name_embedding"):
            continue
        viables = comparable_candidates(cur, row, target_stores, exclude_uids=cart_uids)
        if viables:
            candidates_by_uid[uid] = viables

    if not candidates_by_uid:
        return []

    # Una sola llamada al aplanador para el carrito entero más todos los
    # candidatos. Cada candidato se cotiza a la cantidad del producto que
    # reemplaza, porque las promos condicionales (3x2, 2da al 50%) recién se
    # activan por encima de su umbral.
    to_flatten = list(cart_items)
    for uid, viables in candidates_by_uid.items():
        for cand in viables:
            to_flatten.append({"unified_id": cand["uid"], "quantity": quantities[uid]})

    flat_prices = flatten(to_flatten, user_memberships or [])

    groups = {}
    for uid, viables in candidates_by_uid.items():
        if uid not in flat_prices:
            continue

        anchor_weight, anchor_unit = weight_of(anchor_rows[uid])
        anchor_cost = min(offer["total_cost"] for offer in flat_prices[uid].values())
        metric_info = f"a igual cantidad de {format_size(anchor_weight, anchor_unit)}"

        alternatives = []
        for cand in viables:
            offers = flat_prices.get(cand["uid"])
            if not offers or cand["weight"] <= 0:
                continue

            cand_cost = min(offer["total_cost"] for offer in offers.values())
            proportional_cost = (cand_cost / cand["weight"]) * anchor_weight
            savings = anchor_cost - proportional_cost

            if savings <= anchor_cost * MIN_PROPORTIONAL_SAVINGS_PCT:
                continue

            alternatives.append({
                "suggested_uid": cand["uid"],
                "suggested_product": cand["name"],
                "savings": round(savings, 2),
                "effective_unit_price": min(o["effective_unit_price"] for o in offers.values()),
                "metric_info": metric_info,
            })

        if not alternatives:
            continue

        alternatives.sort(key=lambda a: a["savings"], reverse=True)
        groups[uid] = {
            "original_uid": uid,
            "original_product": anchor_rows[uid]["name"],
            "alternatives": alternatives[:MAX_ALTERNATIVES_PER_PRODUCT],
        }

    # El orden entre grupos sale del mejor ahorro de cada uno. Antes salía de una
    # lista plana ordenada globalmente, lo que hacía que el orden de los grupos
    # dependiera de cuál alternativa suelta había quedado primera.
    return sorted(
        groups.values(),
        key=lambda g: g["alternatives"][0]["savings"],
        reverse=True,
    )
