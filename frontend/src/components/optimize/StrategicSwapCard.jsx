import { ArrowRight, Store } from "lucide-react";
import { formatPrice, storeName } from "../../utils/formatters";

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

  // Una línea y un botón: el mensaje largo del backend, el "antes → después" de
  // los totales y la lista de cambios abierta ocupaban media pantalla arriba
  // del total. La lista sigue a un clic, porque aceptar cambios de producto sin
  // poder verlos no es una opción.
  return (
    <div className="rounded-lg border border-brand-violet-500 bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="flex items-center gap-2 text-sm text-ink">
          <Store size={16} className="shrink-0 text-brand-violet-700" />
          <span>
            Sacá <strong>{storeName(closedStore)}</strong> del pedido y ahorrá{" "}
            <strong className="text-state-success">{formatPrice(suggestion.projected_savings)}</strong>
          </span>
        </p>
        <button
          type="button"
          onClick={() => onApply(suggestion)}
          className="shrink-0 rounded-md bg-brand-accent px-4 py-1.5 text-sm font-semibold text-white hover:bg-brand-accent-dark"
        >
          Aplicar
        </button>
      </div>

      <details className="mt-2">
        <summary className="cursor-pointer select-none text-xs font-semibold text-brand-violet-700">
          Ver {swaps.length === 1 ? "el cambio" : `los ${swaps.length} cambios`}
        </summary>
        <ul className="mt-1">
          {swaps.map((swap) => (
            <SwapRow key={swap.original_uid} swap={swap} />
          ))}
        </ul>
        {relocated > 0 && (
          <p className="mt-1 text-xs text-ink-muted">
            Otros {relocated} producto{relocated === 1 ? "" : "s"} se mudan a otra tienda sin cambiar.
          </p>
        )}
      </details>
    </div>
  );
}
