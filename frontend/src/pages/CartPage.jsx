import { useState } from "react";
import { useCart } from "../context/CartContext";
import { useProfile } from "../context/ProfileContext";
import { optimizeCart } from "../api/optimize";
import { CartLineItem } from "../components/cart/CartLineItem";
import { ProfileDrawer } from "../components/profile/ProfileDrawer";
import { OptimizeButton } from "../components/optimize/OptimizeButton";
import { InfeasibleNotice } from "../components/optimize/InfeasibleNotice";
import { OptimizeResultsPanel } from "../components/optimize/OptimizeResultsPanel";

export function CartPage() {
  const { items, incrementItem, decrementItem, removeItem } = useCart();
  const { cards, memberships, deliveryCosts } = useProfile();
  const entries = Object.entries(items);

  const [optimizeStatus, setOptimizeStatus] = useState("idle"); // idle | loading | success | infeasible
  const [optimizeResult, setOptimizeResult] = useState(null);
  const [infeasibleDetail, setInfeasibleDetail] = useState(null);

  async function handleOptimize() {
    setOptimizeStatus("loading");
    const cartPayload = entries.map(([unifiedId, item]) => ({
      unified_id: unifiedId,
      quantity: item.quantity,
    }));

    const response = await optimizeCart({
      cart: cartPayload,
      userMemberships: memberships,
      userCards: cards,
      deliveryCosts,
    });

    if (response.ok) {
      setOptimizeResult(response.data);
      setOptimizeStatus("success");
    } else {
      setInfeasibleDetail(response.detail);
      setOptimizeStatus("infeasible");
    }
  }

  return (
    <div className="mx-auto w-full max-w-4xl px-4 py-6">
      <h1 className="mb-6 font-display text-xl font-bold text-ink">Mi carrito</h1>

      <div className="flex flex-col gap-6">
        <section className="rounded-lg border border-line bg-surface p-5">
          <h2 className="mb-2 font-display text-lg font-bold text-ink">Productos seleccionados</h2>
          {entries.length === 0 ? (
            <p className="text-sm text-ink-muted">
              Tu carrito está vacío. Buscá productos en la página principal.
            </p>
          ) : (
            <ul className="divide-y divide-line">
              {entries.map(([unifiedId, item]) => (
                <CartLineItem
                  key={unifiedId}
                  name={item.name}
                  quantity={item.quantity}
                  onIncrement={() => incrementItem(unifiedId)}
                  onDecrement={() => decrementItem(unifiedId)}
                  onRemove={() => removeItem(unifiedId)}
                />
              ))}
            </ul>
          )}
        </section>

        <ProfileDrawer />

        <OptimizeButton onClick={handleOptimize} disabled={entries.length === 0} loading={optimizeStatus === "loading"} />

        {optimizeStatus === "infeasible" && <InfeasibleNotice detail={infeasibleDetail} />}
        {optimizeStatus === "success" && optimizeResult && <OptimizeResultsPanel result={optimizeResult} />}
      </div>
    </div>
  );
}
