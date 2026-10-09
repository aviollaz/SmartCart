import { formatPrice } from "../../utils/formatters";

/**
 * El subtotal es una ESTIMACIÓN y el texto lo dice, porque el número que
 * importa lo calcula /optimize: acá se suman los precios que muestran las
 * líneas, sin envío. Es un piso (ver `CartProductsContext`): el total final
 * sale igual o algo mayor.
 *
 * Se muestra tanto en `CartPage` como en `CartDrawer` (ver
 * `CartProductsContext`): es exactamente el mismo número en los dos lugares,
 * así que es un solo componente y no dos copias del mismo JSX.
 */
export function EstimatedSubtotal({ subtotalEstimado, className = "" }) {
  if (subtotalEstimado === null) return null;

  return (
    <div className={`flex items-baseline justify-between border-t border-line pt-3 ${className}`}>
      <div>
        <p className="text-sm font-semibold text-ink">Subtotal estimado</p>
        <p className="text-xs text-ink-muted">
          La suma de los precios que ves, sin envío. El total final puede ser algo mayor; lo calcula “Optimizar compra”.
        </p>
      </div>
      <p className="font-display text-lg font-bold text-brand-violet-700">
        {formatPrice(subtotalEstimado)}
      </p>
    </div>
  );
}
