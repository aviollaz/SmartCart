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
 * Una fila de "Más opciones", como StrategicSwapCard, y una sola opción: la
 * primera del backend, que saca una tienda y es la más barata. Elegirla guarda
 * el tope en el perfil (`maxStores`) y vuelve a optimizar, así que el total que
 * aparece después sale del mismo solver que el número de acá. El monto va con
 * "+" porque es lo que cuesta de más. Con un tope puesto, el "Quitar límite"
 * vive en el encabezado (SavingsPanel), no acá: esta fila sólo aparece si hay
 * una opción que ofrecer.
 */
export function FewerStoresCard({ options, onChoose }) {
  const [option] = options || [];
  if (!option) return null;

  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <p className="flex items-center gap-2 text-sm text-ink">
        <Layers size={16} className="shrink-0 text-brand-violet-700" />
        <span>Comprá {storesLabel(option.stores)}</span>
      </p>
      <span className="flex shrink-0 items-center gap-3">
        <strong className="text-sm text-ink">+{formatPrice(option.extra_cost)}</strong>
        <button
          type="button"
          onClick={() => onChoose(option.max_stores)}
          className="rounded-md border border-brand-accent px-4 py-1.5 text-sm font-semibold text-brand-accent hover:bg-brand-accent hover:text-white"
        >
          Usar
        </button>
      </span>
    </div>
  );
}
