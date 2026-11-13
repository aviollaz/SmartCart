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

      {/* Cada parte ocupa el mismo alto haya o no contenido (etiquetas, promo,
          marca): en una fila de la grilla todas las cards miden igual, y nada
          de lo que cambia al tocar el selector lo corre de lugar. */}
      <div className="mb-2 h-5 overflow-hidden">
        <DietaryBadges product={product} />
      </div>
      <PriceBlock product={product} pricing={pricing} showPricingHint={false} fixedSlots />

      <Link
        to={detailUrl}
        className="mt-2 line-clamp-2 h-10 text-sm text-ink hover:text-brand-violet-700 hover:underline"
        title={product.name}
      >
        {product.name}
      </Link>
      <p className="mb-3 h-4 truncate text-xs text-ink-muted" title={product.brand || undefined}>
        {product.brand}
      </p>

      {/* Patrón e-commerce estándar: hasta que el producto no está en el carrito
          hay un solo botón "Agregar"; el selector de unidades aparece recién
          después. Bajar a 0 elimina el ítem y la card vuelve sola al botón. */}
      {/* El "Calculando…" va en esta fila y no en el PriceBlock: ahí sumaba una
          línea, la card crecía y el stepper bajaba entre un clic y el siguiente. */}
      <div className="mt-auto flex h-9 items-center justify-end gap-2">
        {pricing.pricing && !pricing.byQuantity && (
          <span className="mr-auto min-w-0 truncate text-xs text-ink-muted">Calculando…</span>
        )}
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
            className="flex h-9 w-full items-center justify-center gap-2 rounded-md bg-brand-accent px-4 text-sm font-semibold text-white hover:bg-brand-accent-dark"
          >
            <ShoppingCart size={16} />
            Agregar
          </button>
        )}
      </div>
    </div>
  );
}
