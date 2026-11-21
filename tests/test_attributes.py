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


def test_leche_descremada_no_se_reemplaza_por_parcial_descremada():
    # preparar: redacción vista en Carrefour con medir_reemplazos
    original = "Leche Descremada Manfrey Uat 1 Lt"
    candidato = "Leche ulta parcial descremada Carrefour classic sachet 1 lt."

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


# --------------------------------------------------------------------------
# Todas las góndolas: pares reales de medir_reemplazos (nov-2026)
# --------------------------------------------------------------------------

DISTINTO_TIPO = [
    ("arroz-y-legumbres", "Porotos alubia Egran bolsa 500 g", "Arroz parboil Molinos Ala dorado 500 grs"),
    ("arroz-y-legumbres", "Garbanzos . La Egipcian Bsa 400 Grm", "Lentejas secas Egran Bolsa 400 g"),
    ("azucar-y-endulzantes", "Azucar Organica Dia 500 Gr.", "Azúcar Dulkre Stevia Paquete 500 Gr"),
    ("conservas-de-pescado", "Pulpo Al Ajillo Vigilante 115 Gr", "Filetes Atun En Aceite GOMES DA COSTA Oliva Caja 125 Gr"),
    ("conservas-de-vegetales", "Garbanzos Coto 350g", "Porotos Secos Remojados Dia 340 Gr."),
    ("encurtidos-y-aceitunas", "Berenjenas al escabeche Carrefour Extra 350 grs", "Aceitunas verdes Nucete 180 g."),
    ("espumantes-y-sidras", "Espumante Federico de alvear extra dulce 750 cc.", "Espumante extra brut Cordero con piel de Lobo 750 cc"),
    ("cereales", "Granola Coto con frutos rojos 300g", "Aritos de cereal 3 Arroyos frutado bolsa 160 g."),
    ("aguas", "Agua mineralizada bajo sodio sin gas Benedictino 1.5 lts", "Agua mineralizada con gas Benedictino 1.5 lts"),
    ("energizantes-e-isotonicas", "Bebida energizante Monster Pipeline Punch 473 ml", "Bebida energizante Monster zero en lata 473 cc."),
    ("gaseosas", "Gaseosa lima limón 7 Up light en lata 354 ml", "Gaseosa lima limón Sprite 354 ml"),
    ("desodorantes", "Desodorante antitranspirante masculino NIVEA Derma Control Sensitive Roll-On x 50 ml",
     "Desodorante antitranspirante femenino NIVEA Protect & Care Roll On x 50 ml"),
    ("cepillos-de-dientes", "Cepillo Dental Gum Classic 409 Suave", "Cepillo Dental Infantil Suave Paw Patrol x 1 Un Gum"),
    ("cervezas", "Cerveza Cusqueña Oscura 330cc", "Cerveza rubia Brahma 354 ml"),
    ("vinos", "Vino Tinto Fiel Red Blend 750 Ml.", "Vino tinto dulce ALARIS 750ml"),
    ("frutas", "Naranja para Jugo por Kg", "Manzana Roja Comercial en bolsa malla x Kg."),
    ("verduras", "Papa Colorada x 1 Kg", "Lechuga francesa x kg"),
    ("pollo", "Pollo entero x kg", "Pata de pollo x kg"),
    ("aperitivos-y-licores", "Licor de chocolate Tres Plumas 700 cc", "Gin Heredero en botella 700 ml"),
    ("yogures", "Yogur Milkaut Zero Frutilla Pote 180g", "Yogurt Sabor Frutilla Firme 180 Grs Milkaut"),
    ("pastas-frescas", "Fideos Mostacholes Dia 500 Gr.", "Ravioles De Ricotta Yuli 500g"),
    ("pescados-congelados", "Trucha Filete Grande Con Piel X Kg", "Filet de Merluza Dia 500 Gr."),
    ("salsas-de-tomate", "Salsa De Tomate Frito 400gr La Molisana", "Tomate Cubeteado La Campagnola 400 Gr"),
    ("quesos-rallados", "Queso Rallado Reggianito 100 Grs Cuisine & Co", "Alimento a base de queso rallado La Quesera 100 grs"),
    ("quesos-duros", "Queso La Serenísima pategras sin lactosa x kg.", "Queso Pategrás x Kg La Serenisima"),
    ("quesos-blandos", "Queso Port Salut Light Punta Del Agua x kg", "Queso Cremoso PUNTA DEL AGUA X Kg"),
    ("quesos-untables", "Queso Untable Primer Premio 200g", "Queso Crema Original Quescrem 200g"),
    ("manteca-y-margarina", "Manteca Check 200 G", "Manteca Extra Sal Tonadita 200g"),
    ("cremas-de-leche", "Crema La Serenísima 200 Ml", "Crema La serenisima liviana 200 cc."),
    ("dulce-de-leche", "Dulce de Leche Repostero DIA 400 Gr.", "Dulce de Leche Ser 400 grs"),
    ("limpiadores-de-bano", "Destapa cañerias Ayudín 1 l.", "HARPIC Gel Limpiador De Inodoros Desinfectante Blanco Y Brillante 500ml"),
    ("pastillas-inodoro", "Canasta Liquida Baño Lavanda Full PATO PURIFIC 50ml", "Canasta Liquida Baño Lavanda Repuesto PATO PURIFIC 50ml"),
    ("huevos", "Huevos Color 12 Un Cuisine & Co", "Huevos Blancos Check 12 U"),
    ("pan-lactal", "Pan Salvado Fargo 390 grs", "Pan Lacteado Fargo 370g"),
    ("pan-hamburguesa", "Pan Para Panchos 240 G", "Pan De Hamburguesas 130 Gr Schar"),
    ("fiambres", "Bondiola Feteada Campo Austral 150g", "Pechuga de pavo fet Campo Austral 150 g."),
    ("hamburguesas-congeladas", "Milanesas De Lentejas Viaveg 220g", "Medallon Carne Vacuna/Soja Paty 110g"),
    ("rebozados-congelados", "Nuggets de soja Felices las Vacas sabor pollo 300 grs", "Nuggets de Pollo Grangys Crocantes 300g"),
    ("vegetales-congelados", "Frutillas Fresh Medianas Congeladas 1 Kg", "Espinaca Congelada Granja Del Sol 1kg"),
    ("harinas", "Almidón de maiz Carrefour Classic 500 grs", "Polenta DEL CAMPO Paquete 500 Gr"),
    ("snacks", "Pochoclos Hanks Peanut 112 Gr", "Palitos salados sabor panceta Pep 120 g."),
    ("caldos-y-sopas", "Condimento Para Gallina SAZÓN Paquete 60 Gr", "Sopa crema Knorr de vegetales 60 g"),
    ("mermeladas-y-miel", "Dulce De Membrillo Esnaola Trozado Sobre 1 Kg", "Miel Cremosa Entrenuts 500gr"),
    ("cacao-y-chocolatadas", "Chocolate Bonafide Para Taza 100 Gr", "Chocolate Amargo 60% Cacao 100 Grs Bonafide"),
    ("chocolates", "Lentejas De Chocolate Confitadas Plenario 80 Gr", "Tableta de chocolate con leche Nestlé suave y cremoso 80 grs"),
    ("galletitas", "Galletitas Trío frolitas 300 g.", "Galletitas crackers Paseo multicereal 300 g."),
    ("golosinas", "Mani Con Chocolate Cofler C/leche 100g", "Obleas Chocolat C/Rel 9 De Oro Fwp 100 Grm"),
    ("budines-y-bizcochuelos", "Pan Dulce Firenze Matero con Fruta 350 Gr.", "Pudding Naranja Con Cascara 100 Ducados 350 Gr"),
    ("postres-y-flanes", "Postre De Manzana Y Pera X2 ANELA FRUITS 200g", "Postre Sabor Chocolate Panna Cotta x 2 Un 180 Grs Sterilgarda"),
    ("tampones", "Tampones KOTEX Mini x12 unidades", "Tampones KOTEX Super x12 unidades"),
    ("afeitado", "Gel de afeitar Nivea Men Sensitive para piel sensible 200 ml",
     "Bálsamo After shave Nivea Men Sensitive para piel sensible 100 ml"),
    ("cremas-corporales", "Crema Hidratante Corporal NEUTROGENA Hidrata & Suaviza 200 Ml", "Crema De Manos Cuidado Intensivo 100 Ml Nivea"),
    ("pasta-dental", "Crema dental Sudanta cuidado total 50 grs", "Crema Dental ORAL B Kids Pomo 50 Gr"),
    ("algodon-e-hisopos", "Paños Desmaquillantes Estrella X40u", "Hisopos Bonte 100 Ud."),
    ("limpiadores-de-cocina", "Limpiador líquido desinfectante Lysoform multisuperficies gatillo 500 ml.",
     "PROCENEX Limpiador De Cocina Naranja Gatillo 500ml"),
    ("detergente", "Detergente Líquido Ala Concentrado Limón 300ml", "Lavavajillas Detergente Para Diluir Limón Rinde 300ml X 100ml"),
    ("lavandina", "Lavandina Querubin 2l", "Lavandina Concent. Querubin Bot 1 Ltr"),
    ("limpiavidrios", "Limpiavidrios Limpiamax Gauchita X 1u.", "Limpia Vidrios Y Multiuso Cif 500ml"),
    ("limpiadores-de-piso", "Acondicionadores CERAMICOL Botella 1L", "Limpiador de piso Pinoluz limón 900 ml"),
    ("jabon-para-ropa", "ZORRO Evolution Polvo Quitamanchas 3kg", "Jabón Líquido Para Ropa ARIEL Platinum Doypack 3lt"),
    ("papas-congeladas", "Papas Hornedas Estilo Artesanal MCCAIN 700g", "Croquetas de papas golazo MC CAIN 700g"),
    ("comidas-congeladas", "Barritas De Muzzarella 300 Gr Cuisine & Co", "Chipá Congelado Dia 300 Gr."),
    ("yerba-mate", "Yerba mate Cachamate rosa paquete 1 kg.", "Yerba Tradicional 1 Kg Cachamai"),
    ("te-e-infusiones", "Té de manzanilla en saquitos La Virginia x 25 uni", "Té negro en saquitos La Virginia x 25 uni"),
    ("shampoo", "Shampo Niños Protección Nat Plusbelle Bot 700 Ml", "Shampoo esencia Brillo Profundo PLUSBELLE 700ml"),
    ("papel-higienico", "Papel higiénico hoja simple Carrefour Essential 4 x 80 m.", "Papel Higiénico ELITE Ultra Suave Doble Hoja 50 M 4 Un"),
    ("proteccion-solar", "Protector Solar Sun Fresh Fps 70 Neutrogena 200ml", "Protector Solar Fps 50 Niños Dermaglos 180 Ml"),
    ("aceites-y-aderezos", "Salsa Mayonesa Con Chimichurri TAU 300g", "Salsa cheddar TAU botella pet 300 g."),
    ("suavizantes", "Suavizante Concentrado Violetas Dia 500 Ml.", "Suavizante para Ropa Frescura Matinal 900 Ml Héroe"),
    # Segunda corrida de medir_reemplazos, con las tablas ya puestas:
    ("quesos-rallados", "Queso rallado Tregar 120 g", "Queso Procesado Rallado Deshidratado x 120 Grs Parmiginas"),
    ("pasta-dental", "Crema Dental Colgate Max White Laminas Blanq 102 G", "Pasta Dental COLGATE Sensitive Pro-Alivio Real White 110g"),
]

