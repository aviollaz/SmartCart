const DIETARY_OPTIONS = [
  { key: "glutenFree", label: "Sin TACC" },
  { key: "vegan", label: "Vegano" },
];

/**
 * Único facet que dispara un re-fetch: el filtrado ocurre en SQL (ver
 * api/products.js). Por eso recibe props propias y no sale de useProductFilters.
 */
export function DietaryFacet({ dietary, onToggle }) {
  return (
    <fieldset className="border-b border-line py-4">
      <legend className="mb-2 font-display text-sm font-semibold text-ink">Dieta</legend>
      <ul className="space-y-1.5">
        {DIETARY_OPTIONS.map(({ key, label }) => (
          <li key={key}>
            <label className="flex cursor-pointer items-center gap-2 text-sm text-ink">
              <input
                type="checkbox"
                checked={Boolean(dietary[key])}
                onChange={() => onToggle(key)}
                className="h-4 w-4 accent-brand-violet-700"
              />
              <span className="flex-1 truncate">{label}</span>
            </label>
          </li>
        ))}
      </ul>
      {/* La ausencia del flag significa "no encontramos una declaración", no
          "contiene gluten": el parser solo marca ante una frase explícita.
          El texto evita que el filtro se lea como una certificación. */}
      <p className="mt-2 text-xs text-ink-muted">
        Solo productos con declaración explícita en la etiqueta.
      </p>
    </fieldset>
  );
}
