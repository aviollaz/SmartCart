import { createContext, useCallback, useContext, useMemo } from "react";
import { useLocalStorage } from "../hooks/useLocalStorage";
import {
  EMPTY_HISTORY,
  HISTORY_STORAGE_KEY,
  normalizeHistory,
  recordPurchase as recordPurchaseInHistory,
  selectHabituales,
  selectRecentCarts,
} from "../utils/purchaseHistory";

const HistoryContext = createContext(null);

/**
 * Historial de carritos optimizados, persistido en localStorage.
 *
 * Es 100% del lado del cliente por construcción, no por simplificación: el
 * backend no tiene autenticación ni tabla por usuario, y lo único parecido a una
 * identidad es el `anon_user_id` del perfil, que viaja al analyzer y no vuelve.
 * Consecuencia honesta: borrar los datos del sitio pierde el historial.
 *
 * OJO: este provider NO debe llamar a useCart(). Es legal (está adentro), pero
 * acoplaría la escritura al carrito VIVO, y el carrito puede haber cambiado entre
 * que salió el request de /optimize y volvió la respuesta. El snapshot lo pasa el
 * llamador justamente por eso.
 */
export function HistoryProvider({ children }) {
  const [stored, setStored] = useLocalStorage(HISTORY_STORAGE_KEY, EMPTY_HISTORY);

  const entries = useMemo(() => normalizeHistory(stored).entries, [stored]);
  const habituales = useMemo(() => selectHabituales({ entries }), [entries]);
  const recentCarts = useMemo(() => selectRecentCarts({ entries }), [entries]);

  // El `at` lo estampa el contexto y no el llamador: así ningún caller puede
  // discrepar sobre el reloj y la ventana de sesión se decide en un solo lugar.
  const recordPurchase = useCallback(
    ({ items, total, stores }) =>
      setStored((prev) => recordPurchaseInHistory(prev, { items, total, stores, at: Date.now() })),
    [setStored]
  );

  const clearHistory = useCallback(() => setStored(EMPTY_HISTORY), [setStored]);

  const value = useMemo(
    () => ({ entries, habituales, recentCarts, recordPurchase, clearHistory }),
    [entries, habituales, recentCarts, recordPurchase, clearHistory]
  );

  return <HistoryContext.Provider value={value}>{children}</HistoryContext.Provider>;
}

export function useHistory() {
  const ctx = useContext(HistoryContext);
  if (!ctx) throw new Error("useHistory debe usarse dentro de un HistoryProvider");
  return ctx;
}
