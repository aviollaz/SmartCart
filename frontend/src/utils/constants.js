// Espeja src/category_tree.py DIRECT_MATCH_BUCKETS: los únicos valores que
// existen literalmente en unified_products.category y por lo tanto resuelven
// vía GET /category/{label} en lugar de GET /search?q=.
export const DIRECT_MATCH_SHORTCUTS = ["Lácteos", "Golosinas", "Almacén", "Otros"];

// Tiendas que participan de la comparación, en un solo lugar: dibuja los
// checkboxes de disponibilidad y de acá sale el estado neutro del filtro en
// useProductFilters. Los store_id espejan las claves de
// src/optimizer.py DEFAULT_MIN_SPEND_LIMITS.
export const STORES = [
  { id: "coto_online", label: "Disponible en Coto" },
  { id: "dia_online", label: "Disponible en Día" },
  { id: "carrefour_online", label: "Disponible en Carrefour" },
];
