import { formatPrice } from "../../utils/formatters";

/**
 * Explica de dónde sale el total de una tienda: qué promoción se aplicó a cada
 * línea y qué descuento bancario entró. El JSON crudo sólo existe en el build
 * de desarrollo: sirve para depurar, no para comprar.
 */
export function PromoTransparency({ checkout, cartItems }) {
  const products = checkout.products || [];
  const linesWithPromo = products.filter((item) => item.applied_promo_id);
  const bankDiscount = checkout.bank_discount;

  return (
    <details className="mt-3 text-xs text-ink-muted">
      <summary className="cursor-pointer select-none">Ver descuentos aplicados</summary>

      {linesWithPromo.length === 0 && !bankDiscount ? (
        <p className="mt-2">No se aplicó ninguna promoción en esta tienda.</p>
      ) : (
        <ul className="mt-2 space-y-2">
          {linesWithPromo.map((item) => (
            <li key={item.unified_id} className="border-l-2 border-state-promo pl-2">
              <p className="font-semibold text-ink">
                {cartItems[item.unified_id]?.name || item.unified_id} (x{item.quantity})
              </p>
              <p className="text-state-promo">{item.promo_description}</p>
              <p>
                {formatPrice(item.effective_unit_price)} c/u · total {formatPrice(item.total_cost)}
              </p>
            </li>
          ))}

          {bankDiscount && (
            <li className="border-l-2 border-state-success pl-2">
              <p className="font-semibold text-ink">Descuento bancario</p>
              <p className="text-state-success">
                {bankDiscount.description || `Tarjeta ${bankDiscount.card}`}
              </p>
              <p>-{formatPrice(bankDiscount.amount)}</p>
            </li>
          )}
        </ul>
      )}

      {/* El JSON crudo es una herramienta de desarrollo y no tenía ningún gate:
          quedaba a dos clicks de cualquier usuario, adentro de una pantalla que
          justamente busca que le CREAN al precio. Ver una estructura de datos
          ahí no explica nada y sugiere que la app está a medio hacer.
          `import.meta.env.DEV` es false en el bundle de producción, así que Vite
          lo elimina entero del build. */}
      {import.meta.env.DEV && (
        <details className="mt-2">
          <summary className="cursor-pointer select-none">Ver JSON crudo (dev)</summary>
          {/* El contenedor scrollea solo: sin esto una línea larga del JSON
              empujaría el ancho de toda la página. */}
          <div className="mt-1 max-h-64 overflow-auto rounded bg-surface-muted p-2">
            <pre className="text-[11px] leading-tight">{JSON.stringify(checkout, null, 2)}</pre>
          </div>
        </details>
      )}
    </details>
  );
}
