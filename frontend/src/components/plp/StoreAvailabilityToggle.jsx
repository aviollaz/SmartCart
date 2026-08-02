import { STORES } from "../../utils/constants";

export function StoreAvailabilityToggle({ storeFilter, onToggle, unavailableStores = [] }) {
  // Una tienda que no entrega en la dirección del usuario ya no tiene productos
  // en la grilla: dejar su checkbox solo serviría para vaciarla sin explicación.
  const stores = STORES.filter((store) => !unavailableStores.includes(store.id));
  if (stores.length < 2) return null;

  return (
    <fieldset className="border-b border-line py-4">
      <legend className="mb-2 font-display text-sm font-semibold text-ink">Disponibilidad</legend>
      <ul className="space-y-1.5">
        {stores.map((store) => (
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
