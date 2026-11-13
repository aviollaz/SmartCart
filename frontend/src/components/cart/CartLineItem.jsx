import { Link } from "react-router-dom";
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
 *
 * Alto fijo (`h-20`), sea cual sea el nombre: al quitar una línea sube la
 * siguiente, y si midiera distinto su X quedaría en otra altura y habría que
 * volver a apuntar. Por eso el nombre se recorta a dos líneas (entero en el
 * `title`).
 *
 * La línea es su propio container (`@container`): angosta —el drawer— el
 * total va debajo del nombre, porque en columna aparte le dejaba al nombre
 * ~24px; ancha —/carrito— va en su columna a la derecha.
 */
// `unifiedId` es opcional: con él, el nombre linkea a la ficha del producto.
// El drawer del carrito no lo pasa, porque un link ahí navegaría por debajo
// del panel abierto.
export function CartLineItem({ unifiedId, name, quantity, product, onIncrement, onDecrement, onRemove }) {
  const unitario = product ? resolveDisplayPrice(product) : null;
  const imagen = product ? resolveDisplayImage(product) : null;

  return (
    <li className="@container flex h-20 items-center gap-3">
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

      <div className="min-w-0 flex-1">
        {unifiedId ? (
          <Link
            to={`/producto/${encodeURIComponent(unifiedId)}`}
            title={name}
            className="line-clamp-2 text-sm text-ink hover:text-brand-violet-700 hover:underline"
          >
            {name}
          </Link>
        ) : (
          <p title={name} className="line-clamp-2 text-sm text-ink">
            {name}
          </p>
        )}
        {typeof unitario === "number" && (
          // Angosta, el total va primero: si la línea no entra, que se corte el
          // "c/u" y no el número que importa.
          <p className="truncate text-xs text-ink-muted">
            <span className="font-semibold text-ink @md:hidden">{formatPrice(unitario * quantity)} · </span>
            {formatPrice(unitario)} c/u
          </p>
        )}
      </div>

      {typeof unitario === "number" && (
        <p className="hidden w-28 shrink-0 whitespace-nowrap text-right text-sm font-semibold tabular-nums text-ink @md:block">
          {formatPrice(unitario * quantity)}
        </p>
      )}

      <QuantityStepper quantity={quantity} onIncrement={onIncrement} onDecrement={onDecrement} size="sm" />
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Quitar ${name} del carrito`}
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded text-ink-muted hover:bg-surface-muted hover:text-state-promo"
      >
        <X size={16} />
      </button>
    </li>
  );
}
