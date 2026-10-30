import { Minus, Plus } from "lucide-react";

// Medidas fijas: alto igual al botón "Agregar" que reemplaza (cambiar uno por
// otro no mueve la card) y número de ancho fijo (pasar de 9 a 10 no corre los
// botones de debajo del cursor).
export function QuantityStepper({ quantity, onIncrement, onDecrement, size = "md" }) {
  const box = size === "sm" ? "h-8 px-1.5" : "h-9 px-2";
  return (
    <div className={`flex shrink-0 items-center gap-2 rounded-md bg-brand-violet-700 text-white ${box}`}>
      <button
        type="button"
        onClick={onDecrement}
        aria-label="Quitar uno"
        className="flex items-center justify-center rounded hover:bg-brand-violet-900"
      >
        <Minus size={14} />
      </button>
      <span className="w-6 text-center text-sm font-semibold tabular-nums">{quantity}</span>
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
