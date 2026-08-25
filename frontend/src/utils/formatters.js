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

// Base de comparación por tamaño: por 100 g / 100 ml para envases chicos, por
// kilo / litro a partir de 1000. Es el corte que ya usa el backend para escribir
// un tamaño (src/substitutions.py: 1000 g -> "1 Kg"), así que las dos mitades del
// proyecto hablan igual de una medida.
//
// Una sola base global rompe en un extremo o en el otro: por kilo, un alfajor de
// 30 g a $2.500 anuncia "$83.333,33 por kg", un número un orden de magnitud
// arriba del precio del propio producto que se lee como un error; por 100 ml, un
// bidón de 5 L da una cifra ilegible de chica. El corte coincide con el límite
// del vocabulario canónico ('g'/'ml' ya vienen normalizados a la unidad chica),
// así que no hace falta ningún dato extra para decidirlo.
const UNIT_BASES = {
  g: { grande: "kg", chica: "100 g" },
  ml: { grande: "L", chica: "100 ml" },
};
const UNIT_BASE_CUTOFF = 1000;

/**
 * Precio por unidad de medida: la primitiva de comparación de una app cuyo
 * propósito es comparar precios. "$X,XX por kg" / "por 100 g" / "por L".
 *
 * Sólo cuando hay datos reales para calcularlo — no se inventa.
 *
 * `unit_type === 'un'` devuelve null y NO cae a "precio por unidad": 'un' es lo
 * que devuelve normalize_magnitude() cuando SE DIO POR VENCIDO (src/size_parser.py),
 * y en ese caso total_volume_weight es el placeholder 1.0. Un "precio por unidad"
 * derivado de eso es el precio del producto disfrazado de una medición que nadie
 * hizo. Una unidad desconocida también sale por null, por el mismo motivo que
 * documenta la etapa 2 de CLAUDE.md: una fila que se escapó del vocabulario tiene
 * que caerse de la feature en silencio, no imprimir una unidad equivocada.
 *
 * MULTIPACKS: el peso NO se multiplica, y no es una omisión. El frontend no puede
 * detectar un multipack — `units_per_pack` viaja en ProductResponse pero el
 * scraper nunca lo escribe, así que llega siempre null —, y portar
 * extract_pack_count() a JS tampoco alcanzaría: su propio docstring dice que el
 * número al lado del "xN" es a veces el total del pack y a veces el de cada
 * unidad, sin nada que los distinga. Al no multiplicar, el error sólo puede ir
 * hacia CARO (N× de más cuando el tamaño guardado era el unitario), nunca hacia
 * barato. Es la misma asimetría de los flags dietarios y de los swaps: errar caro
 * resigna un ahorro, errar barato rompe la promesa. El arreglo de fondo es del
 * backend — decidir pack-vs-unidad en el ingest, donde está la evidencia.
 */
export function formatUnitPrice(product) {
  const { min_price: minPrice, unit_info: unitInfo } = product;
  if (!unitInfo || !minPrice || minPrice <= 0) return null;

  const weight = unitInfo.total_volume_weight;
  const base = UNIT_BASES[unitInfo.unit_type];
  if (!base || !weight || weight <= 0 || !Number.isFinite(weight)) return null;

  const grande = weight >= UNIT_BASE_CUTOFF;
  const pricePerBase = (minPrice / weight) * (grande ? UNIT_BASE_CUTOFF : 100);
  return `${formatPrice(pricePerBase)} por ${grande ? base.grande : base.chica}`;
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
