import { useRef, useState } from "react";
import { Trash2 } from "lucide-react";
import { useCart } from "../../context/CartContext";

/**
 * Vaciar el carrito, con confirmación en dos pasos in-place.
 *
 * La confirmación es inline y no un window.confirm porque el diálogo nativo
 * bloquea el hilo y no se puede estilar; acá el propio botón se transforma en la
 * pregunta, sin mover el layout de alrededor.
 *
 * Se conecta solo al contexto (cuenta los ítems y llama a clear), así los dos
 * lugares que lo montan — la página del carrito y el drawer — no cablean nada.
 */
export function ClearCartButton({ className = "" }) {
  const { itemCount, clear } = useCart();
  const [confirming, setConfirming] = useState(false);
  const containerRef = useRef(null);

  if (itemCount === 0) return null;

  // Salir del grupo de botones cancela: dejar la pregunta colgada mientras el
  // usuario sigue en otra parte de la página es una trampa esperando un click.
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
        Vaciar carrito
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
        ¿Vaciar {itemCount === 1 ? "el único producto" : `los ${itemCount} productos`}?
      </span>
      <button
        type="button"
        autoFocus
        onClick={() => {
          clear();
          setConfirming(false);
        }}
        className="rounded-md bg-state-promo px-2.5 py-1.5 text-xs font-semibold text-white hover:opacity-90"
      >
        Sí, vaciar
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
