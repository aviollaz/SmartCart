# src/category_tree.py
"""
Construye un árbol de categorías (top-level -> subcategoría -> leaves) a partir
de las taxonomías estáticas ya scrapeadas de Coto y Día (src/scrapers/*_categories.json).

Estos archivos no están vinculados a productos en la base de datos: son la
navegación completa de cada sitio, usada hoy solo por los scripts de scraping
para saber qué categorías recorrer. Este módulo los reutiliza puramente para
alimentar el mega-menú del frontend con una jerarquía real de 2-3 niveles.

Coto y Día redactan categorías equivalentes de forma distinta (ej. "Golosinas"
vs. "Golosinas y Alfajores", o "Hogar" vs. "Hogar y Deco"). El merge se hace en
capas, de más barata a más costosa:
  1. Texto normalizado (sin acentos, sin mayúsculas, espacios colapsados).
  2. Alias manuales explícitos (escape hatch para casos puntuales mal resueltos).
  3. Similaridad semántica por embeddings (reutiliza el modelo `all-MiniLM-L6-v2`
     que el backend ya carga para la búsqueda semántica de productos, sin
     agregar ninguna dependencia nueva).
"""
import json
import os
from functools import lru_cache

import numpy as np

from src.text_utils import normalize_label

_BASE_DIR = os.path.dirname(__file__)
_COTO_CATEGORIES_PATH = os.path.join(_BASE_DIR, "scrapers", "coto_categories.json")
_DIA_CATEGORIES_PATH = os.path.join(_BASE_DIR, "scrapers", "dia_categories.json")

# Únicos valores que existen literalmente en unified_products.category
# (ver SmartCartDB.CATEGORY_MAP en src/database.py) -> permiten resolver un
# click de mega-menú vía GET /category/{label} en lugar de GET /search?q=.
DIRECT_MATCH_BUCKETS = {"Lácteos", "Golosinas", "Almacén"}

# Calibrado empíricamente contra pares reales de las taxonomías de Coto/Día:
# pares que SÍ son la misma categoría con distinta redacción ("Golosinas" vs.
# "Golosinas y Alfajores" = 0.798, "Hogar" vs. "Hogar y Deco" = 0.680) caen en
# la MISMA banda de similaridad que pares que NO lo son ("Cuidado Personal" vs.
# "Cuidado del Cabello" = 0.751, "Cuidado Bucal" vs. "Cuidado Personal" = 0.778).
# Un único umbral de coseno no separa estos dos grupos de forma confiable, así
# que la similaridad semántica se usa solo como respaldo de alta confianza
# (umbral alto) y la señal principal para el caso común ("X" vs. "X y Z") es la
# contención de tokens significativos, ver _tokens_subset_match().
TOPLEVEL_MERGE_THRESHOLD = 0.90
SUBCATEGORY_MERGE_THRESHOLD = 0.90

_SPANISH_STOPWORDS = {"y", "de", "del", "la", "las", "el", "los", "en", "con", "para", "sin"}

# Escape hatch manual: normalizar(label origen) -> label objetivo (se resuelve
# antes del paso de contención de tokens y de embeddings). Se completó
# revisando una vez el árbol generado y detectando duplicados reales que ni
# la contención de tokens ni el umbral conservador de embeddings atrapan
# (mismo pasillo/rubro, redacción sin palabras en común):
MANUAL_TOPLEVEL_ALIASES = {}
MANUAL_SUBCATEGORY_ALIASES = {
    "aceites y condimentos": "Aceites y Aderezos",
    "pasta seca, lista y rellenas": "Pastas Seca",
    "fiambres": "Fiambrería",
    "cuidado del pelo": "Cuidado del Cabello",
    "papeles": "Papelería",
}


# Compartido con src/category_tags.py, que slugifica los mismos segmentos de
# categoría para guardarlos como tags: ambos tienen que normalizar igual.
_normalize = normalize_label


