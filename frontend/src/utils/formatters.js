const PRICE_FORMATTER = new Intl.NumberFormat("es-AR", {
  style: "currency",
  currency: "ARS",
  minimumFractionDigits: 2,
});

export function formatPrice(value) {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  return PRICE_FORMATTER.format(value);
}

/** "$X,XX x L" / "x Kg" / "x un" a partir de unit_info + min_price, solo
 * cuando hay datos reales suficientes para calcularlo (no se inventa). */
export function formatUnitPrice(product) {
  const { min_price: minPrice, unit_info: unitInfo } = product;
  if (!unitInfo || !minPrice || minPrice <= 0) return null;
  const weight = unitInfo.total_volume_weight;
  const unitType = unitInfo.unit_type;
  if (!weight || weight <= 0 || !unitType) return null;

  const pricePerUnit = minPrice / weight;
  return `${formatPrice(pricePerUnit)} x ${unitType}`;
}

export function storeLabel(storeId) {
  return storeId.replace("_online", "").toUpperCase();
}

/**
 * GET /search no calcula min_price (a diferencia de GET /category, ver
 * src/api.py) — comportamiento preexistente, igual al que ya tenía el
 * frontend Streamlit. Como paliativo (sin tocar el backend), si min_price no
 * vino calculado se usa el menor precio real entre las ofertas de
 * available_at_stores, que sí llegan completas en ambos endpoints. Se usa
 * tanto para mostrar el precio en la card como para el filtro/orden por
 * precio, así ambos quedan consistentes.
 */
export function resolveDisplayPrice(product) {
  if (typeof product.min_price === "number" && product.min_price > 0) return product.min_price;
  const offerPrices = (product.available_at_stores || [])
    .map((offer) => offer.base_price)
    .filter((price) => typeof price === "number" && price > 0);
  return offerPrices.length > 0 ? Math.min(...offerPrices) : null;
}
