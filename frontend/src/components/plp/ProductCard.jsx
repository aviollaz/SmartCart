import { useState } from "react";
import { ShoppingCart } from "lucide-react";
import { useCart } from "../../context/CartContext";
import { useFlattenedPrice } from "../../hooks/useFlattenedPrice";
import { formatPrice, formatUnitPrice, resolveDisplayImage, resolveDisplayPrice, storeLabel } from "../../utils/formatters";
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

// Solo se muestran en afirmativo: la ausencia del flag significa que el parser
// no encontró una declaración explícita, no que el producto tenga gluten.
function DietaryBadges({ product }) {
  const labels = [];
  if (product.is_gluten_free) labels.push("Sin TACC");
  if (product.is_vegan) labels.push("Vegano");
  if (labels.length === 0) return null;

  return (
    <ul className="mb-2 flex flex-wrap gap-1">
      {labels.map((label) => (
        <li
          key={label}
          className="rounded-full border border-line px-2 py-0.5 text-[11px] font-semibold text-ink-muted"
        >
          {label}
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
  const displayImage = resolveDisplayImage(product);

  // Cantidad "en borrador" para los productos que todavía no están en el carrito:
  // permite ver el efecto de una promo de volumen antes de agregar nada.
  const [draftQuantity, setDraftQuantity] = useState(1);
  const quantity = cartEntry ? cartEntry.quantity : draftQuantity;

  const { data: flattened, loading: pricing } = useFlattenedPrice(product.unified_id, quantity);

  // Solo se pisa el precio de la card si el aplanado es efectivamente más barato;
  // si la promo no aplica a esta cantidad, la card queda igual que siempre.
  const hasBetterPrice =
    flattened && typeof displayPrice === "number" && flattened.unitPrice < displayPrice - 0.01;

  return (
    <div className="flex flex-col rounded-lg border border-line bg-surface p-4">
      <div className="mb-3 flex h-36 items-center justify-center">
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
      </div>

      <DietaryBadges product={product} />
      <PromoBadges product={product} />

      {hasBetterPrice ? (
        <>
          <p className="text-lg font-bold text-brand-violet-700">
            {formatPrice(flattened.unitPrice)}
            <span className="ml-2 text-sm font-normal text-ink-muted line-through">
              {formatPrice(displayPrice)}
            </span>
          </p>
          <p className="mb-1 text-xs font-semibold text-state-promo">
            c/u llevando {quantity} en {storeLabel(flattened.storeId)}
            {flattened.promoDescription ? ` · ${flattened.promoDescription}` : ""}
          </p>
        </>
      ) : (
        <>
          {displayPrice != null && (
            <p className="text-lg font-bold text-brand-violet-700">{formatPrice(displayPrice)}</p>
          )}
          {pricing && <p className="mb-1 text-xs text-ink-muted">Calculando precio por cantidad…</p>}
        </>
      )}
      {unitPriceLabel && <p className="mb-1 text-xs text-ink-muted">{unitPriceLabel}</p>}

      <StoreBreakdown product={product} />

      <p className="mb-3 line-clamp-2 flex-1 text-sm text-ink" title={product.name}>
        {product.name}
      </p>
      {product.brand && <p className="mb-3 -mt-2 text-xs text-ink-muted">{product.brand}</p>}

      <div className="flex items-center justify-end gap-2">
        {cartEntry ? (
          <QuantityStepper
            quantity={cartEntry.quantity}
            onIncrement={() => incrementItem(product.unified_id)}
            onDecrement={() => decrementItem(product.unified_id)}
          />
        ) : (
          <>
            <QuantityStepper
              quantity={draftQuantity}
              onIncrement={() => setDraftQuantity((q) => q + 1)}
              onDecrement={() => setDraftQuantity((q) => Math.max(1, q - 1))}
              size="sm"
            />
            <button
              type="button"
              onClick={() => addItem(product.unified_id, product.name, draftQuantity)}
              aria-label="Agregar al carrito"
              className="flex items-center justify-center rounded-md bg-brand-accent p-2.5 text-white hover:bg-brand-accent-dark"
            >
              <ShoppingCart size={18} />
            </button>
          </>
        )}
      </div>
    </div>
  );
}
