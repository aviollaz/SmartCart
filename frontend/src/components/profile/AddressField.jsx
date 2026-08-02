import { MapPin } from "lucide-react";
import { useProfile } from "../../context/ProfileContext";

/**
 * Muestra la dirección elegida en el onboarding y permite cambiarla. Desde que
 * se sacó el dropdown "Zona de envío", es el único control de ubicación del
 * perfil.
 *
 * "Cambiar" abre el mismo modal descartable que el chip del Header, en vez de
 * borrar la ubicación: al limpiarla se disparaba el modal BLOQUEANTE del
 * onboarding, así que arrepentirse de tocar el botón dejaba al usuario sin
 * salida y sin la dirección que ya tenía cargada. Sigue habiendo un único lugar
 * que sabe geocodificar.
 */
export function AddressField({ onOpenLocation }) {
  const { location } = useProfile();

  const skipped = !location || location.skipped;

  return (
    <div className="text-sm text-ink">
      <span className="mb-2 block font-semibold">Dirección de entrega</span>
      <div className="flex items-start justify-between gap-3 rounded-md border border-line bg-surface px-3 py-2">
        <div className="flex min-w-0 items-start gap-2">
          <MapPin size={16} className="mt-0.5 shrink-0 text-brand-accent" />
          <div className="min-w-0">
            <span className={skipped ? "text-ink-muted" : "text-ink"}>
              {skipped ? "Sin dirección — usamos costos estimados por zona" : location.displayName}
            </span>
            {/* La zona ya no se elige, se deriva de la dirección: se muestra
                para que una clasificación equivocada sea visible y no algo que
                el usuario descubra recién en el precio final. */}
            {!skipped && (
              <span className="mt-0.5 block text-xs text-ink-muted">
                {location.zone
                  ? `Envío estimado: zona ${location.zone}`
                  : "Fuera de las zonas de envío conocidas — usamos el costo estimado por defecto"}
              </span>
            )}
          </div>
        </div>
        <button
          type="button"
          onClick={onOpenLocation}
          className="shrink-0 text-xs font-semibold text-brand-accent underline"
        >
          {skipped ? "Agregar" : "Cambiar"}
        </button>
      </div>
    </div>
  );
}
