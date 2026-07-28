import { MapPin } from "lucide-react";
import { useProfile } from "../../context/ProfileContext";

/**
 * Muestra la dirección elegida en el onboarding y permite cambiarla.
 *
 * "Cambiar" limpia la ubicación del perfil, lo que vuelve a disparar el
 * LocationModal desde App.jsx — así hay un único lugar que sabe geocodificar.
 */
export function AddressField() {
  const { location, clearLocation } = useProfile();

  const skipped = !location || location.skipped;

  return (
    <div className="text-sm text-ink">
      <span className="mb-2 block font-semibold">Dirección de entrega</span>
      <div className="flex items-start justify-between gap-3 rounded-md border border-line bg-surface px-3 py-2">
        <div className="flex min-w-0 items-start gap-2">
          <MapPin size={16} className="mt-0.5 shrink-0 text-brand-accent" />
          <span className={skipped ? "text-ink-muted" : "text-ink"}>
            {skipped ? "Sin dirección — usamos costos estimados por zona" : location.displayName}
          </span>
        </div>
        <button
          type="button"
          onClick={clearLocation}
          className="shrink-0 text-xs font-semibold text-brand-accent underline"
        >
          {skipped ? "Agregar" : "Cambiar"}
        </button>
      </div>
    </div>
  );
}
