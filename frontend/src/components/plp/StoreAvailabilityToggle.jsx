const STORES = [
  { id: "coto_online", label: "Disponible en Coto" },
  { id: "dia_online", label: "Disponible en Día" },
];

export function StoreAvailabilityToggle({ storeFilter, onToggle }) {
  return (
    <fieldset className="border-b border-line py-4">
      <legend className="mb-2 font-display text-sm font-semibold text-ink">Disponibilidad</legend>
      <ul className="space-y-1.5">
        {STORES.map((store) => (
          <li key={store.id}>
            <label className="flex cursor-pointer items-center gap-2 text-sm text-ink">
              <input
                type="checkbox"
                checked={storeFilter[store.id]}
                onChange={() => onToggle(store.id)}
                className="h-4 w-4 accent-brand-violet-700"
              />
              {store.label}
            </label>
          </li>
        ))}
      </ul>
    </fieldset>
  );
}
