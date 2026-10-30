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
 *
 * `fixedSlots` (la card de la grilla) dibuja cada parte en un espacio de alto
 * fijo, haya o no promo: si la card creciera con la leyenda, el selector de
 * cantidad bajaría entre un clic y el siguiente (pasar de 2 a 3 unidades
 * activa "c/u llevando 3…"). Sin él (la página del producto) el texto va
 * entero, porque ahí no hay nada debajo que se mueva.
 */
export function PriceBlock({ product, pricing, size = "md", showPricingHint = true, fixedSlots = false }) {
  const { price, listPrice, storeId, promoDescription, byQuantity, quantity, quantityPromo } = pricing;
  const sizes = SIZES[size];
  const unitPriceLabel = formatUnitPrice(product);

  // Un descuento directo ya rige a una unidad, así que se nombra la promo a
  // secas: decir "c/u llevando 1" daría a entender que hace falta una cantidad
  // mínima que no existe.
  const legend = storeId
    ? `${byQuantity ? `c/u llevando ${quantity} en ${storeName(storeId)}` : storeName(storeId)}${
        promoDescription ? ` · ${promoDescription}` : ""
      }`
    : null;
  // Una promo por cantidad no baja el precio grande hasta que se lleva la
  // cantidad, pero tiene que verse antes: si no, un 3x2 sólo se descubre
  // subiendo el selector por casualidad.
  const quantityPromoText = quantityPromo
    ? `${quantityPromo.description || `Llevando ${quantityPromo.required_quantity}`} en ${storeName(
        quantityPromo.storeId
      )}: ${formatPrice(quantityPromo.unit_price)} c/u`
    : null;

  if (fixedSlots) {
    // Zona de promo de dos líneas: si hay una sola leyenda usa las dos; si hay
    // dos, una línea cada una. El tachado va acá y no al lado del precio,
    // donde en la grilla del celular partía la línea en dos.
    const clamp = legend && quantityPromoText ? "truncate" : "line-clamp-2";
    return (
      <div>
        <p className={`h-7 whitespace-nowrap ${sizes.price} font-bold text-brand-violet-700`}>
          {price != null ? formatPrice(price) : ""}
        </p>
        <div className="h-8 text-xs font-semibold text-state-promo">
          {legend && (
            <p className={clamp} title={legend}>
              {listPrice != null && (
                <span className="mr-1 font-normal text-ink-muted line-through">{formatPrice(listPrice)}</span>
              )}
              {legend}
            </p>
          )}
          {quantityPromoText && (
            <p className={clamp} title={quantityPromoText}>
              {quantityPromoText}
            </p>
          )}
        </div>
        <p className="h-4 truncate text-xs text-ink-muted">{unitPriceLabel}</p>
      </div>
    );
  }

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
      {legend && <p className="text-xs font-semibold text-state-promo">{legend}</p>}
      {quantityPromoText && <p className="text-xs font-semibold text-state-promo">{quantityPromoText}</p>}
      {showPricingHint && pricing.pricing && !byQuantity && (
        <p className="text-xs text-ink-muted">Calculando precio por cantidad…</p>
      )}
      {unitPriceLabel && <p className="text-xs text-ink-muted">{unitPriceLabel}</p>}
    </div>
  );
}
