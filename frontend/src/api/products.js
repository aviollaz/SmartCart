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

// Las membresías que el usuario declaró en el onboarding. Cambian PRECIOS, no
// qué productos vuelven: el backend las usa para desbloquear las promos de club
// (ver `_build_store_offer` en src/api.py), así la grilla muestra lo mismo que
// después cobra el optimizador.
function appendMemberships(params, memberships) {
  for (const membership of memberships || []) params.append("memberships", membership);
  return params;
}

export function searchProducts(query, limit = 20, dietary, memberships) {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  appendDietaryParams(params, dietary);
  appendMemberships(params, memberships);
  return apiFetch(`/search?${params.toString()}`);
}

/**
 * Los productos de una góndola, por su slug (ver `getShelfSections`).
 *
 * El slug es una clave cerrada de src/shelves.py, así que un valor inventado
 * contesta 404 y no una lista vacía: "no hay productos" y "esa góndola no
 * existe" son cosas distintas.
 */
export function getProductsByShelf(shelfSlug, limit = 50, dietary, memberships) {
  const params = new URLSearchParams({ limit: String(limit) });
  appendDietaryParams(params, dietary);
  appendMemberships(params, memberships);
  return apiFetch(`/category/${encodeURIComponent(shelfSlug)}?${params.toString()}`);
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
export function getProductsByIds(unifiedIds, memberships = []) {
  return apiFetch("/products/by-ids", {
    method: "POST",
    body: JSON.stringify({ unified_ids: unifiedIds, user_memberships: memberships }),
  });
}

/**
 * Los productos con mayor descuento de hoy, para la home. Cada uno trae
 * `discount_pct` (fracción: 0.6 = 60%). Sin umbral fijo: el backend devuelve
 * los `limit` mejores, porque sin membresías el techo del catálogo ronda el 60%.
 */
export function getDeals(limit = 8, memberships, section) {
  const params = new URLSearchParams({ limit: String(limit) });
  appendMemberships(params, memberships);
  // Una sección de GET /categories ("Congelados"); sin ella, todo el catálogo.
  if (section) params.set("section", section);
  return apiFetch(`/deals?${params.toString()}`);
}

/**
 * Un carrito de ejemplo armado por el backend con el catálogo de hoy.
 *
 * Los ids NO se hardcodean acá: el pruning borra productos discontinuados todas
 * las noches, así que una lista fija en el frontend se pudre sola y sin aviso.
 * El backend elige (ver `/demo-cart` en src/api.py) y devuelve `{unified_id,
 * quantity, name}`, que es exactamente la forma que el carrito guarda.
 */
export function getDemoCart() {
  return apiFetch("/demo-cart");
}
