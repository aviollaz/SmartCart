import { apiFetch, ApiError } from "./client";

/**
 * Llama a POST /optimize. El backend devuelve HTTP 400 cuando el carrito no
 * alcanza los mínimos de compra requeridos por las tiendas (caso esperado,
 * no un error de red) — se modela como {ok:false, detail} en vez de lanzar,
 * para que la UI lo muestre inline (igual que el st.warning de Streamlit).
 */
export async function optimizeCart({
  cart,
  userMemberships,
  userCards,
  deliveryCosts,
  coordinates,
  anonUserId,
  zone,
}) {
  try {
    const data = await apiFetch("/optimize", {
      method: "POST",
      body: JSON.stringify({
        cart,
        user_memberships: userMemberships,
        user_cards: userCards,
        // Costos por zona, derivados de la dirección (ya no de un dropdown).
        // Tienen que viajar SIEMPRE y con las tres tiendas: src/optimizer.py
        // indexa delivery_costs[store] para cada tienda con mínimo de compra
        // —un faltante es KeyError— y src/api.py arma los baselines con sus
        // claves. Es la única fuente del envío de Día y de Carrefour, que no
        // tienen lookup online; para Coto es el fallback.
        delivery_costs: deliveryCosts,
        // Con coordenadas el backend consulta la cobertura y la tarifa real de
        // Coto, y pisa su costo acá arriba. Sólo afecta a Coto: no hay
        // equivalente para Día ni para Carrefour.
        lat: coordinates?.lat ?? null,
        lng: coordinates?.lng ?? null,
        // Los dos que siguen no los usa el optimizador: son para el evento que
        // el backend le manda a SmartCart Performance Analyzer (src/analytics.py).
        // `anon_user_id` identifica el navegador (KPI de usuarios únicos) y la
        // zona permite cortar los KPIs geográficamente — de `delivery_costs` no
        // se puede recuperar la etiqueta. Los dos son nullables del otro lado.
        anon_user_id: anonUserId ?? null,
        zone: zone ?? null,
      }),
    });
    return { ok: true, data };
  } catch (err) {
    if (err instanceof ApiError && err.status === 400) {
      return { ok: false, detail: err.detail || "El carrito no alcanza los mínimos requeridos." };
    }
    throw err;
  }
}
