import { createContext, useContext, useMemo } from "react";
import { useCart } from "./CartContext";
import { useCartProducts } from "../hooks/useCartProducts";
import { resolveDisplayPrice } from "../utils/formatters";

const CartProductsContext = createContext(null);

/**
 * Resuelve los productos del carrito UNA sola vez y lo comparte entre
 * `CartPage` y `CartDrawer`. `useCartProducts` no tiene caché — cada
 * componente que lo llama dispara su propio `POST /products/by-ids` — así que
 * si cada consumidor lo llamara por su cuenta, en `/carrito` (donde el drawer
 * y la página pueden coexistir) el mismo carrito dispararía el pedido dos
 * veces por cada cambio.
 *
 * Vive afuera de `CartContext` porque `useCartProducts` depende de
 * `useProfile()` (para recortar por cobertura), y en `main.jsx` `CartProvider`
 * envuelve a `ProfileProvider` — más afuera no puede leer un contexto que
 * todavía no existe en el árbol.
 */
export function CartProductsProvider({ children }) {
  const { items } = useCart();
  const cartProducts = useCartProducts(items);

  // Piso del carrito, no el total. Suma el precio más barato de cada producto
  // por separado —posiblemente de tres tiendas distintas—, sin envíos, sin
  // descuentos bancarios y sin las promos por cantidad, que /optimize sí
  // aplica. Es `null` mientras no haya precio para TODAS las líneas: un
  // subtotal calculado sobre la mitad del carrito es peor que no mostrarlo.
  const subtotalEstimado = useMemo(() => {
    const entries = Object.entries(items);
    if (entries.length === 0) return null;

    const lineasConPrecio = entries
      .map(([unifiedId, item]) => {
        const producto = cartProducts[unifiedId];
        const unitario = producto ? resolveDisplayPrice(producto) : null;
        return typeof unitario === "number" ? unitario * item.quantity : null;
      })
      .filter((total) => total !== null);

    if (lineasConPrecio.length !== entries.length) return null;
    return lineasConPrecio.reduce((suma, total) => suma + total, 0);
  }, [items, cartProducts]);

  const value = useMemo(
    () => ({ cartProducts, subtotalEstimado }),
    [cartProducts, subtotalEstimado]
  );

  return <CartProductsContext.Provider value={value}>{children}</CartProductsContext.Provider>;
}

export function useCartProductsContext() {
  const ctx = useContext(CartProductsContext);
  if (!ctx) throw new Error("useCartProductsContext debe usarse dentro de un CartProductsProvider");
  return ctx;
}
