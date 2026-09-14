import { useCallback, useEffect, useRef, useState } from "react";
import { useCart } from "../context/CartContext";
import { useProfile } from "../context/ProfileContext";
import { useHistory } from "../context/HistoryContext";
import { optimizeCart } from "../api/optimize";
import { storeName } from "../utils/formatters";
import { useCartProductsContext } from "../context/CartProductsContext";
import { CartLineItem } from "../components/cart/CartLineItem";
import { EstimatedSubtotal } from "../components/cart/EstimatedSubtotal";
import { ClearCartButton } from "../components/cart/ClearCartButton";
import { CoverageWarning } from "../components/cart/CoverageWarning";
import { UndoBar } from "../components/cart/UndoBar";
import { ProfileDrawer } from "../components/profile/ProfileDrawer";
import { OptimizeButton } from "../components/optimize/OptimizeButton";
import { InfeasibleNotice } from "../components/optimize/InfeasibleNotice";
import { OptimizeResultsPanel } from "../components/optimize/OptimizeResultsPanel";
import { PurchaseHistorySection } from "../components/history/PurchaseHistorySection";

export function CartPage({ onOpenLocation }) {
  const { items, incrementItem, decrementItem, removeItem, replaceItem, replaceItems, restoreItems } =
    useCart();
  const { cards, memberships, deliveryCosts, coordinates, location, anon_user_id, setStoreCoverage } =
    useProfile();
  // Sólo el lado de escritura: `entries` de acá abajo ya nombra a los ítems del
  // carrito, y PurchaseHistorySection hace su propio useHistory() para leer.
  const { recordPurchase } = useHistory();
  const entries = Object.entries(items);

  // Imagen y precio de cada línea, y el subtotal estimado. Compartido con
  // CartDrawer vía CartProductsContext para no duplicar el pedido a
  // /products/by-ids en cada cambio de carrito (ver ese contexto).
  const { cartProducts, subtotalEstimado } = useCartProductsContext();

  const [optimizeStatus, setOptimizeStatus] = useState("idle"); // idle | loading | success | infeasible | error
  const [optimizeResult, setOptimizeResult] = useState(null);
  const [infeasibleDetail, setInfeasibleDetail] = useState(null);

  // Se levanta al aceptar una sugerencia para que el efecto de abajo distinga
  // "el carrito cambió por un swap, hay que recalcular" de "el usuario tocó una
  // cantidad", que no debería disparar una optimización sola.
  const reoptimizeRef = useRef(false);

  // Carrito previo a la última recomendación aceptada: { items, message }.
  // Se guarda el objeto entero en vez de invertir los swaps uno por uno porque
  // si el reemplazo ya estaba en el carrito las cantidades se fusionaron, y la
  // operación inversa no puede reconstruir cuánto había de cada uno.
  const [undoSnapshot, setUndoSnapshot] = useState(null);

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
        anonUserId: anon_user_id,
        zone: location?.zone,
      });

      if (response.ok) {
        setOptimizeResult(response.data);
        setOptimizeStatus("success");

        // `items` es el cierre de este useCallback: el carrito TAL COMO se
        // optimizó, no lo que haya pasado a ser mientras el request estaba en
        // vuelo. Es la misma fuente de la que salió cartPayload, así que el
        // historial no puede describir un carrito que nunca se cotizó.
        //
        // Se graba también en las re-optimizaciones que dispara un swap: grabar
        // sólo las manuales perdería el carrito final —el que incluye los
        // reemplazos aceptados—, que es justamente el que importa. Las corridas
        // repetidas las absorbe la ventana de sesión de purchaseHistory.js.
        //
        // El carrito inviable (400) NO se graba: no es una compra, y ensuciaría
        // el ranking con carritos que el usuario nunca pudo comprar.
        recordPurchase({
          items,
          total: response.data.total_spent_net,
          stores: Object.keys(response.data.split || {}),
        });

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
  }, [items, memberships, cards, deliveryCosts, coordinates, anon_user_id, location, recordPurchase]);

  useEffect(() => {
    if (reoptimizeRef.current) {
      reoptimizeRef.current = false;
      runOptimize();
      return;
    }
    // Llegar acá es que el cambio lo hizo el usuario a mano, no una
    // recomendación: el snapshot describe un carrito anterior a ese cambio y
    // restaurarlo le borraría lo que acaba de hacer.
    setUndoSnapshot(null);
    // El resultado describe un carrito que ya no existe: mostrarlo sería mentir.
    setOptimizeStatus((prev) => (prev === "success" || prev === "infeasible" ? "idle" : prev));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items]);

  const handleAcceptSuggestion = useCallback(
    (originalUid, alternative) => {
      setUndoSnapshot({ items, message: `Cambiamos ${alternative.suggested_product} en tu carrito.` });
      reoptimizeRef.current = true;
      replaceItem(originalUid, alternative.suggested_uid, alternative.suggested_product);
    },
    [items, replaceItem]
  );

  // Cierre de tienda: los reemplazos van todos juntos porque el ahorro
  // proyectado sale de simular el carrito completo con la tienda excluida (ver
  // src/strategic_swaps.py). Un lote, una sola re-optimización.
  const handleApplyStrategicSwap = useCallback(
    (suggestion) => {
      const count = suggestion.swaps.length;
      setUndoSnapshot({
        items,
        message: `Cambiamos ${count} producto${count === 1 ? "" : "s"} para sacar ${storeName(
          suggestion.closed_store
        )} del pedido.`,
      });
      reoptimizeRef.current = true;
      replaceItems(
        suggestion.swaps.map((swap) => ({
          from: swap.original_uid,
          to: swap.replacement_uid,
          name: swap.replacement_name,
        }))
      );
    },
    [items, replaceItems]
  );

  const handleUndo = useCallback(() => {
    if (!undoSnapshot) return;
    reoptimizeRef.current = true;
    restoreItems(undoSnapshot.items);
    setUndoSnapshot(null);
  }, [undoSnapshot, restoreItems]);

  return (
    <div className="mx-auto w-full max-w-4xl px-4 py-6">
      <h1 className="mb-6 font-display text-xl font-bold text-ink">Mi carrito</h1>

      <div className="flex flex-col gap-6">
        <CoverageWarning />

        <section className="rounded-lg border border-line bg-surface p-5">
          <div className="mb-2 flex items-start justify-between gap-3">
            <h2 className="font-display text-lg font-bold text-ink">Productos seleccionados</h2>
            <ClearCartButton />
          </div>
          {entries.length === 0 ? (
            <p className="text-sm text-ink-muted">
              Tu carrito está vacío. Buscá productos en la página principal.
            </p>
          ) : (
            <>
              <ul className="divide-y divide-line">
                {entries.map(([unifiedId, item]) => (
                  <CartLineItem
                    key={unifiedId}
                    name={item.name}
                    quantity={item.quantity}
                    product={cartProducts[unifiedId]}
                    onIncrement={() => incrementItem(unifiedId)}
                    onDecrement={() => decrementItem(unifiedId)}
                    onRemove={() => removeItem(unifiedId)}
                  />
                ))}
              </ul>

              {/* CartContext documenta la decisión contraria ("el carrito no
                  muestra subtotal antes de optimizar"). Se rompe a propósito:
                  una lista de nombres sin un solo precio hace que la pregunta
                  "¿cuánto llevo?" no tenga respuesta en la pantalla donde se
                  hace, y esa pregunta la va a hacer todo el mundo. Etiquetarlo
                  como estimado es más barato que no contestarla. */}
              <EstimatedSubtotal subtotalEstimado={subtotalEstimado} className="mt-3" />
            </>
          )}
        </section>

        {/* Con el carrito vacío, el historial es lo único accionable de la
            pantalla; con productos adentro sería ruido al lado del flujo de
            optimización. */}
        {entries.length === 0 && <PurchaseHistorySection />}

        <ProfileDrawer onOpenLocation={onOpenLocation} />

        <OptimizeButton onClick={runOptimize} disabled={entries.length === 0} loading={optimizeStatus === "loading"} />

        {optimizeStatus === "infeasible" && <InfeasibleNotice detail={infeasibleDetail} />}
        {optimizeStatus === "error" && (
          <p className="text-sm text-state-warning">
            No pudimos calcular la optimización. Probá de nuevo en un momento.
          </p>
        )}
        {/* Vive en la página y no adentro del panel de resultados: el panel se
            desmonta y vuelve con el resultado nuevo en cada recálculo, y el
            deshacer tiene que sobrevivir justo a ese recálculo. */}
        <UndoBar
          message={undoSnapshot?.message}
          onUndo={handleUndo}
          onDismiss={() => setUndoSnapshot(null)}
        />

        {optimizeStatus === "success" && optimizeResult && (
          <OptimizeResultsPanel
            result={optimizeResult}
            onAcceptSuggestion={handleAcceptSuggestion}
            onApplyStrategicSwap={handleApplyStrategicSwap}
          />
        )}
      </div>
    </div>
  );
}
