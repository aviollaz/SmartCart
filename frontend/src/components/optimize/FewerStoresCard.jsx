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
 * decide: se le muestra el precio exacto de ahorrarse checkouts.
 *
 * Elegir una opción guarda el tope en el perfil (`maxStores`) y vuelve a
 * optimizar, así que el total que aparece después sale del mismo solver que el
 * número de acá. Con un tope ya puesto se ofrece volver a sin límite, que es la
 * única forma de recuperar el óptimo si ya no hay opciones con menos tiendas.
 */
export function FewerStoresCard({ options, maxStores, onChoose }) {
  const hasOptions = options?.length > 0;
  if (!hasOptions && maxStores == null) return null;

  return (
    <div className="rounded-lg border border-line bg-surface p-4">
      <p className="flex items-center gap-2 text-sm font-semibold text-ink">
        <Layers size={16} className="shrink-0 text-brand-violet-700" />
        {hasOptions ? "¿Preferís hacer menos compras?" : `Estás comprando en como máximo ${maxStores} supermercado${maxStores === 1 ? "" : "s"}`}
      </p>
      {hasOptions && (
        <ul className="mt-2 flex flex-col gap-2">
          {options.map((option) => (
            <li key={option.max_stores} className="flex flex-wrap items-center justify-between gap-2 text-sm text-ink">
              <span>
                Comprá {storesLabel(option.stores)} por{" "}
                <strong>{formatPrice(option.extra_cost)}</strong> más
              </span>
              <button
                type="button"
                onClick={() => onChoose(option.max_stores)}
                className="rounded-md border border-brand-accent px-3 py-1 text-xs font-semibold text-brand-accent hover:bg-brand-accent hover:text-white"
              >
                Usar esta opción
              </button>
            </li>
          ))}
        </ul>
      )}
      {maxStores != null && (
        <button
          type="button"
          onClick={() => onChoose(null)}
          className="mt-2 text-xs text-ink-muted underline hover:text-brand-violet-700"
        >
          Volver a sin límite de supermercados (el más barato)
        </button>
      )}
    </div>
  );
}
