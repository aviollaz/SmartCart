import { ArrowRight, PiggyBank } from "lucide-react";
import { formatPrice, storeName } from "../../utils/formatters";

/**
 * Encabezado del resultado: lo que se gasta y lo que se ahorra por haber elegido
 * bien la tienda de cada producto.
 *
 * El ahorro es una comparación producto a producto — el precio más caro entre
 * los súper que lo tienen, contra el que se termina pagando — y por eso NO es la
 * diferencia entre dos totales: no incluye envíos ni descuentos bancarios. La
 * aclaración está en pantalla y no sólo acá, porque un número grande en verde
 * sin decir contra qué se compara es una promesa que el ticket no cumple.
 */
export function SavingsPanel({ result, cartItems }) {
  const savings = result.price_savings;
  const total = savings?.total ?? 0;
  const items = savings?.items || [];

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <div className="rounded-lg border border-line bg-surface p-4">
        <p className="text-xs text-ink-muted">Gasto total (SmartCart)</p>
        <p className="text-2xl font-bold text-brand-violet-700">{formatPrice(result.total_spent_net)}</p>
      </div>

      {/* Con ahorro cero la tarjeta no se dibuja: pasa cuando cada producto se
          consigue en una sola tienda, y un "$0" en verde es ruido, no un dato.
          El detalle de contra qué se compara (producto a producto, sin envío
          ni descuento bancario) vive en el desplegable de abajo, no en una
          línea fija: una sola frase alcanza para lo que se lee de arriba. */}
      {total > 0 && (
        <div className="rounded-lg border border-line bg-surface p-4">
          <p className="flex items-center gap-1.5 text-sm text-ink">
            <PiggyBank size={16} className="shrink-0 text-state-success" />
            Ahorrás <span className="font-bold text-state-success">{formatPrice(total)}</span> usando
            el sitio
          </p>

          {items.length > 0 && (
            <details className="mt-2 text-xs text-ink-muted">
              <summary className="cursor-pointer select-none">Ver de dónde sale</summary>
              <ul className="mt-1 space-y-1">
                {items.map((item) => (
                  <li key={item.unified_id} className="flex flex-wrap items-center gap-x-1.5">
                    <span className="text-ink">{cartItems[item.unified_id]?.name || item.unified_id}</span>
                    <span>
                      {storeName(item.worst_store)} {formatPrice(item.worst_cost)}
                    </span>
                    <ArrowRight size={12} />
                    <span>
                      {storeName(item.actual_store)} {formatPrice(item.actual_cost)}
                    </span>
                    <span className="font-semibold text-state-success">
                      −{formatPrice(item.savings)}
                    </span>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </div>
  );
}
