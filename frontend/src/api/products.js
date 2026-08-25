import { apiFetch } from "./client";

// A diferencia del resto de los facets (marca, precio, tienda), que se resuelven
// en memoria sobre lo ya fetcheado, los dietarios viajan a la API: el backend solo
// devuelve los `limit` productos más cercanos, así que filtrar del lado del cliente
// mostraría un puñado de resultados en vez de `limit` resultados que cumplan.
// Solo se manda el parámetro cuando está activo, para no ensuciar la URL.
function appendDietaryParams(params, dietary) {
  if (dietary?.glutenFree) params.set("gluten_free", "true");
  if (dietary?.vegan) params.set("vegan", "true");
  return params;
}

export function searchProducts(query, limit = 20, dietary) {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  appendDietaryParams(params, dietary);
  return apiFetch(`/search?${params.toString()}`);
}

export function getProductsByCategory(categoryName, limit = 50, dietary) {
  const params = new URLSearchParams({ limit: String(limit) });
  appendDietaryParams(params, dietary);
  return apiFetch(`/category/${encodeURIComponent(categoryName)}?${params.toString()}`);
}

/**
 * Trae los productos de una lista de unified_id, en el mismo orden en que se
 * piden.
 *
 * Lo usa el historial, que guarda unified_ids en localStorage y necesita
 * resolverlos contra el catálogo de HOY. /price-preview no alcanza: devuelve
 * precio pero ningún metadato.
 *
 * Un id ausente de la respuesta NO es un error de red: significa que el producto
 * ya no existe en el catálogo, porque lo borró el pruning del scraper. Ese es el
 * contrato del endpoint y es la razón por la que existe.
 */
export function getProductsByIds(unifiedIds) {
  return apiFetch("/products/by-ids", {
    method: "POST",
    body: JSON.stringify({ unified_ids: unifiedIds }),
  });
}
