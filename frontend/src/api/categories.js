import { apiFetch } from "./client";

/**
 * Las góndolas del catálogo, agrupadas por sección:
 * `[{ section, shelves: [{ slug, label }] }]`.
 *
 * Reemplazó a `getCategoryTree()` (`GET /categories/tree`), que traía la
 * taxonomía completa de Coto y Día mergeada por embeddings: ~15 top-levels y
 * cientos de hojas sobre un catálogo de 20 góndolas, así que casi todo lo que se
 * clickeaba no tenía productos y caía a una búsqueda semántica por su nombre.
 * Acá cada hoja tiene productos por construcción, y por eso también desapareció
 * `has_direct_category_match`: todo click rutea a `/categoria/{slug}`.
 */
export function getShelfSections() {
  return apiFetch("/categories");
}
