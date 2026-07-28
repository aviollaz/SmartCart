import { apiFetch } from "./client";

/**
 * Consulta si Coto entrega en una coordenada (GET /logistics/coto/coverage).
 *
 * Se usa en el onboarding para avisar en el momento, en vez de que el usuario
 * lo descubra recién al optimizar un carrito ya armado.
 *
 * Ante cualquier fallo devuelve {ok:false} en lugar de lanzar: la política del
 * backend es fail-open, así que "no pudimos preguntar" nunca debe mostrarse
 * como "Coto no llega" — sólo un veredicto afirmativo cuenta.
 */
export async function checkCotoCoverage({ lat, lng }) {
  try {
    return await apiFetch(`/logistics/coto/coverage?lat=${lat}&lng=${lng}`);
  } catch {
    return { ok: false, covered: null, sucursal: null, mensaje: null };
  }
}
