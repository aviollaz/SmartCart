import { Layers } from "lucide-react";
import { formatPrice, storeName } from "../../utils/formatters";

function storesLabel(stores) {
  const names = stores.map(storeName);
  return names.length === 1 ? `solo en ${names[0]}` : `en ${names.join(" y ")}`;
}

/**
 * Cuánto cuesta comprar en menos supermercados (`fewer_stores_options` de
 * /optimize). El solver minimiza plata y nada más, pero cada súper del reparto
 * es un checkout que el usuario completa a mano —franja, pago, a veces producto
 * por producto en Coto—, y ese costo sólo lo puede poner él. Así que no se le
 * decide: se le muestra el precio exacto de ahorrarse un checkout.
 *
 * Una línea, como StrategicSwapCard, y una sola opción: la primera del backend,
 * que saca una tienda y es la más barata. Elegirla guarda el tope en el perfil
 * (`maxStores`) y vuelve a optimizar, así que el total que aparece después sale
 * del mismo solver que el número de acá. Con un tope puesto se ofrece volver a
 * sin límite, que es la única forma de recuperar el óptimo desde el resultado.
 */
export function FewerStoresCard({ options, maxStores, onChoose }) {
  const [option] = options || [];
  if (!option && maxStores == null) return null;

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line bg-surface p-4">
      <p className="flex items-center gap-2 text-sm text-ink">
        <Layers size={16} className="shrink-0 text-brand-violet-700" />
        {option ? (
          <span>
            Comprá {storesLabel(option.stores)} por <strong>{formatPrice(option.extra_cost)}</strong> más
          </span>
        ) : (
          <span>
            Comprando en como máximo {maxStores} supermercado{maxStores === 1 ? "" : "s"}
          </span>
        )}
      </p>
      <span className="flex shrink-0 items-center gap-3">
        {maxStores != null && (
          <button
            type="button"
            onClick={() => onChoose(null)}
            className="text-xs text-ink-muted underline hover:text-brand-violet-700"
          >
            Sin límite
          </button>
        )}
        {option && (
          <button
            type="button"
            onClick={() => onChoose(option.max_stores)}
            className="rounded-md border border-brand-accent px-4 py-1.5 text-sm font-semibold text-brand-accent hover:bg-brand-accent hover:text-white"
          >
            Usar
          </button>
        )}
      </span>
    </div>
  );
}
