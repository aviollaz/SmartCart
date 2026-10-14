import { formatPrice, storeName } from "../../utils/formatters";

/**
 * Cuánto cuesta comprar en menos supermercados (`fewer_stores_options` de
 * /optimize). El solver minimiza plata y nada más, pero cada súper del reparto
 * es un checkout que el usuario completa a mano —franja, pago, a veces producto
 * por producto en Coto—, y ese costo sólo lo puede poner él. Así que no se le
 * decide: se le muestra el precio exacto de ahorrarse un checkout.
 *
 * Vive bajo "Dónde comprar" y no entre las opciones de ahorro porque cuesta
 * más, no ahorra. Una sola opción: la primera del backend, que saca una tienda
 * y es la más barata. Elegirla guarda el tope en el perfil (`maxStores`) y
 * vuelve a optimizar, así que el total que aparece después sale del mismo
 * solver que el número de acá. Con un tope puesto, el "Quitar límite" vive en
 * el encabezado (SavingsPanel): esta fila sólo aparece si hay una opción que
 * ofrecer.
 */
export function FewerStoresCard({ options, split, onChoose }) {
  const [option] = options || [];
  if (!option) return null;

  const removed = Object.keys(split || {})
    .filter((store) => !option.stores.includes(store))
    .map(storeName)
    .join(" y ");

  return (
    <div className="mb-3 flex flex-wrap items-center justify-between gap-3 text-sm text-ink-muted">
      <p>
        ¿Muchos envíos? Podés sacar {removed} pagando{" "}
        <strong className="font-semibold text-ink">{formatPrice(option.extra_cost)}</strong> más
      </p>
      <button
        type="button"
        onClick={() => onChoose(option.max_stores)}
        className="shrink-0 rounded-md border border-brand-accent px-4 py-1.5 text-sm font-semibold text-brand-accent hover:bg-brand-accent hover:text-white"
      >
        Sacar {removed}
      </button>
    </div>
  );
}
