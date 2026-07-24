import { apiFetch, ApiError } from "./client";

/**
 * Llama a POST /optimize. El backend devuelve HTTP 400 cuando el carrito no
 * alcanza los mínimos de compra requeridos por las tiendas (caso esperado,
 * no un error de red) — se modela como {ok:false, detail} en vez de lanzar,
 * para que la UI lo muestre inline (igual que el st.warning de Streamlit).
 */
export async function optimizeCart({ cart, userMemberships, userCards, deliveryCosts }) {
  try {
    const data = await apiFetch("/optimize", {
      method: "POST",
      body: JSON.stringify({
        cart,
        user_memberships: userMemberships,
        user_cards: userCards,
        delivery_costs: deliveryCosts,
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