MISMO_TIPO = [
    ("arroz-y-legumbres", "Poroto Pallares COTO 500g", "Porotos pallares secos 500 g"),
    ("conservas-de-vegetales", "Garbanzos Coto 350g", "Garbanzos secos remojados Inca 350 g."),
    ("aguas", "Agua Mineral Sin Gas Dia 6,25 Lt.", "Agua Sin Gas Mineral Coto 6.25l"),
    ("energizantes-e-isotonicas", "Bebida Isotónica Powerade Naranja 500 Ml", "Bebida Isotónica Powerade Manzana 500 ml"),
    ("frutas", "Naranja para Jugo por Kg", "Naranja de jugo x kg."),
    ("vinos", "Vino tinto Cabernet Sauvignon Intimo 750 ml", "Vino Tinto Estiba I Cabernet Sauvignon 750 Ml."),
    ("pastas-secas", "Fideos Largos Tallarines Bonavita 500g", "Fideos tallarines Favorita 500 g."),
    ("yerba-mate", "Yerba mate Verdeflor con menta 500 g.", "Yerba mate Verdeflor con hierbas serranas 500 g."),
    ("cervezas", "Cerveza rubia Golsch retornable 925 ml", "Cerveza Rubia Grolsch Retornable 925 Ml"),
    ("desodorantes", "Antitranspirante Dove Men Invisible Dry 150ml", "Desodorante Antitranspirante DOVE Men Men Care Invisible Dry 150 Ml"),
    ("quesos-rallados", "Queso rallado Ilolay 120 g", "Queso Rallado SPALEN 120g"),
    ("gaseosas", "Gaseosa naranja Manaos 2,25 lts", "Gaseosa Fanta naranja 2,25 lts"),
    ("galletitas", "Galletitas rellenas Bon o Bon Cofler 85 g.", "Galletitas rellenas vainilla choco Cofler 85 g."),
    ("verduras", "Repollo Blanco Por Kg", "Repollo Blanco 1 Kg"),
]


