import { useEffect } from "react";
import { Store, X } from "lucide-react";
import { StoreToggles } from "./StoreToggles";

/**
 * Los supermercados habilitados, desde el botón "Súper" del Header. Mismo
 * contenido que en el carrito: los cambios se aplican al tocarlos, así que
 * "Listo" sólo cierra.
 */
export function StoresModal({ onClose }) {
  useEffect(() => {
    function onKeyDown(event) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={(event) => event.target === event.currentTarget && onClose()}
    >
      <div className="w-full max-w-sm rounded-lg border border-line bg-surface p-6 shadow-lg">
        <div className="mb-4 flex items-center gap-2">
          <Store className="text-brand-accent" size={20} />
          <h2 className="font-display text-lg font-bold text-ink">¿En qué súper comprás?</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar"
            className="ml-auto rounded-md p-1 text-ink-muted hover:bg-surface-muted hover:text-ink"
          >
            <X size={18} />
          </button>
        </div>

        <StoreToggles />

        <button
          type="button"
          onClick={onClose}
          className="mt-5 w-full rounded-md bg-brand-violet-700 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-violet-900"
        >
          Listo
        </button>
      </div>
    </div>
  );
}
