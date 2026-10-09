import { ArrowRight, PiggyBank } from "lucide-react";
import { formatPrice, storeName } from "../../utils/formatters";

/**
 * Encabezado del resultado: lo que se gasta y lo que se ahorra por haber elegido
 * bien la tienda de cada producto.
 *
 * El ahorro es una comparación producto a producto — el promedio de los otros
 * súper que lo tienen, contra el que se termina pagando — y por eso NO es la
 * diferencia entre dos totales: no incluye envíos ni descuentos bancarios. La
 * aclaración está en pantalla y no sólo acá, porque un número grande en verde
 * sin decir contra qué se compara es una promesa que el ticket no cumple.
 */
export function SavingsPanel({ result, cartItems, maxStores, onChooseMaxStores }) {
  const savings = result.price_savings;
  const total = savings?.total ?? 0;
  const pct = savings?.pct ?? 0;
  const items = savings?.items || [];

  // Una sola tarjeta: total y ahorro eran dos cajas y, con los avisos que
  // venían abajo, el resultado arrancaba con cinco carteles.
  return (
    <div className="rounded-lg border border-line bg-surface p-4">
      <p className="text-2xl font-bold text-brand-violet-700">Total {formatPrice(result.total_spent_net)}</p>
      {/* Sólo cuando comprar alguna tienda otro día del rango sale más
          barato (el backend manda today_total_spent_net en null si no). Qué
          día va cada una lo dice su tarjeta en StoreBreakdownCard. */}
      {result.today_total_spent_net != null && (
        <p className="mt-1 text-sm font-semibold text-ink">
          {formatPrice(result.today_total_spent_net - result.total_spent_net)} menos que comprando todo hoy
        </p>
      )}

      {/* Con ahorro cero o negativo no se dibuja: cero pasa cuando cada
          producto se consigue en una sola tienda, y un "$0" en verde es
          ruido, no un dato.
          El detalle de contra qué se compara (producto a producto, sin envío
          ni descuento bancario) vive en el desplegable, no en una línea fija:
          una sola frase alcanza para lo que se lee de arriba. */}
      {total > 0 && (
        <div className="mt-2">
          <p className="flex flex-wrap items-center gap-x-2 text-lg font-bold text-state-success">
            <PiggyBank size={22} className="shrink-0" />
            Ahorrás {formatPrice(total)}
            <span className="text-sm font-semibold text-ink">
              · {Math.round(pct * 100)}% menos que el promedio de los otros súper
            </span>
          </p>

          {items.length > 0 && (
            <details className="mt-1 text-xs text-ink-muted">
              <summary className="cursor-pointer select-none">Ver de dónde sale</summary>
              <ul className="mt-1 space-y-1">
                {items.map((item) => (
                  <li key={item.unified_id} className="flex flex-wrap items-center gap-x-1.5">
                    <span className="text-ink">{cartItems[item.unified_id]?.name || item.unified_id}</span>
                    <span>Promedio del resto {formatPrice(item.reference_cost)}</span>
                    <ArrowRight size={12} />
                    <span>
                      {storeName(item.actual_store)} {formatPrice(item.actual_cost)}
                    </span>
                    {/* Negativo cuando el solver pagó más que el promedio para
                        llegar al mínimo de compra de esa tienda. */}
                    <span className={`font-semibold ${item.savings > 0 ? "text-state-success" : "text-ink"}`}>
                      {item.savings > 0 ? "−" : "+"}
                      {formatPrice(Math.abs(item.savings))}
                    </span>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}

      {/* Con un tope de súper elegido, el total de arriba no es el óptimo: se
          dice acá, a la vista, junto con la forma de volver a él. */}
      {maxStores != null && (
        <p className="mt-2 text-xs text-ink-muted">
          Comprando en como máximo {maxStores} supermercado{maxStores === 1 ? "" : "s"} ·{" "}
          <button
            type="button"
            onClick={() => onChooseMaxStores(null)}
            className="underline hover:text-brand-violet-700"
          >
            Quitar límite
          </button>
        </p>
      )}
    </div>
  );
}
