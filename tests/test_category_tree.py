# tests/test_category_tree.py
from src.category_tree import (
    build_category_tree,
    _merge_labels,
    _normalize,
    DIRECT_MATCH_BUCKETS,
)


def test_build_category_tree_returns_known_buckets_without_model():
    # Sin modelo: solo corre el merge por texto normalizado + contención de
    # tokens + alias manuales (rápido, sin cargar sentence-transformers).
    tree = build_category_tree(model=None)

    assert len(tree) > 0
    assert "Almacén" in tree
    assert tree["Almacén"]["has_direct_category_match"] is True
    assert len(tree["Almacén"]["subcategories"]) > 0

    for top_label, node in tree.items():
        assert node["label"] == top_label
        assert node["has_direct_category_match"] == (top_label in DIRECT_MATCH_BUCKETS)
        for sub_label, sub_node in node["subcategories"].items():
            assert sub_node["label"] == sub_label
            assert isinstance(sub_node["leaves"], list)


def test_build_category_tree_merges_hogar_variants_via_token_containment():
    # "Hogar" (Coto) vs "Hogar y Deco" (Día): mismo concepto, sin match de
    # texto exacto. La contención de tokens ({hogar} ⊆ {hogar, deco}) debe
    # fusionarlos sin necesitar el modelo de embeddings.
    tree = build_category_tree(model=None)

    assert "Hogar" in tree
    assert "Hogar y Deco" not in tree


def test_build_category_tree_merges_manual_aliases():
    # "Fiambres" (Frescos, Coto) vs "Fiambrería" (Frescos, Día): mismo rubro,
    # sin palabras en común (no hay contención de tokens) y por debajo del
    # umbral conservador de embeddings -> requiere el alias manual explícito.
    tree = build_category_tree(model=None)

    fiambres_subs = tree["Frescos"]["subcategories"]
    assert "Fiambrería" not in fiambres_subs
    assert any("fiambr" in _normalize(sub) for sub in fiambres_subs)


def test_normalize_strips_accents_case_and_whitespace():
    assert _normalize("Panadería") == _normalize("panaderia")
    assert _normalize("Aire  Libre") == _normalize("aire libre")


def test_merge_labels_keeps_unrelated_labels_separate_without_model():
    # Sin señal de contención de tokens ni de embeddings, etiquetas distintas
    # no deben fusionarse solo por pertenecer al mismo rubro.
    labels = ["Cuidado Personal", "Cuidado Bucal", "Cuidado del Cabello"]
    merged = _merge_labels(labels, model=None, threshold=0.90, manual_aliases={})

    assert len(set(merged.values())) == 3


def test_merge_labels_merges_token_subset_pairs_without_model():
    labels = ["Golosinas", "Golosinas y Alfajores"]
    merged = _merge_labels(labels, model=None, threshold=0.90, manual_aliases={})

    assert merged["Golosinas"] == merged["Golosinas y Alfajores"]
