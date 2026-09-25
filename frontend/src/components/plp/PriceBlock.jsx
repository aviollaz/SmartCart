import { formatPrice, formatUnitPrice, storeName } from "../../utils/formatters";

const SIZES = {
  md: { price: "text-lg", list: "text-sm" },
  lg: { price: "text-3xl", list: "text-base" },
};

/**
 * El precio de un producto tal como lo resuelve useProductPricing: el grande,
 * el tachado, la leyenda de la promo y el precio por kg/L. Es lo único que la
 * card muestra de precio —el desglose por supermercado vive en la página del
 * producto— así que este bloque tiene que alcanzar solo.
 */
export function PriceBlock({ product, pricing, size = "md" }) {
  const { price, listPrice, storeId, promoDescription, byQuantity, quantity } = pricing;
  const sizes = SIZES[size];
  const unitPriceLabel = formatUnitPrice(product);

  return (
    <div>
      {price != null && (
        // flex-wrap: en la grilla de dos columnas del celular, precio y tachado
        // no entran en una línea y el tachado desbordaba la pantalla.
        <p className={`flex flex-wrap items-baseline gap-x-2 ${sizes.price} font-bold text-brand-violet-700`}>
          {formatPrice(price)}
          {listPrice != null && (
            <span className={`${sizes.list} font-normal text-ink-muted line-through`}>
              {formatPrice(listPrice)}
            </span>
          )}
        </p>
      )}
      {/* Un descuento directo ya rige a una unidad, así que se nombra la promo
          a secas: decir "c/u llevando 1" daría a entender que hace falta una
          cantidad mínima que no existe. */}
      {storeId && (
        <p className="text-xs font-semibold text-state-promo">
          {byQuantity ? `c/u llevando ${quantity} en ${storeName(storeId)}` : storeName(storeId)}
          {promoDescription ? ` · ${promoDescription}` : ""}
        </p>
      )}
      {pricing.pricing && !byQuantity && (
        <p className="text-xs text-ink-muted">Calculando precio por cantidad…</p>
      )}
      {unitPriceLabel && <p className="text-xs text-ink-muted">{unitPriceLabel}</p>}
    </div>
  );
}
