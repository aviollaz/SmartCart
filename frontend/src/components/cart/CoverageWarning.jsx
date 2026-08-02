import { AlertTriangle } from "lucide-react";
import { useUnavailableCartItems } from "../../hooks/useUnavailableCartItems";
import { storeLabel } from "../../utils/formatters";

/**
 * Avisa que hay productos del carrito que solo vende una tienda que no entrega
 * en la dirección elegida.
 *
 * Es solo un aviso: no borra nada, no deshabilita el optimizador y no toca las
 * cantidades. Si el usuario cambió de dirección por error, deshacer el cambio
 * tiene que devolverle el carrito intacto.
 */
export function CoverageWarning({ className = "" }) {
  const { items, unavailableStores } = useUnavailableCartItems();
  if (items.length === 0) return null;

  const stores = unavailableStores.map(storeLabel).join(" y ");

  return (
    <div
      className={`flex items-start gap-2 rounded-lg border border-state-warning/40 bg-state-warning/10 p-4 ${className}`}
    >
      <AlertTriangle size={18} className="mt-0.5 shrink-0 text-state-warning" />
      <div className="text-sm">
        <p className="font-semibold text-ink">
          {items.length === 1
            ? "Un producto de tu carrito no llega a tu dirección"
            : `${items.length} productos de tu carrito no llegan a tu dirección`}
        </p>
        <p className="mt-1 text-ink-muted">
          {items.length === 1 ? "Solo lo vende" : "Solo los vende"} {stores}, que no entrega ahí.
          Los dejamos en el carrito: si cambiás la dirección, vuelven a estar disponibles.
        </p>
        <ul className="mt-2 space-y-0.5 text-xs text-ink-muted">
          {items.map((item) => (
            <li key={item.unified_id}>· {item.name || item.unified_id}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}
