import { Minus, Plus } from "lucide-react";

export function QuantityStepper({ quantity, onIncrement, onDecrement, size = "md" }) {
  const padding = size === "sm" ? "px-1.5 py-1" : "px-2 py-1.5";
  return (
    <div className={`flex items-center gap-2 rounded-md bg-brand-violet-700 text-white ${padding}`}>
      <button
        type="button"
        onClick={onDecrement}
        aria-label="Quitar uno"
        className="flex items-center justify-center rounded hover:bg-brand-violet-900"
      >
        <Minus size={14} />
      </button>
      <span className="min-w-4 text-center text-sm font-semibold tabular-nums">{quantity}</span>
      <button
        type="button"
        onClick={onIncrement}
        aria-label="Agregar uno"
        className="flex items-center justify-center rounded hover:bg-brand-violet-900"
      >
        <Plus size={14} />
      </button>
    </div>
  );
}
