import { ArrowRight, BadgePercent } from "lucide-react";
import { formatPrice, storeName } from "../../utils/formatters";

/**
 * Encabezado del resultado: lo que se paga y lo que se ahorra.
 *
 * El ahorro suma dos cosas que SmartCart hace por el usuario: elegir la tienda
 * de cada producto (`price_savings`, contra el promedio de los otros súper) y
 * aplicar el mejor descuento bancario de cada tienda (`bank_discount` de cada
 * checkout). No resta envíos, y el desplegable dice de dónde sale cada parte:
 * un número grande en verde sin decir contra qué se compara es una promesa que
 * el ticket no cumple.
 */
export function SavingsPanel({ result, cartItems, maxStores, onChooseMaxStores }) {
  const priceSavings = Math.max(result.price_savings?.total ?? 0, 0);
  const items = result.price_savings?.items || [];
  const bankSavings = Object.values(result.split || {}).reduce(
    (sum, checkout) => sum + (checkout.bank_discount?.amount || 0),
    0
  );
  const total = priceSavings + bankSavings;
  // La base del porcentaje, a la vista y tachada. Antes no se mostraba, y la
  // gente comparaba el ahorro contra el único otro número que había visto (el
  // subtotal estimado del carrito): "32% de $275.000 no da $236.000". Con la
  // base al lado, la resta y el porcentaje se verifican en la misma pantalla.
  // Lleva los mismos envíos que el total, así que la diferencia es exacta.
  const baseline = result.total_spent_net + total;
  const pct = total / baseline;

  // Formato de etiqueta de góndola (como Día): tachado grande + porcentaje
  // destacado arriba, total abajo. Los pesos ahorrados y contra qué se compara
  // van en el desplegable: los usuarios no leen, y el texto suelto le quitaba
  // peso a los dos números que sí miran.
  return (
    <div className="rounded-lg border border-line bg-surface p-4">
      {/* Con ahorro cero no se dibuja: un "$0" en verde es ruido, no un dato. */}
      {total > 0 && (
        <div className="flex items-center gap-2">
          <span className="text-xl font-semibold text-ink-muted line-through">{formatPrice(baseline)}</span>
          <span className="flex items-center gap-1 rounded-md bg-state-success px-2 py-0.5 text-base font-bold text-white">
            <BadgePercent size={18} className="shrink-0" aria-hidden="true" />
            {Math.round(pct * 100)}%
          </span>
        </div>
      )}
      <p className="text-2xl font-bold text-brand-violet-700">Total {formatPrice(result.total_spent_net)}</p>

      {total > 0 && (
        <div className="mt-1">
          <details className="text-sm text-ink-muted">
            <summary className="cursor-pointer select-none">Ver de dónde sale</summary>
            <div className="mt-2 space-y-2">
              <p className="text-xs">
                Ahorrás <span className="font-semibold text-state-success">{formatPrice(total)}</span> frente a comprar
                cada producto al precio promedio de los otros súper, sin descuentos bancarios.
              </p>
              {priceSavings > 0 && (
                <div>
                  <SavingsLine label="Mejor precio en cada producto" amount={priceSavings} />
                  <ul className="mt-1 space-y-1 pl-3 text-xs">
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
                </div>
              )}
              {bankSavings > 0 && <SavingsLine label="Descuentos bancarios" amount={bankSavings} />}
              {/* Sólo cuando comprar alguna tienda otro día del rango sale más
                  barato (el backend manda today_total_spent_net en null si no).
                  Ya está dentro de los descuentos bancarios: es una nota, no un
                  sumando. Qué día va cada tienda lo dice StoreBreakdownCard. */}
              {result.today_total_spent_net != null && (
                <p className="text-xs">
                  Incluye comprar en el mejor día:{" "}
                  {formatPrice(result.today_total_spent_net - result.total_spent_net)} menos que comprando todo hoy.
                </p>
              )}
              <p className="text-xs">Los envíos son los mismos en los dos precios.</p>
            </div>
          </details>
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

function SavingsLine({ label, amount }) {
  return (
    <p className="flex justify-between gap-3 text-ink">
      <span>{label}</span>
      <span className="font-semibold text-state-success">−{formatPrice(amount)}</span>
    </p>
  );
}
