import { apiFetch } from "./client";

/**
 * Pide el costo neto y el precio unitario aplanado de cada producto para una
 * cantidad dada, por tienda. La matemática de promociones vive en Python
 * (src/flattener.py) y no se replica acá a propósito: es la misma función que
 * usa el optimizador, así que una copia en JS se desincronizaría apenas
 * apareciera un tipo de promo nuevo.
 *
 * @param {{unified_id: string, quantity: number}[]} items
 * @returns {Promise<Object>} { [unified_id]: { [store_id]: { total_cost,
 *   effective_unit_price, applied_promo_id, promo_description } } }
 *   Los productos sin oferta en stock no aparecen como clave.
 */
export function previewPrices(items, userMemberships = []) {
  return apiFetch("/price-preview", {
    method: "POST",
    body: JSON.stringify({ items, user_memberships: userMemberships }),
  });
}
