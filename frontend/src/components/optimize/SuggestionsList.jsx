import { formatPrice } from "../../utils/formatters";

// Cada alternativa a la vista, con su botón: el <select> anterior escondía las
// opciones y su ahorro detrás de un click, y la letra chica de abajo describía
// sólo la elegida. El backend ya las manda ordenadas por ahorro, así que la
// primera es la más barata.
function SuggestionRow({ group, onAccept }) {
  const alternatives = group.alternatives || [];
  if (alternatives.length === 0) return null;

  return (
    <li className="flex flex-col gap-2">
      <p className="text-xs text-ink-muted">
        En lugar de <em className="text-ink">{group.original_product}</em> ({group.original_quantity} ×{" "}
        {group.original_size})
      </p>

      <ul className="flex flex-col gap-2">
        {alternatives.map((alt, index) => (
          <li
            key={alt.suggested_uid}
            className="flex items-center gap-3 rounded-md border border-state-success/30 bg-state-success/10 px-3 py-2"
          >
            <div className="min-w-0 flex-1">
              {/* Nombre a dos líneas fijas: los "Cambiar" de la lista quedan a
                  la misma distancia uno de otro. */}
              <p className="line-clamp-2 h-10 text-sm font-medium text-ink" title={alt.suggested_product}>
                {alt.suggested_product}
              </p>
              <p className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-ink-muted">
                <span>
                  {alt.suggested_quantity} × {alt.suggested_size}
                </span>
                <span className="font-semibold text-state-success">Ahorrás {formatPrice(alt.savings)}</span>
                {index === 0 && (
                  <span className="rounded-full bg-state-success px-2 py-0.5 text-[11px] font-semibold text-white">
                    Más barato
                  </span>
                )}
              </p>
            </div>
            <button
              type="button"
              onClick={() => onAccept(group.original_uid, alt)}
              className="shrink-0 rounded-md bg-brand-accent px-3 py-1.5 text-sm font-semibold text-white hover:bg-brand-accent-dark"
            >
              Cambiar
            </button>
          </li>
        ))}
      </ul>
    </li>
  );
}

// Vive adentro del desplegable "Más opciones", que ya pone la caja y el
// título: acá va sólo la lista.
export function SuggestionsList({ suggestions, onAccept }) {
  if (!suggestions || suggestions.length === 0) return null;

  return (
    <ul className="space-y-4">
      {suggestions.map((group) => (
        <SuggestionRow key={group.original_uid} group={group} onAccept={onAccept} />
      ))}
    </ul>
  );
}
