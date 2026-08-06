import { createContext, useCallback, useContext, useMemo } from "react";
import { useLocalStorage } from "../hooks/useLocalStorage";
import { applySwaps } from "../utils/cartOperations";

const CartContext = createContext(null);

const STORAGE_KEY = "smartcart_cart_v1";

// { [unified_id]: { name, quantity } } — sin precio (ver decisión de paridad
// del plan: el carrito no muestra subtotal antes de optimizar).
export function CartProvider({ children }) {
  const [items, setItems] = useLocalStorage(STORAGE_KEY, {});

  // `quantity` tiene default 1 para no romper a los llamadores que agregan de a uno.
  const addItem = useCallback(
    (unifiedId, name, quantity = 1) => {
      setItems((prev) => {
        const existing = prev[unifiedId];
        return {
          ...prev,
          [unifiedId]: { name, quantity: existing ? existing.quantity + quantity : quantity },
        };
      });
    },
    [setItems]
  );

  const incrementItem = useCallback(
    (unifiedId) => {
      setItems((prev) => {
        if (!prev[unifiedId]) return prev;
        return {
          ...prev,
          [unifiedId]: { ...prev[unifiedId], quantity: prev[unifiedId].quantity + 1 },
        };
      });
    },
    [setItems]
  );

  const decrementItem = useCallback(
    (unifiedId) => {
      setItems((prev) => {
        if (!prev[unifiedId]) return prev;
        const nextQuantity = prev[unifiedId].quantity - 1;
        if (nextQuantity <= 0) {
          const { [unifiedId]: _removed, ...rest } = prev;
          return rest;
        }
        return { ...prev, [unifiedId]: { ...prev[unifiedId], quantity: nextQuantity } };
      });
    },
    [setItems]
  );

  const removeItem = useCallback(
    (unifiedId) => {
      setItems((prev) => {
        const { [unifiedId]: _removed, ...rest } = prev;
        return rest;
      });
    },
    [setItems]
  );

  /**
   * Swap in-place en lote para las recomendaciones del optimizador: cada
   * `{ from, to, name }` conserva la cantidad, porque la sugerencia se calculó
   * justamente para esa cantidad.
   *
   * Es un lote y no N llamadas sueltas porque el cierre de tienda
   * (src/strategic_swaps.py) es todo o nada: su ahorro proyectado sale de
   * simular el carrito con TODOS los reemplazos aplicados y la tienda excluida,
   * así que aplicar una parte deja la tienda abierta y el número deja de
   * corresponder a nada.
   *
   * La forma `{ from, to, name }` es a propósito genérica: el mapeo desde los
   * nombres de campo de cada endpoint se hace en el llamador, así el carrito no
   * queda acoplado al payload de ninguna feature en particular.
   */
  const replaceItems = useCallback(
    (swaps) => setItems((prev) => applySwaps(prev, swaps)),
    [setItems]
  );

  const replaceItem = useCallback(
    (oldUnifiedId, newUnifiedId, newName) => {
      replaceItems([{ from: oldUnifiedId, to: newUnifiedId, name: newName }]);
    },
    [replaceItems]
  );

  // Restaura un carrito entero tal cual estaba. Es lo que usa el "deshacer" de
  // las recomendaciones: invertir swap por swap no sirve, porque si el destino
  // ya estaba en el carrito las cantidades se fusionaron y la operación inversa
  // no puede saber cuánto había antes.
  const restoreItems = useCallback((snapshot) => setItems(snapshot || {}), [setItems]);

  const clear = useCallback(() => setItems({}), [setItems]);

  const itemCount = useMemo(
    () => Object.values(items).reduce((sum, item) => sum + item.quantity, 0),
    [items]
  );

  const value = useMemo(
    () => ({
      items,
      addItem,
      incrementItem,
      decrementItem,
      removeItem,
      replaceItem,
      replaceItems,
      restoreItems,
      clear,
      itemCount,
    }),
    [
      items,
      addItem,
      incrementItem,
      decrementItem,
      removeItem,
      replaceItem,
      replaceItems,
      restoreItems,
      clear,
      itemCount,
    ]
  );

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

export function useCart() {
  const ctx = useContext(CartContext);
  if (!ctx) throw new Error("useCart debe usarse dentro de un CartProvider");
  return ctx;
}
