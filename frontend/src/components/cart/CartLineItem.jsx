import { X } from "lucide-react";
import { QuantityStepper } from "../plp/QuantityStepper";
import { formatPrice, resolveDisplayImage, resolveDisplayPrice } from "../../utils/formatters";

/**
 * Una línea del carrito.
 *
 * `product` es opcional a propósito: viene de `/products/by-ids`
 * (`useCartProducts`) y esa consulta falla abierto, así que la línea tiene que
 * dibujarse igual con sólo el nombre y la cantidad, que es lo único que
 * `CartContext` guarda.
 */
export function CartLineItem({ name, quantity, product, onIncrement, onDecrement, onRemove }) {
  const unitario = product ? resolveDisplayPrice(product) : null;
  const imagen = product ? resolveDisplayImage(product) : null;

  return (
    <li className="flex items-center gap-3 py-3">
      {imagen ? (
        <img
          src={imagen}
          alt=""
          loading="lazy"
          className="h-12 w-12 shrink-0 rounded object-contain"
        />
      ) : (
        <div className="h-12 w-12 shrink-0 rounded bg-surface-muted" aria-hidden="true" />
      )}

      <div className="flex-1">
        <p className="text-sm text-ink">{name}</p>
        {typeof unitario === "number" && (
          <p className="text-xs text-ink-muted">{formatPrice(unitario)} c/u</p>
        )}
      </div>

      {typeof unitario === "number" && (
        <p className="w-24 shrink-0 text-right text-sm font-semibold text-ink">
          {formatPrice(unitario * quantity)}
        </p>
      )}

      <QuantityStepper quantity={quantity} onIncrement={onIncrement} onDecrement={onDecrement} size="sm" />
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Quitar ${name} del carrito`}
        className="text-ink-muted hover:text-state-promo"
      >
        <X size={16} />
      </button>
    </li>
  );
}
