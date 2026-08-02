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

const SHORT_ADDRESS_MAX = 30;

/**
 * Versión corta de la dirección del perfil, para el chip del Header.
 *
 * Nominatim devuelve el camino completo ("Avenida Cabildo 1234, Belgrano,
 * Comuna 13, Buenos Aires, ..."), del que solo interesa el primer segmento: el
 * resto es jerarquía administrativa que no ayuda a reconocer la dirección y no
 * entra en una barra. Cuando el punto se fijó en el mapa sin reverse geocoding,
 * displayName son las coordenadas, que también sirven como identificación.
 *
 * Devuelve null cuando no hay dirección (nunca onboardeado o "seguir sin
 * dirección"), para que el Header elija el texto del caso vacío.
 */
export function formatShortAddress(location) {
  if (!location || location.skipped || !location.displayName) return null;
  const [firstSegment] = location.displayName.split(",");
  const label = firstSegment.trim();
  if (!label) return null;
  return label.length > SHORT_ADDRESS_MAX ? `${label.slice(0, SHORT_ADDRESS_MAX - 1)}…` : label;
}

/**
 * El precio que anuncia la card: el más barato entre tiendas, ya con la promo
 * que rige desde la primera unidad (`promo_unit_price`, que el backend calcula
 * con el mismo evaluador que el optimizador — ver `_build_store_offer` en
 * src/api.py). Las promos condicionales ("Llevando 2", "3x2") vienen en null
 * ahí, así que a una unidad esto devuelve el precio de lista; el precio por
 * cantidad lo resuelve useFlattenedPrice cuando el usuario sube el selector.
 *
 * Las ofertas van primero y `min_price` quedó de fallback (antes era al revés):
 * el backend lo calcula como el mínimo de los precios de LISTA, así que
 * priorizarlo tapaba el descuento. Sigue haciendo falta porque GET /search no
 * lo manda y porque stripUnavailableStores() lo anula a propósito.
 *
 * Se usa tanto para mostrar el precio como para el filtro/orden por precio
 * (hooks/useProductFilters.js), así la grilla ordena por lo que muestra.
 */
export function resolveDisplayPrice(product) {
  const best = resolveBestOffer(product);
  if (best) return best.price;
  if (typeof product.min_price === "number" && product.min_price > 0) return product.min_price;
  return null;
}

/** La oferta que define el precio de la card: `{offer, price}` con el neto ya
 * aplicado, o null. Se expone aparte de resolveDisplayPrice para que la card
 * pueda nombrar la tienda y la promo que ganaron sin volver a buscarlas. */
export function resolveBestOffer(product) {
  let best = null;
  for (const offer of product.available_at_stores || []) {
    const price = offer.promo_unit_price ?? offer.base_price;
    if (typeof price !== "number" || price <= 0) continue;
    if (!best || price < best.price) best = { offer, price };
  }
  return best;
}

/**
 * GET /search no calcula un image_url a nivel de producto (mismo gap que
 * min_price, ver resolveDisplayPrice), aunque sí trae image_url por oferta en
 * available_at_stores. Como paliativo, si no vino resuelto se busca la
 * primera imagen disponible priorizando Coto sobre Día (mismo criterio que
 * ya usa el backend en GET /category).
 */
export function resolveDisplayImage(product) {
  if (product.image_url) return product.image_url;
  const offers = product.available_at_stores || [];
  const cotoOffer = offers.find((offer) => offer.store_id === "coto_online" && offer.image_url);
  if (cotoOffer) return cotoOffer.image_url;
  const diaOffer = offers.find((offer) => offer.store_id === "dia_online" && offer.image_url);
  if (diaOffer) return diaOffer.image_url;
  return null;
}
