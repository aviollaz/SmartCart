import { createContext, useCallback, useContext, useMemo } from "react";
import { useLocalStorage } from "../hooks/useLocalStorage";

const CartContext = createContext(null);

const STORAGE_KEY = "smartcart_cart_v1";

// { [unified_id]: { name, quantity } } — sin precio (ver decisión de paridad
// del plan: el carrito no muestra subtotal antes de optimizar).
export function CartProvider({ children }) {
  const [items, setItems] = useLocalStorage(STORAGE_KEY, {});

  const addItem = useCallback(
    (unifiedId, name) => {
      setItems((prev) => {
        const existing = prev[unifiedId];
        return {
          ...prev,
          [unifiedId]: { name, quantity: existing ? existing.quantity + 1 : 1 },
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

  const clear = useCallback(() => setItems({}), [setItems]);

  const itemCount = useMemo(
    () => Object.values(items).reduce((sum, item) => sum + item.quantity, 0),
    [items]
  );

  const value = useMemo(
    () => ({ items, addItem, incrementItem, decrementItem, removeItem, clear, itemCount }),
    [items, addItem, incrementItem, decrementItem, removeItem, clear, itemCount]
  );

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

export function useCart() {
  const ctx = useContext(CartContext);
  if (!ctx) throw new Error("useCart debe usarse dentro de un CartProvider");
  return ctx;
}
