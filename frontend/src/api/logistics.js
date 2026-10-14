import { apiFetch } from "./client";

/**
 * Consulta si una tienda ("coto", "dia" o "carrefour") entrega en una coordenada
 * (GET /logistics/{store}/coverage).
 *
 * Se usa en el onboarding para avisar en el momento, en vez de que el usuario
 * lo descubra recién al optimizar un carrito ya armado.
 *
 * Ante cualquier fallo devuelve {ok:false} en lugar de lanzar: la política del
 * backend es fail-open, así que "no pudimos preguntar" nunca debe mostrarse
 * como "no llega" — sólo un veredicto afirmativo cuenta.
 */
export async function checkCoverage(store, { lat, lng }) {
  try {
    return await apiFetch(`/logistics/${store}/coverage?lat=${lat}&lng=${lng}`);
  } catch {
    return { ok: false, covered: null, sucursal: null, mensaje: null };
  }
}
