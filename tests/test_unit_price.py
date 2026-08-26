"""
Suite pura del precio por unidad de medida (`_build_unit_price` en src/api.py).

Sin base y sin modelo: se le pasan una fila de unified_products y una lista de
ofertas ya armadas, que es exactamente lo que recibe en producción.

Importar src.api levanta el modelo de sentence-transformers al construir la app,
pero no en el import del módulo, así que esto corre sin descargar nada.
"""
import pytest

from src.api import _build_unit_price, _display_price


def _oferta(base_price, promo=None):
    return {"store_id": "coto_online", "base_price": base_price, "promo_unit_price": promo}


def _fila(unit_type="g", peso=500.0):
    return {"unit_type": unit_type, "total_volume_weight": peso}


# ---------------------------------------------------------------- base única

def test_por_kilo_para_gramos():
    # 500 g a $7.464,50 -> $14.929/kg, la mediana medida del catálogo real.
    assert _build_unit_price(_fila("g", 500.0), [_oferta(7464.50)]) == {
        "value": 14929.0, "base": "kg",
    }


def test_por_litro_para_mililitros():
    assert _build_unit_price(_fila("ml", 1500.0), [_oferta(3000.0)]) == {
        "value": 2000.0, "base": "L",
    }


def test_un_envase_chico_tambien_va_por_kilo():
    """
    Antes había un corte en 1000 (por 100 g abajo, por kilo arriba) para que un
    alfajor de 30 g no anunciara una cifra un orden de magnitud arriba de su
    propio precio. El número grande se acepta: dos bases conviviendo en la misma
    grilla rompen la comparabilidad, que es el motivo entero de mostrarlo.
    """
    resultado = _build_unit_price(_fila("g", 30.0), [_oferta(2500.0)])

    assert resultado == {"value": 83333.33, "base": "kg"}


# ------------------------------------------------- cuándo NO hay que mostrarlo

def test_unidad_desconocida_no_inventa_un_precio():
    """
    'un' es lo que devuelve normalize_magnitude() cuando SE DIO POR VENCIDO, y
    ahí `total_volume_weight` es el placeholder 1.0. Un precio por unidad
    derivado de eso es el precio del producto disfrazado de una medición que
    nadie hizo.
    """
    assert _build_unit_price(_fila("un", 1.0), [_oferta(2500.0)]) is None


@pytest.mark.parametrize("unidad", ["kg", "gr", "lt", "", None])
def test_unidad_fuera_del_vocabulario_se_cae_en_silencio(unidad):
    """El vocabulario canónico es 'g' | 'ml' | 'un'. Una fila que se escapó tiene
    que caerse de la feature, no imprimir una unidad equivocada."""
    assert _build_unit_price(_fila(unidad, 500.0), [_oferta(2500.0)]) is None


@pytest.mark.parametrize("peso", [0.0, None, -100.0])
def test_sin_peso_no_hay_precio_por_unidad(peso):
    assert _build_unit_price(_fila("g", peso), [_oferta(2500.0)]) is None


def test_sin_ofertas_no_hay_precio_por_unidad():
    assert _build_unit_price(_fila(), []) is None


def test_una_oferta_sin_precio_no_alcanza():
    assert _build_unit_price(_fila(), [_oferta(0.0)]) is None


# ------------------------------------------------------- qué precio se divide

def test_usa_el_precio_con_promo_y_no_el_de_lista():
    """
    El bug de fondo que motivó mover esto al backend: el frontend dividía
    `min_price`, que es el mínimo de los precios de LISTA, así que la card
    anunciaba el precio con descuento y el precio por kilo de otro número.
    """
    ofertas = [_oferta(10000.0, promo=5000.0)]

    assert _build_unit_price(_fila("g", 1000.0), ofertas)["value"] == 5000.0


def test_toma_la_tienda_mas_barata():
    ofertas = [_oferta(10000.0), _oferta(8000.0), _oferta(9000.0)]

    assert _display_price(ofertas) == 8000.0


def test_la_promo_de_una_tienda_le_puede_ganar_al_precio_de_lista_de_otra():
    ofertas = [_oferta(9000.0), _oferta(10000.0, promo=7000.0)]

    assert _display_price(ofertas) == 7000.0


def test_no_multiplica_por_el_pack():
    """
    El peso de un multipack no se multiplica, y no es una omisión: el número al
    lado del "xN" es a veces el total del pack y a veces el tamaño de cada
    unidad, sin nada que los distinga. Al no multiplicar, el error sólo puede ir
    hacia CARO (N× de más cuando el tamaño guardado era el unitario), nunca hacia
    barato — la asimetría que el proyecto acepta en todos lados.
    """
    fila = _fila("g", 42.0)  # "Alfajor MILKA Simple Mousse 42g Display X 6 Un."

    assert _build_unit_price(fila, [_oferta(4200.0)])["value"] == 100000.0
