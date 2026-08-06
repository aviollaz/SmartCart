import { RotateCcw, X } from "lucide-react";

/**
 * Barra de "deshacer" para un cambio que la app le hizo al carrito al aceptar
 * una recomendación.
 *
 * Es genérica a propósito (recibe el texto ya armado): la usan tanto el cierre
 * de tienda como los Smart Replacements, y la única diferencia entre los dos es
 * cuántos productos cambiaron.
 */
export function UndoBar({ message, onUndo, onDismiss }) {
  if (!message) return null;

  return (
    <div className="flex items-center gap-3 rounded-lg border border-state-success bg-surface p-3">
      <p className="flex-1 text-sm text-ink">{message}</p>
      <button
        type="button"
        onClick={onUndo}
        className="flex shrink-0 items-center gap-1.5 rounded-md border border-line px-2.5 py-1.5 text-xs font-semibold text-ink hover:border-brand-violet-500 hover:text-brand-violet-700"
      >
        <RotateCcw size={14} />
        Deshacer
      </button>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Ocultar aviso"
        className="shrink-0 text-ink-muted hover:text-ink"
      >
        <X size={16} />
      </button>
    </div>
  );
}
