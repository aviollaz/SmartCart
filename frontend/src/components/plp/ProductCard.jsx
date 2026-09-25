import { Link } from "react-router-dom";
import { ShoppingCart } from "lucide-react";
import { useCart } from "../../context/CartContext";
import { useProductPricing } from "../../hooks/useProductPricing";
import { resolveDisplayImage } from "../../utils/formatters";
import { DietaryBadges } from "./DietaryBadges";
import { PriceBlock } from "./PriceBlock";
import { QuantityStepper } from "./QuantityStepper";

/**
 * Card de la grilla. Muestra UN precio —el más barato para la cantidad
 * elegida— y el precio por kg/L; el precio de cada supermercado y sus promos
 * por cantidad viven en la página del producto (`/producto/:id`), a un clic.
 * Antes la card listaba los tres precios y todas las promos, y con cuatro
 * columnas de grilla eso era una pared de números que tapaba el que importa.
 */
export function ProductCard({ product }) {
  const { addItem, incrementItem, decrementItem } = useCart();
  const pricing = useProductPricing(product);
  const { cartEntry } = pricing;
  const displayImage = resolveDisplayImage(product);
  const detailUrl = `/producto/${encodeURIComponent(product.unified_id)}`;

  return (
    <div className="flex flex-col rounded-lg border border-line bg-surface p-4 transition-shadow hover:shadow-md">
      <Link to={detailUrl} className="relative mb-3 flex h-36 items-center justify-center">
        {/* Sólo en /deals: el backend llena discount_pct únicamente ahí. */}
        {product.discount_pct > 0 && (
          <span className="absolute left-0 top-0 rounded-md bg-state-promo px-2 py-0.5 text-xs font-bold text-white">
            −{Math.round(product.discount_pct * 100)}%
          </span>
        )}
        {displayImage ? (
          <img
            src={displayImage}
            alt={product.name}
            className="h-full w-full object-contain"
            loading="lazy"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center rounded bg-surface-muted text-xs text-ink-muted">
            Sin foto
          </div>
        )}
      </Link>

      <DietaryBadges product={product} className="mb-2" />
      <PriceBlock product={product} pricing={pricing} />

      <Link
        to={detailUrl}
        className="mb-3 mt-2 line-clamp-2 flex-1 text-sm text-ink hover:text-brand-violet-700 hover:underline"
        title={product.name}
      >
        {product.name}
      </Link>
      {product.brand && <p className="mb-3 -mt-2 text-xs text-ink-muted">{product.brand}</p>}

      {/* Patrón e-commerce estándar: hasta que el producto no está en el carrito
          hay un solo botón "Agregar"; el selector de unidades aparece recién
          después. Bajar a 0 elimina el ítem y la card vuelve sola al botón. */}
      <div className="flex items-center justify-end gap-2">
        {cartEntry ? (
          <QuantityStepper
            quantity={cartEntry.quantity}
            onIncrement={() => incrementItem(product.unified_id)}
            onDecrement={() => decrementItem(product.unified_id)}
          />
        ) : (
          <button
            type="button"
            onClick={() => addItem(product.unified_id, product.name, 1)}
            className="flex w-full items-center justify-center gap-2 rounded-md bg-brand-accent px-4 py-2 text-sm font-semibold text-white hover:bg-brand-accent-dark"
          >
            <ShoppingCart size={16} />
            Agregar
          </button>
        )}
      </div>
    </div>
  );
}
