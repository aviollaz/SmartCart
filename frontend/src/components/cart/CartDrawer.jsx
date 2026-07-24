import { Link } from "react-router-dom";
import { X } from "lucide-react";
import { useCart } from "../../context/CartContext";
import { CartLineItem } from "./CartLineItem";

export function CartDrawer({ open, onClose }) {
  const { items, incrementItem, decrementItem, removeItem } = useCart();
  const entries = Object.entries(items);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40 flex justify-end" role="dialog" aria-modal="true">
      <button type="button" aria-label="Cerrar carrito" onClick={onClose} className="absolute inset-0 bg-ink/40" />
      <div className="relative z-10 flex h-full w-full max-w-sm flex-col bg-surface p-5 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-display text-lg font-bold text-ink">Tu carrito</h2>
          <button type="button" onClick={onClose} aria-label="Cerrar" className="text-ink-muted hover:text-ink">
            <X size={20} />
          </button>
        </div>

        {entries.length === 0 ? (
          <p className="text-sm text-ink-muted">
            Tu carrito está vacío. Buscá productos y agregalos desde la grilla.
          </p>
        ) : (
          <ul className="flex-1 divide-y divide-line overflow-y-auto">
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

        <Link
          to="/carrito"
          onClick={onClose}
          className="mt-4 block rounded-md bg-brand-accent px-4 py-2.5 text-center text-sm font-semibold text-white hover:bg-brand-accent-dark"
        >
          Ir a mi carrito
        </Link>
      </div>
    </div>
  );
}