def _significant_tokens(label: str) -> set:
    """Palabras normalizadas de una etiqueta, sin stopwords en español."""
    norm = _normalize(label)
    return {tok for tok in norm.replace(",", " ").split() if tok not in _SPANISH_STOPWORDS}


def _is_token_subset_match(norm_a: str, norm_b: str, tokens_by_norm: dict) -> bool:
    """
    True si el conjunto de palabras significativas de una etiqueta está
    contenido en el de la otra (ej. {golosinas} ⊆ {golosinas, alfajores}).
    Cubre el patrón dominante "X" vs. "X y Z" entre Coto/Día sin depender de
    un umbral de similaridad, evitando los falsos positivos que ese umbral
    produciría entre subcategorías simplemente relacionadas (ver comentario
    sobre el calibrado de TOPLEVEL_MERGE_THRESHOLD/SUBCATEGORY_MERGE_THRESHOLD).
    """
    tokens_a, tokens_b = tokens_by_norm[norm_a], tokens_by_norm[norm_b]
    if not tokens_a or not tokens_b:
        return False
    return tokens_a.issubset(tokens_b) or tokens_b.issubset(tokens_a)


def _parse_category_file(path: str):
    """Devuelve una lista de tuplas (top, sub, leaf) a partir de un archivo de
    taxonomía con valores tipo "Top -> Sub -> Leaf" (2 o 3 niveles)."""
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    paths = []
    for value in raw.values():
        parts = [p.strip() for p in value.split("->")]
        parts = [p for p in parts if p]
        if not parts:
            continue
        top = parts[0]
        sub = parts[1] if len(parts) >= 2 else None
        leaf = " -> ".join(parts[2:]) if len(parts) >= 3 else None
        paths.append((top, sub, leaf))
    return paths


class _UnionFind:
    def __init__(self, keys_in_order):
        self._order = list(keys_in_order)
        self._index = {k: i for i, k in enumerate(self._order)}
        self._parent = {k: k for k in self._order}

    def find(self, key):
        root = key
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[key] != root:
            self._parent[key], key = root, self._parent[key]
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        # El root resultante es siempre el que apareció primero (mantiene la
        # convención "primera etiqueta vista, orden Coto -> Día, gana").
        if self._index[ra] > self._index[rb]:
            ra, rb = rb, ra
        self._parent[rb] = ra


def _merge_labels(labels_in_order, model, threshold, manual_aliases):
    """
    Recibe labels "crudas" (con repeticiones, en orden de aparición Coto->Día) y
    devuelve un dict {label_original: label_canonica} donde todas las labels que
    representan el mismo concepto (por texto normalizado, alias manual, o
    similaridad semántica) apuntan a la misma label canónica (la primera vista).
    """
    # 1. Agrupar por texto normalizado, quedándonos con la primera grafía vista.
    canonical_by_norm = {}
    norms_in_order = []
    for raw in labels_in_order:
        norm = _normalize(raw)
        if norm not in canonical_by_norm:
            canonical_by_norm[norm] = raw
            norms_in_order.append(norm)

    uf = _UnionFind(norms_in_order)

    # 2. Alias manuales explícitos (antes de gastar cómputo en embeddings).
    for norm in norms_in_order:
        alias_target = manual_aliases.get(norm)
        if alias_target:
            target_norm = _normalize(alias_target)
            if target_norm in uf._parent:
                uf.union(norm, target_norm)

    # 3. Contención de tokens significativos (señal principal, sin umbral):
    # cubre el patrón dominante "X" vs "X y Z" (ej. "Golosinas" vs "Golosinas
    # y Alfajores", "Hogar" vs "Hogar y Deco") con cero falsos positivos
    # observados en el calibrado empírico.
    tokens_by_norm = {n: _significant_tokens(canonical_by_norm[n]) for n in norms_in_order}
    for i in range(len(norms_in_order)):
        for j in range(i + 1, len(norms_in_order)):
            norm_i, norm_j = norms_in_order[i], norms_in_order[j]
            if uf.find(norm_i) == uf.find(norm_j):
                continue
            if _is_token_subset_match(norm_i, norm_j, tokens_by_norm):
                uf.union(norm_i, norm_j)

    # 4. Similaridad semántica (respaldo de alta confianza) entre los grupos
    # que sigan sin matchear tras los pasos anteriores.
    if model is not None and len(norms_in_order) > 1:
        texts = [canonical_by_norm[n] for n in norms_in_order]
        embeddings = np.asarray(model.encode(texts), dtype=float)
        magnitudes = np.linalg.norm(embeddings, axis=1, keepdims=True)
        magnitudes[magnitudes == 0] = 1.0
        unit_vectors = embeddings / magnitudes
        similarity_matrix = unit_vectors @ unit_vectors.T

        for i in range(len(norms_in_order)):
            for j in range(i + 1, len(norms_in_order)):
                if uf.find(norms_in_order[i]) == uf.find(norms_in_order[j]):
                    continue
                if similarity_matrix[i, j] >= threshold:
                    uf.union(norms_in_order[i], norms_in_order[j])

    # 5. Mapear cada label original a la canónica de su cluster final.
    root_canonical = {}
    for norm in norms_in_order:
        root = uf.find(norm)
        if root not in root_canonical:
            root_canonical[root] = canonical_by_norm[root]

    result = {}
    for raw in labels_in_order:
        norm = _normalize(raw)
        result[raw] = root_canonical[uf.find(norm)]
    return result


