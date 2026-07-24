import { X } from "lucide-react";
import { QuantityStepper } from "../plp/QuantityStepper";

export function CartLineItem({ name, quantity, onIncrement, onDecrement, onRemove }) {
  return (
    <li className="flex items-center gap-3 py-3">
      <p className="flex-1 text-sm text-ink">{name}</p>
      <QuantityStepper quantity={quantity} onIncrement={onIncrement} onDecrement={onDecrement} size="sm" />
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Quitar ${name} del carrito`}
        className="text-ink-muted hover:text-state-promo"
      >
        <X size={16} />
      </button>
    </li>
  );
}
