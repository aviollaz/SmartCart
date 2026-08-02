import { useCallback, useEffect, useRef, useState } from "react";
import { useCart } from "../context/CartContext";
import { useProfile } from "../context/ProfileContext";
import { optimizeCart } from "../api/optimize";
import { CartLineItem } from "../components/cart/CartLineItem";
import { CoverageWarning } from "../components/cart/CoverageWarning";
import { ProfileDrawer } from "../components/profile/ProfileDrawer";
import { OptimizeButton } from "../components/optimize/OptimizeButton";
import { InfeasibleNotice } from "../components/optimize/InfeasibleNotice";
import { OptimizeResultsPanel } from "../components/optimize/OptimizeResultsPanel";

export function CartPage({ onOpenLocation }) {
  const { items, incrementItem, decrementItem, removeItem, replaceItem } = useCart();
  const { cards, memberships, deliveryCosts, coordinates, setStoreCoverage } = useProfile();
  const entries = Object.entries(items);

  const [optimizeStatus, setOptimizeStatus] = useState("idle"); // idle | loading | success | infeasible | error
  const [optimizeResult, setOptimizeResult] = useState(null);
  const [infeasibleDetail, setInfeasibleDetail] = useState(null);

  // Se levanta al aceptar una sugerencia para que el efecto de abajo distinga
  // "el carrito cambió por un swap, hay que recalcular" de "el usuario tocó una
  // cantidad", que no debería disparar una optimización sola.
  const reoptimizeRef = useRef(false);

  const runOptimize = useCallback(async () => {
    setOptimizeStatus("loading");
    const cartPayload = Object.entries(items).map(([unifiedId, item]) => ({
      unified_id: unifiedId,
      quantity: item.quantity,
    }));

    try {
      const response = await optimizeCart({
        cart: cartPayload,
        userMemberships: memberships,
        userCards: cards,
        deliveryCosts,
        coordinates,
      });

      if (response.ok) {
        setOptimizeResult(response.data);
        setOptimizeStatus("success");

        // El optimizador vuelve a consultar la cobertura con cada corrida, así
        // que su veredicto es más fresco que el guardado en el onboarding. Solo
        // se persiste un "no entrega" afirmativo: la respuesta sin coordenadas
        // trae covered:true por fail-open, y guardarlo pisaría un "no" real.
        const covered = response.data.logistics?.coto?.covered;
        if (covered === false) {
          setStoreCoverage("coto_online", {
            covered: false,
            message: response.data.logistics.coto.message,
          });
        }
      } else {
        setInfeasibleDetail(response.detail);
        setOptimizeStatus("infeasible");
      }
    } catch {
      // Sin este catch, cualquier fallo que no sea el 400 de "carrito inviable"
      // dejaba el estado clavado en "loading" y el botón deshabilitado para siempre.
      setOptimizeResult(null);
      setOptimizeStatus("error");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, memberships, cards, deliveryCosts, coordinates]);

  useEffect(() => {
    if (reoptimizeRef.current) {
      reoptimizeRef.current = false;
      runOptimize();
      return;
    }
    // El resultado describe un carrito que ya no existe: mostrarlo sería mentir.
    setOptimizeStatus((prev) => (prev === "success" || prev === "infeasible" ? "idle" : prev));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items]);

  const handleAcceptSuggestion = useCallback(
    (originalUid, alternative) => {
      reoptimizeRef.current = true;
      replaceItem(originalUid, alternative.suggested_uid, alternative.suggested_product);
    },
    [replaceItem]
  );

  return (
    <div className="mx-auto w-full max-w-4xl px-4 py-6">
      <h1 className="mb-6 font-display text-xl font-bold text-ink">Mi carrito</h1>

      <div className="flex flex-col gap-6">
        <CoverageWarning />

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

        <ProfileDrawer onOpenLocation={onOpenLocation} />

        <OptimizeButton onClick={runOptimize} disabled={entries.length === 0} loading={optimizeStatus === "loading"} />

        {optimizeStatus === "infeasible" && <InfeasibleNotice detail={infeasibleDetail} />}
        {optimizeStatus === "error" && (
          <p className="text-sm text-state-warning">
            No pudimos calcular la optimización. Probá de nuevo en un momento.
          </p>
        )}
        {optimizeStatus === "success" && optimizeResult && (
          <OptimizeResultsPanel result={optimizeResult} onAcceptSuggestion={handleAcceptSuggestion} />
        )}
      </div>
    </div>
  );
}
