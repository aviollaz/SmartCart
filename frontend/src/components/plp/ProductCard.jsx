import { ShoppingCart } from "lucide-react";
import { useCart } from "../../context/CartContext";
import { useProfile } from "../../context/ProfileContext";
import { useFlattenedPrice } from "../../hooks/useFlattenedPrice";
import {
  formatPrice,
  formatUnitPrice,
  resolveBestOffer,
  resolveDisplayImage,
  resolveDisplayPrice,
  storeLabel,
} from "../../utils/formatters";
import { QuantityStepper } from "./QuantityStepper";

// `skipDescription` evita repetir como badge la promo que ya está explicada
// debajo del precio.
function PromoBadges({ product, skipDescription }) {
  const badges = [];
  for (const offer of product.available_at_stores || []) {
    for (const promo of offer.promotions || []) {
      if (!promo.description) continue;
      if (skipDescription && promo.description === skipDescription) continue;
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
      {/* Se muestra el neto, no el de lista: con un descuento directo el
          desglose contradecía al precio grande de arriba. */}
      {offers.map((offer, index) => (
        <span key={offer.store_id} className={offer.in_stock ? "" : "line-through opacity-60"}>
          {index > 0 && " · "}
          {storeLabel(offer.store_id)} {formatPrice(offer.promo_unit_price ?? offer.base_price)}
        </span>
      ))}
    </p>
  );
}

export function ProductCard({ product }) {
  const { items, addItem, incrementItem, decrementItem } = useCart();
  const { unavailableStores } = useProfile();
  const cartEntry = items[product.unified_id];
  const displayPrice = resolveDisplayPrice(product);
  const unitPriceLabel = formatUnitPrice({ ...product, min_price: displayPrice });
  const displayImage = resolveDisplayImage(product);

  // Promo que ya está aplicada en el precio de la card (descuento directo, el
  // único tipo que rige desde la primera unidad). Las condicionales no entran
  // acá: el backend manda promo_unit_price en null a cantidad 1.
  //
  // El precio tachado es el de lista DE ESTA oferta, no el mínimo entre
  // tiendas: si Día lista más barato que Coto pero el descuento lo tiene Coto,
  // tachar el de Día pondría el precio de una tienda al lado del de la otra.
  const bestOffer = resolveBestOffer(product);
  const catalogPromo =
    bestOffer && bestOffer.offer.promo_unit_price != null ? bestOffer.offer : null;

  // La cantidad sale del carrito: antes existía un borrador local que dejaba el
  // stepper en 3 o 4 unidades sin que el producto estuviera agregado.
  const quantity = cartEntry ? cartEntry.quantity : 1;

  const { data: flattened, loading: pricing } = useFlattenedPrice(
    product.unified_id,
    quantity,
    unavailableStores
  );

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
      <PromoBadges product={product} skipDescription={catalogPromo?.promo_description} />

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
            <p className="text-lg font-bold text-brand-violet-700">
              {formatPrice(displayPrice)}
              {catalogPromo && (
                <span className="ml-2 text-sm font-normal text-ink-muted line-through">
                  {formatPrice(catalogPromo.base_price)}
                </span>
              )}
            </p>
          )}
          {/* Un descuento directo ya rige a una unidad, así que se nombra la
              promo a secas: decir "c/u llevando 1" daría a entender que hace
              falta una cantidad mínima que no existe. */}
          {catalogPromo && (
            <p className="mb-1 text-xs font-semibold text-state-promo">
              {storeLabel(catalogPromo.store_id)}
              {catalogPromo.promo_description ? ` · ${catalogPromo.promo_description}` : ""}
            </p>
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
