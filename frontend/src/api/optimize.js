import { apiFetch, ApiError } from "./client";

/**
 * Llama a POST /optimize. El backend devuelve HTTP 400 cuando el carrito no
 * alcanza los mínimos de compra requeridos por las tiendas (caso esperado,
 * no un error de red) — se modela como {ok:false, detail} en vez de lanzar,
 * para que la UI lo muestre inline (igual que el st.warning de Streamlit).
 */
export async function optimizeCart({ cart, userMemberships, userCards, deliveryCosts, coordinates }) {
  try {
    const data = await apiFetch("/optimize", {
      method: "POST",
      body: JSON.stringify({
        cart,
        user_memberships: userMemberships,
        user_cards: userCards,
        delivery_costs: deliveryCosts,
        // Con coordenadas el backend consulta la cobertura y el envío real de
        // Coto; sin ellas cae a los costos por zona de deliveryCosts.
        lat: coordinates?.lat ?? null,
        lng: coordinates?.lng ?? null,
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
