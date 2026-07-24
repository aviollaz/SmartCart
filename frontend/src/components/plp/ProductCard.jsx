import { ShoppingCart } from "lucide-react";
import { useCart } from "../../context/CartContext";
import { formatPrice, formatUnitPrice, resolveDisplayPrice, storeLabel } from "../../utils/formatters";
import { QuantityStepper } from "./QuantityStepper";

function PromoBadges({ product }) {
  const badges = [];
  for (const offer of product.available_at_stores || []) {
    for (const promo of offer.promotions || []) {
      if (!promo.description) continue;
      badges.push({ key: `${offer.store_id}-${promo.promo_id || promo.description}`, storeId: offer.store_id, promo });
    }
  }
  if (badges.length === 0) return null;

  return (
    <ul className="mb-2 space-y-1">
      {badges.map(({ key, storeId, promo }) => (
        <li key={key} className="text-xs font-semibold text-state-promo">
          {storeLabel(storeId)}: {promo.description}
        </li>
      ))}
    </ul>
  );
}

function StoreBreakdown({ product }) {
  const offers = product.available_at_stores || [];
  if (offers.length === 0) return null;

  return (
    <p className="mb-2 text-xs text-ink-muted">
      {offers.map((offer, index) => (
        <span key={offer.store_id} className={offer.in_stock ? "" : "line-through opacity-60"}>
          {index > 0 && " · "}
          {storeLabel(offer.store_id)} {formatPrice(offer.base_price)}
        </span>
      ))}
    </p>
  );
}

export function ProductCard({ product }) {
  const { items, addItem, incrementItem, decrementItem } = useCart();
  const cartEntry = items[product.unified_id];
  const displayPrice = resolveDisplayPrice(product);
  const unitPriceLabel = formatUnitPrice({ ...product, min_price: displayPrice });

  return (
    <div className="flex flex-col rounded-lg border border-line bg-surface p-4">
      <div className="mb-3 flex h-36 items-center justify-center">
        {product.image_url ? (
          <img
            src={product.image_url}
            alt={product.name}
            className="h-full w-full object-contain"
            loading="lazy"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center rounded bg-surface-muted text-xs text-ink-muted">
            Sin foto
          </div>
        )}
      </div>

      <PromoBadges product={product} />

      {displayPrice != null && (
        <p className="text-lg font-bold text-brand-violet-700">{formatPrice(displayPrice)}</p>
      )}
      {unitPriceLabel && <p className="mb-1 text-xs text-ink-muted">{unitPriceLabel}</p>}

      <StoreBreakdown product={product} />

      <p className="mb-3 line-clamp-2 flex-1 text-sm text-ink" title={product.name}>
        {product.name}
      </p>
      {product.brand && <p className="mb-3 -mt-2 text-xs text-ink-muted">{product.brand}</p>}

      <div className="flex items-center justify-end">
        {cartEntry ? (
          <QuantityStepper
            quantity={cartEntry.quantity}
            onIncrement={() => incrementItem(product.unified_id)}
            onDecrement={() => decrementItem(product.unified_id)}
          />
        ) : (
          <button
            type="button"
            onClick={() => addItem(product.unified_id, product.name)}
            aria-label="Agregar al carrito"
            className="flex items-center justify-center rounded-md bg-brand-accent p-2.5 text-white hover:bg-brand-accent-dark"
          >
            <ShoppingCart size={18} />
          </button>
        )}
      </div>
    </div>
  );
}