def build_category_tree(model=None):
    """
    Construye el árbol mergeado Coto+Día. `model` es opcional (inyección de
    dependencia): si se pasa un SentenceTransformer ya cargado (el mismo que
    usa /search), se aplica el paso de merge semántico; si es None, el árbol
    se arma solo con match de texto normalizado + alias manuales (más rápido,
    útil para tests).
    """
    coto_paths = _parse_category_file(_COTO_CATEGORIES_PATH)
    dia_paths = _parse_category_file(_DIA_CATEGORIES_PATH)
    all_paths = coto_paths + dia_paths  # Coto primero: su fraseo gana los empates

    top_labels_in_order = [top for top, _sub, _leaf in all_paths]
    top_merge_map = _merge_labels(
        top_labels_in_order, model, TOPLEVEL_MERGE_THRESHOLD, MANUAL_TOPLEVEL_ALIASES
    )

    paths_by_top = {}
    for top, sub, leaf in all_paths:
        canonical_top = top_merge_map[top]
        paths_by_top.setdefault(canonical_top, []).append((sub, leaf))

    tree = {}
    for canonical_top, sub_leaf_pairs in paths_by_top.items():
        sub_labels_in_order = [sub for sub, _leaf in sub_leaf_pairs if sub is not None]
        sub_merge_map = _merge_labels(
            sub_labels_in_order, model, SUBCATEGORY_MERGE_THRESHOLD, MANUAL_SUBCATEGORY_ALIASES
        )

        leaves_by_sub = {}
        for sub, leaf in sub_leaf_pairs:
            if sub is None:
                continue
            canonical_sub = sub_merge_map[sub]
            leaf_set = leaves_by_sub.setdefault(canonical_sub, set())
            if leaf:
                leaf_set.add(leaf)

        tree[canonical_top] = {
            "label": canonical_top,
            "has_direct_category_match": canonical_top in DIRECT_MATCH_BUCKETS,
            "subcategories": {
                canonical_sub: {"label": canonical_sub, "leaves": sorted(leaves)}
                for canonical_sub, leaves in leaves_by_sub.items()
            },
        }

    return tree


@lru_cache(maxsize=1)
def build_category_tree_cached(model=None):
    """Variante cacheada de build_category_tree (maxsize=1: el árbol se
    construye una sola vez por proceso, ya que las taxonomías son estáticas)."""
    return build_category_tree(model)
