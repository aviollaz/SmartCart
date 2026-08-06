import { ArrowRight, Store } from "lucide-react";
import { formatPrice, storeName } from "../../utils/formatters";

// A partir de acá la lista de cambios se colapsa en un <details>. El backend
// topea en 8 (MAX_ANCHOR_SWAPS), así que el caso largo existe y una lista de
// ocho filas abierta tapa el resto del resultado.
const INLINE_SWAPS_LIMIT = 3;

function SwapRow({ swap }) {
  return (
    <li className="flex flex-col gap-1 border-t border-brand-violet-100 py-2 first:border-t-0 sm:flex-row sm:items-center sm:gap-3">
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm text-ink-muted line-through">{swap.original_name}</p>
        <p className="text-xs text-ink-muted">
          {swap.original_size}
          {swap.original_cost != null && ` · ${formatPrice(swap.original_cost)}`}
        </p>
      </div>

      <ArrowRight size={16} className="hidden shrink-0 text-brand-violet-500 sm:block" />

      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-ink">
          {swap.replacement_name}
          {swap.quantity > 1 && <span className="text-ink-muted"> (x{swap.quantity})</span>}
        </p>
        <p className="text-xs text-ink-muted">
          {swap.replacement_size} · {formatPrice(swap.replacement_cost)} en{" "}
          {storeName(swap.replacement_store)}
        </p>
      </div>
    </li>
  );
}

/**
 * Cierre de tienda: la recomendación de src/strategic_swaps.py.
 *
 * Responde algo que el solver no puede responder solo, porque sustituir un
 * producto lo saca de su espacio de búsqueda: un puñado de productos exclusivos
 * de una tienda la obligan a estar abierta, y con ella entran su mínimo de
 * compra y un segundo envío.
 *
 * Un solo CTA, sin selección por ítem: el ahorro proyectado sale de simular el
 * carrito con TODOS los reemplazos aplicados y la tienda excluida (el backend
 * corre optimize_cart() de verdad, no una cuenta aparte). Aplicar una parte deja
 * la tienda abierta y el número deja de significar nada.
 */
export function StrategicSwapCard({ suggestion, onApply }) {
  if (!suggestion || !suggestion.swaps?.length) return null;

  const { swaps, closed_store: closedStore, relocated_count: relocated } = suggestion;
  const swapList = <ul className="mt-1">{swaps.map((swap) => <SwapRow key={swap.original_uid} swap={swap} />)}</ul>;

  return (
    <div className="rounded-lg border-2 border-brand-violet-500 bg-surface p-4">
      <p className="flex items-center gap-2 font-display text-sm font-semibold text-brand-violet-700">
        <Store size={16} />
        Podés sacar {storeName(closedStore)} del pedido
      </p>

      <p className="mt-2 text-sm text-ink">{suggestion.message}</p>

      <div className="mt-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-2xl font-bold text-state-success">
          {formatPrice(suggestion.projected_savings)}
        </span>
        <span className="text-xs text-ink-muted">
          menos: {formatPrice(suggestion.original_total)} → {formatPrice(suggestion.simulated_total)}
        </span>
      </div>

      {swaps.length <= INLINE_SWAPS_LIMIT ? (
        swapList
      ) : (
        <details className="mt-2">
          <summary className="cursor-pointer select-none text-xs font-semibold text-brand-violet-700">
            Ver los {swaps.length} cambios
          </summary>
          {swapList}
        </details>
      )}

      {relocated > 0 && (
        <p className="mt-2 text-xs text-ink-muted">
          Los otros {relocated} producto{relocated === 1 ? "" : "s"} que ibas a comprar en{" "}
          {storeName(closedStore)} se mudan solos a otra tienda, sin cambiar de producto.
        </p>
      )}

      <button
        type="button"
        onClick={() => onApply(suggestion)}
        className="mt-3 w-full rounded-md bg-brand-accent px-4 py-2 text-sm font-semibold text-white hover:bg-brand-accent-dark"
      >
        Aplicar y recalcular
      </button>
    </div>
  );
}
