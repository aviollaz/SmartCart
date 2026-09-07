import { STORES } from "./constants";

const PRICE_FORMATTER = new Intl.NumberFormat("es-AR", {
  style: "currency",
  currency: "ARS",
  minimumFractionDigits: 2,
});

export function formatPrice(value) {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  return PRICE_FORMATTER.format(value);
}

/**
 * Precio por unidad de medida, listo para mostrar: "$14.929,00 por kg".
 *
 * Acá NO se calcula nada: el número lo manda el backend en `product.unit_price`
 * (`{value, base}`, ver `_build_unit_price` en src/api.py). Antes se derivaba
 * en el cliente y las dos partes del cálculo estaban mal por el mismo motivo —
 * el dato no estaba acá. Se dividía `min_price`, que es el mínimo de los precios
 * de LISTA, así que la card anunciaba el precio con promo y el precio por kilo de
 * otro número distinto; y `GET /search` ni siquiera manda `min_price`, así que en
 * resultados de búsqueda el precio por unidad directamente no aparecía.
 *
 * También quedó del lado del backend la decisión de si el número existe: `null`
 * para `unit_type = 'un'` (que es lo que devuelve normalize_magnitude() cuando se
 * dio por vencido, con `total_volume_weight` en el placeholder 1.0) y para
 * cualquier unidad fuera del vocabulario. Una fila que se escapó del vocabulario
 * tiene que caerse de la feature en silencio, no imprimir una unidad equivocada.
 *
 * Base única —por kilo y por litro, siempre—, sin el corte en 1000 que había
 * antes: dos bases conviviendo en la misma grilla rompen justamente la
 * comparabilidad que es el motivo de mostrar este número.
 */
export function formatUnitPrice(product) {
  const unitPrice = product?.unit_price;
  if (!unitPrice || !(unitPrice.value > 0)) return null;
  return `${formatPrice(unitPrice.value)} por ${unitPrice.base}`;
}

export function storeLabel(storeId) {
  return storeId.replace("_online", "").toUpperCase();
}

const STORE_NAMES = Object.fromEntries(STORES.map((store) => [store.id, store.name]));

/**
 * Nombre de la tienda tal como se escribe en una oración ("Coto", "Día"), a
 * diferencia de storeLabel(), que devuelve el encabezado en mayúsculas.
 *
 * Cae a storeLabel() ante un id desconocido: el backend puede conocer una tienda
 * que todavía no está en STORES, y ahí "CARREFOUR" es feo pero correcto, mientras
 * que un undefined en medio de una frase es un bug visible.
 */
export function storeName(storeId) {
  if (!storeId) return "";
  return STORE_NAMES[storeId] || storeLabel(storeId);
}

const SHORT_ADDRESS_MAX = 30;

/**
 * Versión corta de la dirección del perfil, para el chip del Header.
 *
 * Usa `location.street` (calle + altura, que `geocoding.js` saca del `address`
 * estructurado de Nominatim). El primer segmento de `display_name` NO sirve
 * para esto, aunque lo parezca: en un resultado con altura ese segmento es la
 * altura sola —de ahí el "Envío a 3160" que se veía— y en un POI es el nombre
 * del lugar ("Envío a Centro Educativo de Nivel Sec…"), nunca la calle.
 *
 * Se mantiene el fallback al primer segmento para los perfiles guardados antes
 * de que existiera `street`, y para los puntos marcados en el mapa donde el
 * reverse geocoding no devolvió calle: ahí `displayName` son las coordenadas,
 * que también identifican el punto.
 *
 * Devuelve null cuando no hay dirección (nunca onboardeado o "seguir sin
 * dirección"), para que el Header elija el texto del caso vacío.
 */
export function formatShortAddress(location) {
  if (!location || location.skipped || !location.displayName) return null;

  const label = (location.street || location.displayName.split(",")[0] || "").trim();
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
 * primera imagen disponible priorizando Coto, después Día y por último
 * Carrefour (mismo criterio que ya usa el backend en GET /category).
 */
const IMAGE_STORE_PRIORITY = ["coto_online", "dia_online", "carrefour_online"];

export function resolveDisplayImage(product) {
  if (product.image_url) return product.image_url;
  const offers = product.available_at_stores || [];
  for (const storeId of IMAGE_STORE_PRIORITY) {
    const offer = offers.find((o) => o.store_id === storeId && o.image_url);
    if (offer) return offer.image_url;
  }
  return null;
}