def test_reemplazos_de_distinto_tipo_se_rechazan():
    # preparar / ejecutar: cada par real que salió mal en la medición
    aceptados = [(shelf, a, b) for shelf, a, b in DISTINTO_TIPO if attributes_match(shelf, a, b)]

    # verificar
    assert aceptados == []


def test_reemplazos_del_mismo_tipo_se_siguen_aceptando():
    # preparar / ejecutar: pares reales correctos, incluido el sabor (libre)
    rechazados = [(shelf, a, b) for shelf, a, b in MISMO_TIPO if not attributes_match(shelf, a, b)]

    # verificar
    assert rechazados == []


def test_coloracion_no_tiene_reemplazo():
    # preparar: el tono es lo que se compra
    original = "Tinte Para Cabello 20 Negro Soft Color"
    candidato = "Tinte Para Cabello 20 Negro Soft Color"

    # ejecutar
    compatibles = attributes_match("coloracion", original, candidato)

    # verificar
    assert compatibles is False


def test_sin_tacc_solo_se_reemplaza_por_sin_tacc():
    # preparar
    ancla = {"id": "sin_tacc", "name": "Fideos sin TACC mostacholes Blue Patna 500 g.", "shelf": "pastas-secas",
             "total_volume_weight": 500.0, "unit_type": "g", "name_embedding": "[1]",
             "is_gluten_free": True, "is_vegan": False}
    con_gluten = {"id": "comun", "name": "Fideos Mostachol Dia 500 Gr.", "total_volume_weight": 500.0,
                  "unit_type": "g", "distance": 0.2, "is_gluten_free": False, "is_vegan": False}
    otro_sin_tacc = {"id": "otro", "name": "Fideos sin TACC mostachol Aglu 500 g.", "total_volume_weight": 500.0,
                     "unit_type": "g", "distance": 0.3, "is_gluten_free": True, "is_vegan": False}
    cur = _Cursor({"sin_tacc": [con_gluten, otro_sin_tacc]})

    # ejecutar
    candidatos = comparable_candidates(cur, {"sin_tacc": ancla}, ["dia_online"])

    # verificar
    assert [c["uid"] for c in candidatos["sin_tacc"]] == ["otro"]


def test_vegano_solo_se_reemplaza_por_vegano():
    # preparar
    ancla = {"id": "vegano", "name": "Postre A Base De Plantas Dulce De Leche Felices Las Vacas 125 Gr.",
             "shelf": "postres-y-flanes", "total_volume_weight": 125.0, "unit_type": "g",
             "name_embedding": "[1]", "is_gluten_free": False, "is_vegan": True}
    no_vegano = {"id": "gandara", "name": "Postre Sabor Dulce De Leche Gandara 120g", "total_volume_weight": 120.0,
                 "unit_type": "g", "distance": 0.2, "is_gluten_free": False, "is_vegan": False}
    cur = _Cursor({"vegano": [no_vegano]})

    # ejecutar
    candidatos = comparable_candidates(cur, {"vegano": ancla}, ["coto_online"])

    # verificar
    assert candidatos == {}
