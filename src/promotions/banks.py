"""
Normalización de la entidad que otorga el descuento a un slug canónico.

Sin esta capa el módulo no sirve para nada: Coto identifica al banco con el nombre
del archivo del logo ("logo_galicia.png"), Día lo escribe en prosa dentro del texto
legal ("Banco Galicia"), y el perfil del usuario guarda "galicia". Si las tres
fuentes no colapsan al mismo slug, el descuento se scrapea correctamente y después
no matchea nunca contra las tarjetas declaradas.

BANK_ALIASES es DATA, no lógica — igual que PARTIDO_ZONES en el frontend. Sumar un
banco es una línea, y esa es toda la mantención que este archivo debería necesitar.

Los slugs canónicos tienen que coincidir con los que ofrece el frontend en
frontend/src/components/profile/ProfileDrawer.jsx (CARD_OPTIONS y
MEMBERSHIP_OPTIONS). Un slug que no esté ahí es un descuento que ningún usuario
puede llegar a seleccionar.
"""
import re

from src.text_utils import normalize_label

# alias normalizado -> slug canónico.
#
# Se matchea por substring sobre el texto normalizado, así que los alias más
# específicos tienen que poder ganarle a los más genéricos: el orden de este dict
# es el orden de evaluación (ver _ALIASES_POR_LONGITUD abajo, que lo resuelve por
# longitud descendente para no depender del orden de escritura).
BANK_ALIASES = {
    # Bancos
    "galicia": "galicia",
    "macro": "macro",
    "bbva": "bbva",
    "frances": "bbva",
    "nacion": "nacion",
    "bna": "nacion",
    "icbc": "icbc",
    "santander": "santander",
    "ciudad": "ciudad",
    "comafi": "comafi",
    "credicoop": "credicoop",
    "patagonia": "patagonia",
    "supervielle": "supervielle",
    "columbia": "columbia",
    "hipotecario": "hipotecario",
    "provincia": "provincia",
    "bapro": "provincia",
    "hsbc": "hsbc",
    "itau": "itau",
    # Tarjetas / billeteras
    "naranja x": "naranja_x",
    "naranjax": "naranja_x",
    "naranja": "naranja_x",
    "american express": "amex",
    "amex": "amex",
    "mercado pago": "mercado_pago",
    "mercadopago": "mercado_pago",
    "modo": "modo",
    "uala": "uala",
    "cabal": "cabal",
    "prex": "prex",
    "personal pay": "personal_pay",
    "banco del sol": "banco_del_sol",
    "del sol": "banco_del_sol",
    "club la nacion": "club_la_nacion",
    "club lanacion": "club_la_nacion",
    "lanacion": "club_la_nacion",
    # Programas propios de las cadenas. No son bancos, pero comparten el mecanismo
    # (un porcentaje con tope) y el usuario los declara igual, sólo que en el eje
    # de membresías en vez del de tarjetas. Ver MEMBERSHIP_ENTITIES abajo.
    "comunidad coto": "comunidad_coto",
    "comunidad": "comunidad_coto",
    "tci": "coto_tci",
    "club dia": "club_dia",
    "mi carrefour": "mi_carrefour",
    "mi crf": "mi_carrefour",
    "tarjeta carrefour": "mi_carrefour",
    # Carrefour Banco (Banco de Servicios Financieros) es una entidad distinta de
    # Mi Carrefour, que es el programa de fidelidad. Comparten la palabra
    # "carrefour", y por eso estos alias son más largos: _ALIASES_POR_LONGITUD los
    # evalúa antes que "tarjeta carrefour" y no se pisan.
    "carrefour banco": "carrefour_banco",
    "cuenta digital": "carrefour_banco",
    "carrefour credito": "carrefour_banco",
}

# Entidades que el perfil declara como membresía (`user_memberships`) y no como
# tarjeta bancaria (`user_cards`). El loader necesita saber contra qué eje comparar;
# sin esta distinción, "Comunidad Coto 15%" se buscaría entre las tarjetas y no se
# aplicaría nunca, aunque el usuario tenga la membresía tildada.
MEMBERSHIP_ENTITIES = frozenset({
    "comunidad_coto", "coto_tci", "club_dia", "mi_carrefour", "club_la_nacion",
})

