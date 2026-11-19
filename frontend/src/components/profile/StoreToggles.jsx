import { AlertTriangle } from "lucide-react";
import { useProfile } from "../../context/ProfileContext";
import { STORES } from "../../utils/constants";

export function storesSummary(excludedStores, maxStores) {
  const enabled = STORES.filter((store) => !excludedStores.includes(store.id));
  const names = enabled.length === STORES.length ? "Todos" : enabled.map((store) => store.name).join(" y ");
  return maxStores == null ? names : `${names} · máximo ${maxStores}`;
}

/**
 * Qué supermercados puede usar el optimizador. Existe sobre todo por Coto: no
 * permite armar el carrito desde otro sitio (hay que agregar producto por
 * producto), y hay quien prefiere pagar un poco más con tal de no hacerlo.
 *
 * Lo usan el carrito y el botón "Súper" del Header, para que se pueda cambiar
 * desde cualquier página: cambia los precios que muestra toda la grilla. El
 * "comprar en como máximo" queda sólo en el carrito: es una opción de cómo
 * optimizar, y en el Header parecía limitar qué súper se muestran.
 *
 * La última tienda marcada queda deshabilitada: sin ninguna no hay nada que
 * optimizar, y el backend lo rechaza igual (422).
 */
export function StoreToggles({ className = "" }) {
  const { excludedStores, setExcludedStores } = useProfile();
  const enabledCount = STORES.length - excludedStores.length;

  const toggle = (storeId) => {
    setExcludedStores(
      excludedStores.includes(storeId)
        ? excludedStores.filter((id) => id !== storeId)
        : [...excludedStores, storeId]
    );
  };

  return (
    <fieldset className={`flex flex-col gap-2 ${className}`}>
      <legend className="sr-only">Supermercados habilitados</legend>
      {STORES.map((store) => {
        const checked = !excludedStores.includes(store.id);
        const locked = checked && enabledCount === 1;
        return (
          <div key={store.id}>
            <label className={`flex items-center gap-2 text-sm ${locked ? "text-ink-muted" : "text-ink"}`}>
              <input
                type="checkbox"
                checked={checked}
                disabled={locked}
                onChange={() => toggle(store.id)}
                className="accent-brand-accent"
              />
              {store.name}
              {store.warning && <AlertTriangle size={14} className="shrink-0 text-state-warning" aria-hidden="true" />}
            </label>
            {/* Una tienda con aviso arranca deshabilitada (ProfileContext);
                el texto se ve antes de habilitarla, no después. */}
            {store.warning && (
              <p className="ml-6 mt-1 rounded border border-state-warning/40 bg-state-warning/10 px-2 py-1 text-xs text-ink">
                {store.warning}
              </p>
            )}
          </div>
        );
      })}
      <p className="text-xs text-ink-muted">Los que desmarques no se usan al optimizar ni aparecen en los precios.</p>
    </fieldset>
  );
}
