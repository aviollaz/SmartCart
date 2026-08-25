import { useRef, useState } from "react";
import { Trash2 } from "lucide-react";
import { useHistory } from "../../context/HistoryContext";

/**
 * Borrar el historial de compras, con confirmación en dos pasos in-place.
 *
 * Misma forma que ClearCartButton: el propio botón se transforma en la pregunta,
 * sin window.confirm (bloquea el hilo y no se puede estilar) y sin mover el
 * layout de alrededor.
 *
 * Existe porque el historial es lo más parecido a un dato personal que guarda la
 * app: tiene que poder borrarse de un click, sin buscarlo en un menú.
 *
 * No hay borrado por entrada a propósito: es más UI y más estado, y el usuario no
 * puede ver el efecto de lo que estaría editando (el ranking).
 */
export function ClearHistoryButton({ className = "" }) {
  const { entries, clearHistory } = useHistory();
  const [confirming, setConfirming] = useState(false);
  const containerRef = useRef(null);

  if (entries.length === 0) return null;

  const handleBlur = (event) => {
    if (!containerRef.current?.contains(event.relatedTarget)) setConfirming(false);
  };

  if (!confirming) {
    return (
      <button
        type="button"
        onClick={() => setConfirming(true)}
        className={`flex shrink-0 items-center gap-1.5 rounded-md border border-line px-2.5 py-1.5 text-xs font-semibold text-ink-muted hover:border-state-promo hover:text-state-promo ${className}`}
      >
        <Trash2 size={14} />
        Borrar historial
      </button>
    );
  }

  return (
    <div
      ref={containerRef}
      onBlur={handleBlur}
      onKeyDown={(event) => event.key === "Escape" && setConfirming(false)}
      className={`flex shrink-0 flex-wrap items-center gap-2 ${className}`}
    >
      <span className="text-xs text-ink-muted">
        ¿Borrar {entries.length === 1 ? "la única compra guardada" : `las ${entries.length} compras guardadas`}?
      </span>
      <button
        type="button"
        autoFocus
        onClick={() => {
          clearHistory();
          setConfirming(false);
        }}
        className="rounded-md bg-state-promo px-2.5 py-1.5 text-xs font-semibold text-white hover:opacity-90"
      >
        Sí, borrar
      </button>
      <button
        type="button"
        onClick={() => setConfirming(false)}
        className="rounded-md border border-line px-2.5 py-1.5 text-xs font-semibold text-ink-muted hover:text-ink"
      >
        Cancelar
      </button>
    </div>
  );
}