# Alias ordenados por longitud descendente: "naranja x" tiene que evaluarse antes
# que "naranja", y "comunidad coto" antes que "comunidad". Resolverlo acá hace que
# el orden en que se escribe BANK_ALIASES no cambie el resultado.
_ALIASES_POR_LONGITUD = sorted(BANK_ALIASES.items(), key=lambda kv: len(kv[0]), reverse=True)

# Frases que contienen el nombre de un banco sin referirse a él. Se borran antes
# de matchear. Las dos que están son casos reales del relevamiento de Día, y las
# dos producían una promo atribuida al banco equivocado:
#
#   "CIUDAD AUTÓNOMA DE BUENOS AIRES"  -> el domicilio legal del anunciante, que
#       le asignaba a Banco del Sol una promo de Banco Ciudad.
#   "DE ALCANCE NACIONAL"              -> ver _limite_palabra: además lo tapa el
#       borde de palabra, pero el domicilio no, porque "ciudad" ahí sí es palabra.
_FRASES_RUIDO = (
    "ciudad autonoma de buenos aires",
    "ciudad autonoma",
)

# El borde bloquea LETRAS pero permite DÍGITOS a los costados, y esa asimetría es
# deliberada:
#
# - Bloquear letras es lo que evita los falsos positivos reales del relevamiento:
#   "ALCANCE NACIONAL" activaba "nacion" y le daba a Personal Pay una promo de
#   Banco Nación.
# - Permitir dígitos es obligatorio porque la fuente más confiable es el nombre
#   del archivo del logo, y Coto le pega un número de versión: "logo_ciudad1.png",
#   "logo_naranjax2.png", "bbva2.png", "logo_amex1.png". Con un \b clásico ninguno
#   de esos matchearía y nos quedaríamos sin la mejor fuente que tenemos.
_ALIAS_RES = {
    alias: re.compile(r"(?<![a-z])" + re.escape(alias) + r"(?![a-z])")
    for alias in BANK_ALIASES
}


def normalize_entity(*fuentes: str | None) -> str | None:
    """
    Devuelve el slug canónico de la entidad, o None si ninguna fuente lo revela.

    Recibe las fuentes en orden de confianza y devuelve el primer acierto. Para
    Coto eso es (icono, textoDescuento, descripcion): el nombre del logo es mucho
    más confiable que la prosa, donde "Visa" y "Mastercard" aparecen en casi todas
    las promos y dirían la marca de la tarjeta en vez del banco que la emite.

    Devolver None es un resultado legítimo, no un error: el llamador descarta la
    promo con log. Adivinar acá produciría un descuento atribuido al banco
    equivocado, que es peor que no tenerlo.
    """
    for fuente in fuentes:
        if not fuente:
            continue

        # El nombre del logo viene como "logo_naranjax2.png": se le sacan la
        # extensión y los separadores para que quede texto matcheable.
        texto = normalize_label(str(fuente).replace("_", " ").replace("-", " ").replace(".", " "))
        if not texto:
            continue

        for ruido in _FRASES_RUIDO:
            texto = texto.replace(ruido, " ")

        for alias, slug in _ALIASES_POR_LONGITUD:
            if _ALIAS_RES[alias].search(texto):
                return slug

    return None


def is_membership(entidad: str) -> bool:
    """¿Esta entidad se declara como membresía en vez de como tarjeta bancaria?"""
    return entidad in MEMBERSHIP_ENTITIES


# Nombres para mostrar, sólo donde el título automático queda mal. El default
# (slug.replace("_", " ").title()) sirve para la mayoría — "galicia" -> "Galicia" —
# pero destroza las siglas ("Icbc") y se come las tildes.
DISPLAY_NAMES = {
    "icbc": "ICBC",
    "bbva": "BBVA",
    "hsbc": "HSBC",
    "amex": "American Express",
    "nacion": "Nación",
    "naranja_x": "Naranja X",
    "modo": "MODO",
    "uala": "Ualá",
    "itau": "Itaú",
    "coto_tci": "Coto TCI",
    "club_dia": "Club Día",
    "mi_carrefour": "Mi Carrefour",
    "comunidad_coto": "Comunidad Coto",
    "mercado_pago": "Mercado Pago",
    "carrefour_banco": "Carrefour Banco",
    "club_la_nacion": "Club La Nación",
    "personal_pay": "Personal Pay",
    "banco_del_sol": "Banco del Sol",
}


def display_name(entidad: str) -> str:
    """Nombre legible de una entidad, para los textos que ve el usuario."""
    return DISPLAY_NAMES.get(entidad) or entidad.replace("_", " ").title()
