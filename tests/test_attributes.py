"""
Atributos que un reemplazo tiene que compartir con el original (src/attributes.py).

Puro Python. Los nombres son reales del catálogo: el motivo de la tabla son
reemplazos malos que salieron con ellos ("reducida en lactosa" -> chocolatada,
Nidina -> leche en polvo común).
"""
from src.attributes import attributes_match
from src.substitutions import comparable_candidates


def test_leche_sin_lactosa_no_se_reemplaza_por_chocolatada():
    # preparar
    original = "Leche reducida en lactosa UAT Carrefour classic 1 lt."
    candidato = "Leche Chocolatada Dia Larga Vida 1 Lt."

    # ejecutar
    compatibles = attributes_match("leches", original, candidato)

    # verificar
    assert compatibles is False


def test_leche_sin_lactosa_acepta_otra_redaccion():
    # preparar
    original = "Leche reducida en lactosa UAT Carrefour classic 1 lt."
    candidatos = [
        "Leche UAT Zero lactosa La Serenisima 1L",
        "Leche UHT 0% Lactosa Las Tres Niñas 1 lt",
        "Leche Deslactosada Larga Vida Ilolay 1 L",
    ]

    # ejecutar
    resultados = [attributes_match("leches", original, c) for c in candidatos]

    # verificar
    assert resultados == [True, True, True]


def test_leche_comun_no_se_reemplaza_por_una_sin_lactosa():
    # preparar
    original = "Leche Entera DIA Larga Vida 1 Lt."
    candidato = "Leche UAT Zero lactosa La Serenisima 1L"

    # ejecutar
    compatibles = attributes_match("leches", original, candidato)

    # verificar
    assert compatibles is False


def test_leche_en_polvo_no_se_reemplaza_por_fluida():
    # preparar
    original = "Leche Entera en Polvo DIA 800 Gr."
    candidato = "Leche Entera DIA Larga Vida 1 Lt."

    # ejecutar
    compatibles = attributes_match("leches", original, candidato)

    # verificar
    assert compatibles is False


def test_leche_entera_no_se_reemplaza_por_descremada():
    # preparar: la del original no declara la grasa, y eso es entera
    original = "Leche Larga Vida CIUDAD DEL LAGO Ttb 1 L"
    candidato = "Leche Semi Descremada DIA Larga Vida 1 Lt."

    # ejecutar
    compatibles = attributes_match("leches", original, candidato)

    # verificar
    assert compatibles is False


def test_bebida_vegetal_solo_se_reemplaza_por_vegetal():
    # preparar
    original = "Bebida vegetal protein Biba brick 500 ml"
    vegetal = "Bebida de Almendras Original Silk 1 L"
    no_vegetal = "Bebida Protein Vainilla 260ml Nutren"

    # ejecutar
    con_vegetal = attributes_match("leches", original, vegetal)
    con_no_vegetal = attributes_match("leches", original, no_vegetal)

    # verificar
    assert (con_vegetal, con_no_vegetal) == (True, False)


def test_leche_infantil_no_se_reemplaza_por_leche_comun():
    # preparar: el nombre no dice "infantil"; lo dice la marca
    original = "Leche En Polvo 800gr 1 Nidina"
    candidato = "Leche Entera en Polvo DIA 800 Gr."

    # ejecutar
    compatibles = attributes_match("leches", original, candidato)

    # verificar
    assert compatibles is False


def test_carne_no_se_reemplaza_por_otro_corte():
    # preparar
    original = "Asado x kg"
    candidato = "Peceto x kg"

    # ejecutar
    compatibles = attributes_match("carnes", original, candidato)

    # verificar
    assert compatibles is False


def test_carne_sin_corte_reconocido_no_tiene_reemplazo():
    # preparar: ninguno de los dos tiene un corte de la tabla
    original = "Carne envasada x kg"
    candidato = "Carne envasada x kg"

    # ejecutar
    compatibles = attributes_match("carnes", original, candidato)

    # verificar
    assert compatibles is False


def test_gondola_sin_tabla_no_filtra_por_atributos():
    # preparar
    original = "Yerba Mate Playadito 1 Kg"
    candidato = "Yerba Mate Suave Taragüi 1 Kg"

    # ejecutar
    compatibles = attributes_match("yerba", original, candidato)

    # verificar
    assert compatibles is True


class _Cursor:
    """La query de vecinos de src/substitutions.py, con vecinos fijos."""

    def __init__(self, neighbors):
        self.neighbors = neighbors
        self._result = []

    def execute(self, sql, params):
        _, _, anchors = params
        self._result = [{**row, "anchor_id": uid} for uid in anchors for row in self.neighbors.get(uid, [])]

    def fetchall(self):
        return self._result


def test_comparable_candidates_descarta_atributos_distintos():
    # preparar: la chocolatada es la más cercana, la zero lactosa viene después
    ancla = {"id": "sin_lactosa", "name": "Leche reducida en lactosa UAT Carrefour classic 1 lt.",
             "shelf": "leches", "total_volume_weight": 1000.0, "unit_type": "ml", "name_embedding": "[1]"}
    chocolatada = {"id": "chocolatada", "name": "Leche Chocolatada Dia Larga Vida 1 Lt.",
                   "total_volume_weight": 1000.0, "unit_type": "ml", "distance": 0.38}
    zero = {"id": "zero", "name": "Leche UAT Zero lactosa La Serenisima 1L",
            "total_volume_weight": 1000.0, "unit_type": "ml", "distance": 0.41}
    cur = _Cursor({"sin_lactosa": [chocolatada, zero]})

    # ejecutar
    candidatos = comparable_candidates(cur, {"sin_lactosa": ancla}, ["dia_online"])

    # verificar
    assert [c["uid"] for c in candidatos["sin_lactosa"]] == ["zero"]
