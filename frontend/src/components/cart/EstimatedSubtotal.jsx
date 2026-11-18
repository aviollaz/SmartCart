import { formatPrice } from "../../utils/formatters";

/**
 * El subtotal es una ESTIMACIÓN, porque el número que importa lo calcula
 * /optimize: acá se suman los precios que muestran las líneas, sin envío. No es
 * un piso ni un techo (ver `CartProductsContext`).
 *
 * Sólo la etiqueta, sin párrafo explicativo: los usuarios no leen, y un
 * párrafo al lado le quitaba peso al botón de optimizar. "Estimado" alcanza; el
 * porqué de la diferencia con el total está en la FAQ.
 *
 * Se muestra tanto en `CartPage` como en `CartDrawer` (ver
 * `CartProductsContext`): es exactamente el mismo número en los dos lugares,
 * así que es un solo componente y no dos copias del mismo JSX.
 */
export function EstimatedSubtotal({ subtotalEstimado, className = "" }) {
  if (subtotalEstimado === null) return null;

  return (
    <div className={`flex items-baseline justify-between border-t border-line pt-3 ${className}`}>
      <p className="text-sm font-semibold text-ink">Subtotal estimado</p>
      <p className="font-display text-lg font-bold text-brand-violet-700">
        {formatPrice(subtotalEstimado)}
      </p>
    </div>
  );
}
