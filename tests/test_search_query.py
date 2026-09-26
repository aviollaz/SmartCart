# tests/test_search_query.py
"""
Suite pura (sin Postgres ni sentence-transformers) de src/search.py.

Lo que se protege: que la query del usuario nunca llegue a `to_tsquery` como
sintaxis (un "&" o un ":" suelto es un error de Postgres, o sea un 500 en
/search), y que el modo elegido sea el SQL que realmente corre.
"""
import pytest

from src import search
from src.search import build_lexical_query, search_rows


def test_tokens_en_or_con_prefijo():
    assert build_lexical_query("Oreo 354g") == "oreo:* | 354:*"


def test_decimales_con_coma_o_punto_quedan_como_un_numero():
    assert build_lexical_query("coca cola 2,25") == "coca:* | cola:* | 2.25:*"
    assert build_lexical_query("coca cola 2.25") == "coca:* | cola:* | 2.25:*"


def test_los_acentos_se_conservan_para_que_los_saque_postgres():
    # smartcart_unaccent corre del lado de Postgres, sobre la query y sobre el
    # tsvector por igual: sacarlos acá también sería una segunda regla.
    assert build_lexical_query("Café") == "café:*"


@pytest.mark.parametrize("q", ["leche & pan", "leche:* | !x", "(yerba)", "o'hara", "yerba<->mate"])
def test_la_sintaxis_de_tsquery_nunca_pasa(q):
    resultado = build_lexical_query(q)
    assert resultado is not None
    for caracter in "&!()<>'":
        assert caracter not in resultado
    # Cada término es `palabra:*`, separado por " | ": nada más.
    for termino in resultado.split(" | "):
        palabra, sufijo = termino.split(":")
        assert sufijo == "*" and palabra


def test_letras_sueltas_se_descartan_pero_los_numeros_no():
    assert build_lexical_query("yerba x 1 kg") == "yerba:* | 1:* | kg:*"


def test_tokens_repetidos_van_una_vez():
    assert build_lexical_query("leche leche") == "leche:*"


@pytest.mark.parametrize("q", ["", "   ", "&&", "a b c", None])
def test_sin_tokens_utiles_devuelve_none(q):
    assert build_lexical_query(q) is None


class FakeCursor:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def fetchall(self):
        return []


def test_el_modo_denso_no_toca_el_tsvector():
    cur = FakeCursor()
    search_rows(cur, "[0.1]", "oreo", 10, mode="denso")

    sql, params = cur.calls[-1]
    assert "name_tsv" not in sql
    assert params["limit"] == 10 and params["pool"] == search.SEARCH_POOL_SIZE


def test_el_modo_hibrido_fusiona_las_dos_mitades():
    cur = FakeCursor()
    search_rows(cur, "[0.1]", "oreo", 10, mode="hibrido")

    sql, params = cur.calls[-1]
    assert "name_tsv @@ q" in sql and "dense_ranked" in sql
    assert params["tsq"] == "oreo:*" and params["k"] == search.RRF_K


def test_el_hibrido_sin_tokens_cae_al_denso():
    cur = FakeCursor()
    search_rows(cur, "[0.1]", "&&", 10, mode="hibrido")

    sql, _ = cur.calls[-1]
    assert "name_tsv" not in sql


def test_siempre_sube_ef_search_antes_de_buscar():
    """Sin esto el pool queda topeado en 40 filas sin ningún error a la vista."""
    cur = FakeCursor()
    search_rows(cur, "[0.1]", "oreo", 10, mode="hibrido")

    sql, params = cur.calls[0]
    assert "hnsw.ef_search" in sql
    assert params == (str(search.SEARCH_EF_SEARCH),)


def test_el_filtro_dietario_se_aplica_a_las_dos_mitades():
    cur = FakeCursor()
    search_rows(cur, "[0.1]", "oreo", 10, dietary_clause="AND is_vegan = TRUE", mode="hibrido")

    sql, _ = cur.calls[-1]
    assert sql.count("AND is_vegan = TRUE") == 2


def test_un_modo_desconocido_levanta():
    with pytest.raises(ValueError):
        search_rows(FakeCursor(), "[0.1]", "oreo", 10, mode="bm25")
